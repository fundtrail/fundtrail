"""Problems on records and files (contracts.md section 8), raised by code.

- a bill linked for more than its total
- a bill with money nobody charged, 60 days after it arrived. The shared-cost
  case, provisional decision 0021, plugs in at _unused_bill(): until it's
  settled, each grant's copy of a shared invoice shows the other grant's part here.
- a term waiting for the accountant to confirm it
- confirmed terms that disagree (see _disagreeing_terms for the provisional rule)
- the exact same file on the grant twice
- a confirmed approval rule that code can't place (each charge also gets a
  Needs a human reason pointing at it)
- the agent's flag on a record or a file, until the accountant settles it
- an agent run that failed for good, on the file or record that triggered it
"""

from collections import defaultdict
from collections.abc import Hashable
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.checks.answers import ANSWER_BUCKET
from app.checks.codes import flag_code
from app.checks.findings import AGENT_RUN, APPROVAL, BILL, SAME_FILE, TERMS, Finding
from app.checks.rules_match import rule_category
from app.checks.text import day, money, norm
from app.checks.view import GrantView, LinkInForce, notice_number
from app.contracts.checks import MISSING_EVIDENCE_DAYS, Bucket
from app.contracts.evidence import EvidenceFile
from app.contracts.records import (
    Answer,
    ApprovalRule,
    Author,
    Bill,
    BudgetLine,
    Judgment,
    Notice,
    PeriodOfPerformance,
    Question,
    Rate,
    Record,
)
from app.contracts.runs import AgentRun, TriggerKind

from .checklist import compare


@dataclass
class Subject:
    record_id: str | None = None
    file_id: str | None = None


@dataclass
class SubjectFinding:
    subject: Subject
    finding: Finding


def _arrived(view: GrantView, record: Record) -> datetime:
    times = [view.files[f].arrived_at for f in view.files_of(record) if f in view.files]
    return min(times) if times else record.written_at


def over_linked_bills(view: GrantView) -> set[str]:
    out: set[str] = set()
    for r in view.current:
        if isinstance(r.data, Bill) and not view.is_copy(r):
            links = view.using_links(r.id)
            total = sum(lk.data.amount_cents or 0 for lk in links)
            if compare(total, r.data.total.value) > 0:
                out.add(r.id)
    return out


def _bill_problems(view: GrantView, now: datetime) -> list[SubjectFinding]:
    out: list[SubjectFinding] = []
    for r in view.current:
        bill = r.data
        if not isinstance(bill, Bill) or view.is_copy(r):
            continue
        all_links = view.links_to_fact.get(r.id, [])
        links = view.using_links(r.id)
        # Links to a fully reversed charge don't use up the total (it's free to be linked
        # again), but the ledger shows what happened to that money, so it's accounted
        # for when asking whether any of the bill is money nobody charged (decision 0020).
        freed = sum(lk.data.amount_cents or 0 for lk in all_links if lk not in links)
        total = sum(lk.data.amount_cents or 0 for lk in links)
        target = bill.total.value
        side = compare(total, target)
        ids = [r.id] + [lk.link.id for lk in links]
        if side > 0:
            out.append(
                SubjectFinding(
                    Subject(record_id=r.id),
                    Finding(
                        BILL,
                        "over_linked",
                        Bucket.NEEDS_HUMAN,
                        f"Linked for {money(total)}, more than its total of {money(target)}.",
                        ids,
                    ),
                )
            )
        # A remainder record that counts says where the rest went (0021).
        elif (
            side < 0
            and compare(total + freed, target) < 0
            and not view.has_remainder(r.id)
            and not _credit_on_a_credit_line(view, target, links)
        ):
            found = _unused_bill(view, r, now, total + freed, target, ids)
            if found is not None:
                out.append(found)
    return out


def _credit_on_a_credit_line(view: GrantView, target: int, links: list[LinkInForce]) -> bool:
    """A credit (a bill with a negative total) linked to a line that takes money off the grant.

    Call 38 (#74): that link can't carry an amount, but the ledger shows what happened
    to the money, so the credit isn't "money nobody charged".
    """
    if target >= 0:
        return False
    charges = {c.id: c for c in view.charges}
    return any(
        (c := charges.get(lk.data.charge_id)) is not None and c.amount_cents < 0 for lk in links
    )


def _unused_bill(
    view: GrantView, r: Record, now: datetime, total: int, target: int, ids: list[str]
) -> SubjectFinding | None:
    # Decision 0021 (provisional, shared costs) plugs in here.
    # Reached only when the links are under the total with the same sign: links of
    # the opposite sign are "over" (compare), so the amount left has the bill's sign.
    arrived = _arrived(view, r)
    if now < arrived + timedelta(days=MISSING_EVIDENCE_DAYS):
        return None
    return SubjectFinding(
        Subject(record_id=r.id),
        Finding(
            BILL,
            "unused",
            Bucket.NEEDS_HUMAN,
            f"{money(target - total)} of this bill's {money(target)} isn't linked to any charge, "
            f"{(now - arrived).days} days after it arrived on {day(arrived.date())}.",
            ids,
        ),
    )


def _term_label(r: Record) -> str:
    return r.kind.value.replace("_", " ")


def _disagreeing_terms(view: GrantView) -> list[SubjectFinding]:
    """Confirmed terms that disagree.

    Provisional and kept minimal (architecture.md: discussed with Alex before building):

    - two periods of performance with the same date that state different dates
    - two budget lines with the same date and category that state different amounts
    - two notices with the same amendment number that state different types or amounts
    - two rates with the same name and date that state different rates
    """
    groups: dict[Hashable, list[tuple[Record, Hashable]]] = defaultdict(list)
    for r in view.current:
        d = r.data
        if isinstance(d, PeriodOfPerformance):
            value = (d.start.value if d.start else None, d.end.value)
            groups[("period", d.dated.value)].append((r, value))
        elif isinstance(d, BudgetLine):
            groups[("budget_line", d.dated.value, d.category)].append((r, d.amount.value))
        elif isinstance(d, Notice):
            value = (
                norm(d.amendment_type.value),
                d.obligated_by_amendment.value if d.obligated_by_amendment else None,
                d.obligated_to_date.value if d.obligated_to_date else None,
            )
            key = notice_number(d)
            groups[("notice", key if key is not None else norm(d.amendment_number.value))].append(
                (r, value)
            )
        elif isinstance(d, Rate):
            # Ruling 61: a benefit rate is one per group and start date, so rates the
            # same agreement prints for several groups or years don't disagree.
            key = (
                "rate",
                norm(d.name.value),
                d.dated.value,
                d.applies_to.value if d.applies_to else None,
                d.effective_from.value if d.effective_from else None,
            )
            groups[key].append((r, d.rate.value))
    out: list[SubjectFinding] = []
    for members in groups.values():
        if len({v for _, v in members}) < 2:
            continue
        ids = [r.id for r, _ in members]
        for r, _ in members:
            out.append(
                SubjectFinding(
                    Subject(record_id=r.id),
                    Finding(
                        TERMS,
                        "disagree",
                        Bucket.NEEDS_HUMAN,
                        f"This {_term_label(r)} disagrees with another confirmed term of the "
                        "same date.",
                        ids,
                    ),
                )
            )
    return out


def record_problems(
    view: GrantView, now: datetime, failed_runs: list[AgentRun]
) -> list[SubjectFinding]:
    out = _bill_problems(view, now)

    for r in view.waiting_terms:
        out.append(
            SubjectFinding(
                Subject(record_id=r.id),
                Finding(
                    TERMS,
                    "waiting",
                    Bucket.NEEDS_HUMAN,
                    f"This {_term_label(r)} is waiting for the accountant to confirm it.",
                    [r.id],
                ),
            )
        )
    out += _disagreeing_terms(view)

    for rule in view.approval_rules():
        if rule_category(view, rule) is None:
            assert isinstance(rule.data, ApprovalRule)
            out.append(
                SubjectFinding(
                    Subject(record_id=rule.id),
                    Finding(
                        APPROVAL,
                        "rule_unmatched",
                        Bucket.NEEDS_HUMAN,
                        "Code can't tell which charges this approval rule, for "
                        f"'{rule.data.applies_to.value}', applies to.",
                        [rule.id],
                    ),
                )
            )

    by_hash: dict[str, list[str]] = defaultdict(list)

    # The first to arrive is the original. Equal arrival times go by stored order
    # (call 36, ruling 4); a file not stored yet comes after, and ID only breaks
    # what's left.
    def arrival(f: EvidenceFile) -> tuple[datetime, bool, int, str]:
        return (f.arrived_at, f.stored_seq is None, f.stored_seq or 0, f.id)

    for f in sorted(view.files.values(), key=arrival):
        by_hash[f.sha256].append(f.id)
    for ids in by_hash.values():
        first = view.files[ids[0]]
        for file_id in ids[1:]:
            out.append(
                SubjectFinding(
                    Subject(file_id=file_id),
                    Finding(
                        SAME_FILE,
                        "same_file",
                        Bucket.NEEDS_HUMAN,
                        f"The exact same file as {first.name}, which arrived on "
                        f"{day(first.arrived_at.date())}.",
                    ),
                )
            )

    taken: dict[tuple[str | None, str | None], set[str]] = {}
    for r in view.judgments:
        j = r.data
        assert isinstance(j, Judgment)
        if j.question != Question.FLAG or j.charge_id is not None or j.answer == Answer.SUPPORTS:
            continue
        if j.record_id is not None:
            now_version = view.state.current_version(j.record_id)
            subject = Subject(record_id=now_version.id if now_version else j.record_id)
        else:
            subject = Subject(file_id=j.file_id)
        who = (
            "The agent flagged this"
            if r.author == Author.AGENT
            else "The accountant answered the agent's flag"
        )
        out.append(
            SubjectFinding(
                subject,
                Finding(
                    "flag",
                    flag_code(
                        view, r, taken.setdefault((subject.record_id, subject.file_id), set())
                    ),
                    ANSWER_BUCKET[j.answer],
                    f"{who}: {j.text}",
                    [r.id, *j.rests_on],
                ),
            )
        )

    for run in failed_runs:
        # A charge's run is a reason on the charge (charge_checks.py), and the
        # clock's is on the grant (grant_checks.py). Here: a file's or a record's run,
        # a thread run on the record its thread is about, and an open question's run
        # on the record whose question is open.
        kind = run.trigger.kind
        subject: Subject | None = None
        text = "The agent couldn't finish reading this."
        record_id: str | None = None
        if kind == TriggerKind.FILE and run.trigger.id in view.files:
            subject = Subject(file_id=run.trigger.id)
        elif kind == TriggerKind.RECORD:
            record_id = run.trigger.id
        elif kind == TriggerKind.THREAD_MESSAGE and run.thread_record_id is not None:
            record_id = run.thread_record_id
            text = "The agent couldn't finish answering a message in this record's thread."
        elif kind == TriggerKind.OPEN_QUESTION:
            record_id = run.trigger.id
            text = "The agent couldn't finish answering an open question on this record."
        if record_id is not None:
            # Like a flag, on the record as it stands now, following corrections.
            now_version = view.state.current_version(record_id)
            found = now_version or view.state.by_id.get(record_id)
            if found is not None and found.grant_id == view.grant_id:
                subject = Subject(record_id=found.id)
        if subject is not None:
            out.append(
                SubjectFinding(
                    subject,
                    Finding(AGENT_RUN, f"failed:{run.id}", Bucket.NEEDS_HUMAN, text),
                )
            )
    return out
