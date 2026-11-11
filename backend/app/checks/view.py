"""One grant's records with what counts worked out.

The terms in force, links, assignments and answers.

Built once per run of the checks from rules.RecordState, and read by every check.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import cached_property
from typing import TYPE_CHECKING

from app.contracts.charges import Charge
from app.contracts.corrections import NetAmount, net_amounts
from app.contracts.evidence import EvidenceFile
from app.contracts.records import (
    FACT_KINDS,
    TERM_KINDS,
    BenefitGroup,
    BudgetAssignment,
    BudgetLine,
    ChecklistItem,
    ChecklistRemoval,
    Decision,
    Duplicate,
    Judgment,
    Link,
    Notice,
    OtherTerm,
    PeriodOfPerformance,
    Person,
    Question,
    Record,
    RecordKind,
    Remainder,
    citations,
)
from app.contracts.rules import RecordState

if TYPE_CHECKING:
    from app.checks.benefits import Cell


@dataclass(frozen=True)
class PeriodInForce:
    """The grant's period in force, from its confirmed period_of_performance terms.

    The latest-dated term that states an end gives the end, and the latest-dated
    term that states a start gives the start (an extension states only its end).
    """

    start: date | None
    end: date
    record_ids: list[str]  # the terms that give the start and the end
    disagree: list[str]  # confirmed terms with the same date that state different dates


@dataclass(frozen=True)
class LinkInForce:
    link: Record  # a current link
    fact: Record  # the record it points to now, following corrections

    @property
    def data(self) -> Link:
        assert isinstance(self.link.data, Link)
        return self.link.data


class GrantView:
    def __init__(
        self,
        grant_id: str,
        state: RecordState,
        charges: Sequence[Charge],
        files: Sequence[EvidenceFile],
    ):
        self.grant_id = grant_id
        self.state = state
        self.charges = [c for c in charges if c.grant_id == grant_id]
        self.files = {f.id: f for f in files if f.grant_id == grant_id}
        self.records = [r for r in state.records if r.grant_id == grant_id]
        self.pos = {r.id: i for i, r in enumerate(state.records)}
        self.current = [r for r in self.records if state.is_current(r.id)]
        self.waiting = [r for r in self.records if state.is_waiting(r.id)]

        self.terms: dict[RecordKind, list[Record]] = defaultdict(list)
        for r in self.current:
            if r.kind in TERM_KINDS:
                self.terms[r.kind].append(r)
        self.waiting_terms = [r for r in self.waiting if r.kind in TERM_KINDS]

        # Files the accountant confirmed as copies: they stay out of matching.
        self.copy_files = {
            r.data.copy_file_id
            for r in self.current
            if isinstance(r.data, Duplicate) and state.decision(r.id) == Decision.CONFIRMED
        }

        self.links: dict[str, list[LinkInForce]] = defaultdict(list)  # by charge
        self.links_to_fact: dict[str, list[LinkInForce]] = defaultdict(list)  # by fact
        self.assignment: dict[str, Record] = {}
        self.items: dict[str, list[Record]] = defaultdict(list)
        self.removals: dict[str, list[Record]] = defaultdict(list)
        self.judgments: list[Record] = []
        for r in self.current:
            data = r.data
            if isinstance(data, Link):
                fact = state.current_version(data.record_id)
                if fact is None or fact.kind not in FACT_KINDS or self.is_copy(fact):
                    continue
                lif = LinkInForce(r, fact)
                self.links[data.charge_id].append(lif)
                self.links_to_fact[fact.id].append(lif)
            elif isinstance(data, BudgetAssignment):
                self.assignment[data.charge_id] = r  # at most one is current; the latest wins
            elif isinstance(data, ChecklistItem):
                self.items[data.charge_id].append(r)
            elif isinstance(data, ChecklistRemoval):
                self.removals[data.charge_id].append(r)
            elif isinstance(data, Judgment):
                self.judgments.append(r)

        self.period = _period_in_force(self.terms[RecordKind.PERIOD_OF_PERFORMANCE])
        # Decision 0020: each charge netted with the lines that correct it.
        self.nets: dict[str, NetAmount] = net_amounts(self.charges, state)

    @cached_property
    def benefit_cells(self) -> dict[tuple[BenefitGroup, date], "Cell"]:
        """Ruling 61: the benefit charges and salary lines by group and month, worked out
        once per view (benefits.cells)."""
        from app.checks.benefits import cells  # benefits reads this module

        return cells(self)

    # Small helpers every check uses.

    def root(self, record_id: str) -> str:
        """The first record in a chain of corrections: stable while the record is corrected."""
        seen: set[str] = set()
        r = self.state.by_id.get(record_id)
        while r is not None and r.replaces_id is not None and r.id not in seen:
            seen.add(r.id)
            older = self.state.by_id.get(r.replaces_id)
            if older is None:
                break
            r = older
        return r.id if r is not None else record_id

    def using_links(self, fact_id: str) -> list[LinkInForce]:
        """The links that use up a bill's total. Decision 0020: a link to a fully reversed
        charge doesn't, so the bill is free to be linked to the line that now carries it."""
        return [
            lk
            for lk in self.links_to_fact.get(fact_id, [])
            if not ((net := self.nets.get(lk.data.charge_id)) is not None and net.reversed)
        ]

    def has_remainder(self, bill_id: str) -> bool:
        """Decision 0021: a current remainder record says the rest of this bill belongs
        to another award. The agent's waits for the accountant."""
        for r in self.current:
            if isinstance(r.data, Remainder):
                now = self.state.current_version(r.data.record_id)
                if now is not None and now.id == bill_id:
                    return True
        return False

    def files_of(self, record: Record) -> set[str]:
        return {c.file_id for c in citations(record.data)}

    def is_copy(self, record: Record) -> bool:
        files = self.files_of(record)
        return bool(files) and files <= self.copy_files

    def is_email(self, record: Record) -> bool:
        """Whether a record was read from an email."""
        return any(
            (f := self.files.get(fid)) is not None
            and (f.media_type == "message/rfc822" or f.source == "gmail")
            for fid in self.files_of(record)
        )

    def assigned_line(self, charge_id: str) -> tuple[Record, Record | None] | None:
        """The charge's current budget assignment, and the budget_line it points to now.

        The line is None when it isn't confirmed, or no longer in force.
        """
        assignment = self.assignment.get(charge_id)
        if assignment is None:
            return None
        assert isinstance(assignment.data, BudgetAssignment)
        line = self.state.current_version(assignment.data.record_id)
        if line is None or not isinstance(line.data, BudgetLine):
            return assignment, None
        return assignment, line

    def unconfirmed_line(self, charge_id: str) -> Record | None:
        """The budget_line a charge is assigned to, when it's still waiting for the accountant."""
        assignment = self.assignment.get(charge_id)
        if assignment is None:
            return None
        assert isinstance(assignment.data, BudgetAssignment)
        line = self.state.by_id.get(assignment.data.record_id)
        if line is not None and self.state.is_waiting(line.id):
            return line
        return None

    def people_by_email(self) -> dict[str, Person]:
        found: dict[str, Person] = {}
        for r in self.terms[RecordKind.PERSON]:
            assert isinstance(r.data, Person)
            if r.data.email is not None:
                found[r.data.email.value.strip().lower()] = r.data
        return found

    def approval_rules(self) -> list[Record]:
        return self.terms[RecordKind.APPROVAL_RULE]

    def budget_lines(self) -> list[Record]:
        return self.terms[RecordKind.BUDGET_LINE]

    def notices(self) -> list[Record]:
        return self.terms[RecordKind.NOTICE]

    def other_terms_on(self, day: date) -> list[Record]:
        """Confirmed other_terms in force on a date: each is in force from its own date on."""
        out: list[Record] = []
        for r in self.terms[RecordKind.OTHER_TERM]:
            assert isinstance(r.data, OtherTerm)
            if r.data.dated.value <= day:
                out.append(r)
        return out

    def judgments_for(
        self, charge_id: str, question: Question, record_id: str | None
    ) -> list[Record]:
        """Current answers to one question, matching the record it's about through corrections."""
        out: list[Record] = []
        for r in self.judgments:
            j = r.data
            assert isinstance(j, Judgment)
            if j.question != question or j.charge_id != charge_id:
                continue
            about = None
            if j.record_id is not None:
                now = self.state.current_version(j.record_id)
                about = now.id if now is not None else j.record_id
            if about == record_id:
                out.append(r)
        return out

    def ever_answered_by_user(
        self, charge_id: str, question: Question, record_id: str | None
    ) -> bool:
        for r in self.records:
            j = r.data
            if r.author.value != "user" or not isinstance(j, Judgment):
                continue
            if j.question != question or j.charge_id != charge_id:
                continue
            about = None if j.record_id is None else self.root(j.record_id)
            if about == (None if record_id is None else self.root(record_id)):
                return True
        return False


def period_in_force(grant_id: str, records: Sequence[Record]) -> PeriodInForce | None:
    """A grant's period in force, the same one the checks use. None when no dates are confirmed.

    `records` are the workspace's records visible at the clock's "now", in the order
    they were written. The latest-dated confirmed term gives the end, and the
    latest-dated one that states a start gives the start. When confirmed terms of
    the same date disagree, `disagree` names them and the dates can't be relied on.
    """
    state = RecordState(records)
    terms = [
        r
        for r in records
        if r.grant_id == grant_id
        and r.kind == RecordKind.PERIOD_OF_PERFORMANCE
        and state.is_current(r.id)
    ]
    return _period_in_force(terms)


def _period_in_force(terms: list[Record]) -> PeriodInForce | None:
    periods = [(r, r.data) for r in terms if isinstance(r.data, PeriodOfPerformance)]
    if not periods:
        return None

    def latest(pairs: list[tuple[Record, PeriodOfPerformance]], value):  # type: ignore[no-untyped-def]
        top = max(p.dated.value for _, p in pairs)
        tied = [(r, p) for r, p in pairs if p.dated.value == top]
        values = {value(p) for _, p in tied}
        chosen = tied[-1][0]
        disagree = [r.id for r, _ in tied] if len(values) > 1 else []
        return chosen, value(tied[-1][1]), disagree

    end_record, end, end_disagree = latest(periods, lambda p: p.end.value)
    with_start = [(r, p) for r, p in periods if p.start is not None]
    start: date | None = None
    record_ids = [end_record.id]
    disagree = list(end_disagree)
    if with_start:
        start_record, start, start_disagree = latest(with_start, lambda p: p.start.value)
        if start_record.id not in record_ids:
            record_ids.insert(0, start_record.id)
        disagree += [d for d in start_disagree if d not in disagree]
    return PeriodInForce(start=start, end=end, record_ids=record_ids, disagree=disagree)


def notice_number(notice: Notice) -> int | None:
    text = notice.amendment_number.value.strip()
    return int(text) if text.isdigit() else None


def net_of(view: GrantView, charge: Charge) -> int:
    """The amount that counts for a charge: its net once corrections are netted into it."""
    found = view.nets.get(charge.id)
    return found.net_cents if found is not None else charge.amount_cents


def is_reversed(view: GrantView, charge: Charge) -> bool:
    """Fully corrected (decision 0020): something was netted into it and the net is zero."""
    found = view.nets.get(charge.id)
    return found is not None and found.reversed
