"""What counts, and the write check.

From docs/contracts.md section 1, "What counts" and "Checking a write".

Every area applies these rules through the same functions:

- what waits for the accountant: the agent's records that count only once a
  confirmation lists them with "confirmed"
- current records: the records that count, minus those an effective record
  replaces, minus retractions
- a pointer follows a correction: current_version()
- check_new_record(): the problems with a record about to be written

Pass only the records and files visible at the clock's "now", and pass records
in the order they were written (the database orders them by written_at, then
by its real-time created_at). Whether one of the agent's records waits is
decided from what was written before it.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime

from .charges import Charge
from .evidence import EvidenceFile
from .records import (
    FACT_KINDS,
    FOUND,
    TERM_KINDS,
    AcceptedReason,
    Answer,
    Author,
    BudgetAssignment,
    ChecklistItem,
    ChecklistRemoval,
    Confirmation,
    Decision,
    DefaultItems,
    Dispute,
    Duplicate,
    Judgment,
    Link,
    Question,
    Record,
    RecordKind,
    Snooze,
    citations,
    cited_values,
)

# Kinds of the agent's that always wait for the accountant.
_ALWAYS_WAIT = TERM_KINDS | {RecordKind.CHECKLIST_REMOVAL, RecordKind.DISPUTE, RecordKind.DUPLICATE}

# How strong a concern an answer raises. Moving down this order clears or weakens a problem.
_CONCERN = {Answer.SUPPORTS: 0, Answer.UNSURE: 1, Answer.CONTRADICTS: 2}


class RecordState:
    """The records and files visible at one moment, with what counts worked out.

    Build it once and ask it many questions. The module's functions wrap it.
    """

    def __init__(self, records: Iterable[Record], files: Iterable[EvidenceFile] = ()):
        self.records: list[Record] = list(records)
        self.files: dict[str, EvidenceFile] = {f.id: f for f in files}
        self.by_id: dict[str, Record] = {}
        self._pos: dict[str, int] = {}
        self._replacers: dict[str, list[str]] = {}
        self._confirmations_of: dict[str, list[str]] = {}
        self._links_of: dict[str, list[str]] = {}  # by charge
        self._answers_of: dict[tuple[str, str | None, str | None], list[str]] = {}
        self._waits: dict[str, bool] = {}
        self._effective_memo: dict[tuple[str, int], bool] = {}
        for i, r in enumerate(self.records):
            if r.id in self.by_id:
                raise ValueError(f"record {r.id} appears twice")
            self.by_id[r.id] = r
            self._pos[r.id] = i
            self._waits[r.id] = self._decide_waits(r, i)
            if r.replaces_id is not None:
                self._replacers.setdefault(r.replaces_id, []).append(r.id)
            if isinstance(r.data, Confirmation) and r.author == Author.USER:
                for target in r.data.record_ids:
                    self._confirmations_of.setdefault(target, []).append(r.id)
            if isinstance(r.data, Link):
                self._links_of.setdefault(r.data.charge_id, []).append(r.id)
            if isinstance(r.data, Judgment) and r.data.question != Question.FLAG:
                self._answers_of.setdefault(_answer_key(r.data), []).append(r.id)
        self._end = len(self.records)

    # Questions about the state at the end, which is "now".

    def waits(self, record_id: str) -> bool:
        """Whether one of the agent's records counts only once the accountant confirms it."""
        return self._waits[record_id]

    def decision(self, record_id: str) -> Decision | None:
        """The accountant's latest decision on a record, from confirmations nothing replaced."""
        found = self._decision_at(record_id, self._end)
        return found[0] if found else None

    def decided_by(self, record_id: str) -> Record | None:
        """The confirmation that made the latest decision on a record."""
        found = self._decision_at(record_id, self._end)
        return self.by_id[found[1]] if found else None

    def is_effective(self, record_id: str) -> bool:
        """Counts: not rejected, and either it doesn't wait or the accountant confirmed it."""
        return self._effective_at(record_id, self._end)

    def is_current(self, record_id: str) -> bool:
        return self._current_at(record_id, self._end)

    def is_waiting(self, record_id: str) -> bool:
        """Waits for the accountant with no decision yet, and what it replaces is current."""
        r = self.by_id[record_id]
        if not self._waits[record_id] or self.decision(record_id) is not None:
            return False
        if self.is_replaced(record_id):
            return False  # the accountant replaced it, for example by typing the right value
        return r.replaces_id is None or self.is_current(r.replaces_id)

    def is_replaced(self, record_id: str) -> bool:
        """Whether a record that counts replaces this one."""
        return bool(self._replaced_at(record_id, self._end))

    def effective(self) -> list[Record]:
        return [r for r in self.records if self.is_effective(r.id)]

    def current(self) -> list[Record]:
        return [r for r in self.records if self.is_current(r.id)]

    def waiting(self) -> list[Record]:
        return [r for r in self.records if self.is_waiting(r.id)]

    def current_version(self, record_id: str) -> Record | None:
        """Follows a pointer through corrections to the record that counts now.

        None when the record doesn't exist, or when it was retracted, or when it
        and everything replacing it is rejected or still waiting.
        """
        return self._current_version_at(record_id, self._end)

    def unconfirmed_values(self, record: Record) -> list[str]:
        """The paths of a record's values that aren't confirmed.

        A value is confirmed when its citation was found in its file, when the
        accountant confirmed the record it's in, or when the accountant typed it.
        """
        if record.author == Author.USER or self.decision(record.id) == Decision.CONFIRMED:
            return []
        return [
            path
            for path, value in cited_values(record.data)
            if value.citation is None or value.citation.match not in FOUND
        ]

    def new_evidence_between(
        self, after: datetime, until: datetime, grant_id: str, *, before: int | None = None
    ) -> bool:
        """Whether new evidence arrived on a grant in (after, until].

        New evidence is a file that arrived, or a grant term the accountant
        confirmed or typed. Something the agent links later from what was
        already on file doesn't count, and neither does confirming a term again.
        `before` limits it to the records written before that position.
        """
        for f in self.files.values():
            if f.grant_id == grant_id and after < f.arrived_at <= until:
                return True
        for r in self.records[:before]:
            if r.grant_id != grant_id or r.author != Author.USER:
                continue
            if not after < r.written_at <= until:
                continue
            if r.kind in TERM_KINDS:
                return True
            data = r.data
            if isinstance(data, Confirmation) and data.decision == Decision.CONFIRMED:
                for t in data.record_ids:
                    term = self.by_id.get(t)
                    if term is None or term.kind not in TERM_KINDS:
                        continue
                    earlier = self._decision_at(t, self._pos[r.id])
                    if earlier is None or earlier[0] != Decision.CONFIRMED:
                        return True
        return False

    # The same questions, asked as of record position i: only records[:i] are written.

    def _decision_at(self, record_id: str, i: int) -> tuple[Decision, str] | None:
        for conf_id in reversed(self._confirmations_of.get(record_id, [])):
            if self._pos[conf_id] >= i:
                continue
            if any(
                self._pos[r] < i and self._effective_at(r, i)
                for r in self._replacers.get(conf_id, [])
            ):
                continue  # only confirmations that nothing has replaced are counted
            conf = self.by_id[conf_id].data
            if isinstance(conf, Confirmation):
                return conf.decision, conf_id
        return None

    def _effective_at(self, record_id: str, i: int) -> bool:
        key = (record_id, i)
        if key not in self._effective_memo:
            found = self._decision_at(record_id, i)
            if found and found[0] == Decision.REJECTED:
                result = False
            elif self._waits[record_id]:
                result = found is not None and found[0] == Decision.CONFIRMED
            else:
                result = True
            self._effective_memo[key] = result
        return self._effective_memo[key]

    def _replaced_at(self, record_id: str, i: int) -> list[str]:
        return [
            r
            for r in self._replacers.get(record_id, [])
            if self._pos[r] < i and self._effective_at(r, i)
        ]

    def _current_at(self, record_id: str, i: int) -> bool:
        r = self.by_id.get(record_id)
        if r is None or self._pos[record_id] >= i or r.kind == RecordKind.RETRACTION:
            return False
        return self._effective_at(record_id, i) and not self._replaced_at(record_id, i)

    def _current_version_at(self, record_id: str, i: int) -> Record | None:
        seen: set[str] = set()
        while record_id in self.by_id and record_id not in seen and self._pos[record_id] < i:
            seen.add(record_id)
            replacers = self._replaced_at(record_id, i)
            if replacers:
                record_id = replacers[-1]
                continue
            r = self.by_id[record_id]
            if not self._effective_at(record_id, i) or r.kind == RecordKind.RETRACTION:
                return None
            return r
        return None

    def _decide_waits(self, r: Record, i: int) -> bool:
        """Whether one of the agent's records waits, decided from the records written before it."""
        if r.author != Author.AGENT:
            return False
        if r.kind in _ALWAYS_WAIT:
            return True
        data = r.data
        if r.replaces_id is not None:
            old = self.by_id.get(r.replaces_id)
            if (
                isinstance(data, Judgment)
                and old is not None
                and old.author == Author.AGENT
                and isinstance(old.data, Judgment)
            ):
                return self._new_answer_waits(old, old.data.answer, r, data.answer, i)
            return True  # a fix, a correction, a withdrawal, or a new answer to the accountant's
        if isinstance(data, Judgment) and data.question != Question.FLAG:
            # A second answer beside its own is a new answer over it.
            for old_id in reversed(self._answers_of.get(_answer_key(data), [])):
                old = self.by_id[old_id]
                if (
                    old.author == Author.AGENT
                    and isinstance(old.data, Judgment)
                    and self._current_at(old_id, i)
                ):
                    return self._new_answer_waits(old, old.data.answer, r, data.answer, i)
            return False
        if isinstance(data, Link):
            return self._second_bill_link(data, i)
        return False

    def _new_answer_waits(
        self, old: Record, before: Answer, new: Record, after: Answer, i: int
    ) -> bool:
        if _CONCERN[after] >= _CONCERN[before]:
            return False  # the same answer refreshed, or a change toward a concern
        if before == Answer.CONTRADICTS:
            return True  # contradicts turning into anything milder
        # unsure turning into supports counts right away only once new evidence has arrived
        return not self.new_evidence_between(old.written_at, new.written_at, new.grant_id, before=i)

    def _second_bill_link(self, link: Link, i: int) -> bool:
        bill = self._current_version_at(link.record_id, i)
        if bill is None or bill.kind != RecordKind.BILL:
            return False
        for other_id in self._links_of.get(link.charge_id, []):
            if self._pos[other_id] >= i or not self._current_at(other_id, i):
                continue
            other = self.by_id[other_id].data
            if not isinstance(other, Link):
                continue
            other_bill = self._current_version_at(other.record_id, i)
            if other_bill is not None and other_bill.id == bill.id:
                return True
        return False


def _answer_key(answer: Judgment) -> tuple[str, str | None, str | None]:
    return (answer.question.value, answer.charge_id, answer.record_id)


# The module's functions, for a single question.


def effective_records(
    records: Iterable[Record], files: Iterable[EvidenceFile] = ()
) -> list[Record]:
    """The records that count: all except those waiting for, or rejected by, the accountant."""
    return RecordState(records, files).effective()


def current_records(records: Iterable[Record], files: Iterable[EvidenceFile] = ()) -> list[Record]:
    """The records that count, minus those an effective record replaces, minus retractions."""
    return RecordState(records, files).current()


def waiting_records(records: Iterable[Record], files: Iterable[EvidenceFile] = ()) -> list[Record]:
    """The agent's records waiting for the accountant to confirm or reject them."""
    return RecordState(records, files).waiting()


def current_version(
    record_id: str, records: Iterable[Record], files: Iterable[EvidenceFile] = ()
) -> Record | None:
    """Where a pointer to record_id leads now. See RecordState.current_version."""
    return RecordState(records, files).current_version(record_id)


# The write check.


def _referenced_records(new: Record) -> list[str]:
    data = new.data
    ids: list[str] = []
    if isinstance(data, Link):
        ids += [data.record_id, *([data.item_record_id] if data.item_record_id else [])]
    elif isinstance(data, BudgetAssignment):
        ids.append(data.record_id)
    elif isinstance(data, Judgment):
        ids += [*([data.record_id] if data.record_id else []), *data.rests_on]
    elif isinstance(data, ChecklistItem):
        if data.rate is not None and data.rate.rate_id is not None:
            ids.append(data.rate.rate_id)
    elif isinstance(data, ChecklistRemoval):
        if data.item_record_id is not None:
            ids.append(data.item_record_id)
    elif isinstance(data, AcceptedReason):
        ids += [
            *([data.record_id] if data.record_id else []),
            *([data.reuses_id] if data.reuses_id else []),
        ]
        ids += data.rests_on
    elif isinstance(data, Snooze):
        if data.record_id is not None:
            ids.append(data.record_id)
    elif isinstance(data, Confirmation):
        ids += data.record_ids
    return ids


def _referenced_files(new: Record) -> list[str]:
    data = new.data
    ids = [c.file_id for c in citations(data)]
    if isinstance(data, Judgment | AcceptedReason | Snooze) and data.file_id is not None:
        ids.append(data.file_id)
    if isinstance(data, Duplicate):
        ids += [data.copy_file_id, data.original_file_id]
    return ids


def _suggestion_key(new: Record, state: RecordState) -> tuple[str, ...] | None:
    """What makes two of the agent's suggestions "the same one", for the no-repeats rule."""
    data = new.data
    if new.replaces_id is not None:
        answer = data.answer.value if isinstance(data, Judgment) else ""
        return ("replace", new.replaces_id, new.kind.value, answer)
    if isinstance(data, ChecklistRemoval):
        return ("removal", data.charge_id, data.item_record_id or "", data.default_item or "")
    if isinstance(data, Dispute):
        return ("dispute", data.charge_id, data.check)
    if isinstance(data, Duplicate):
        return ("duplicate", *sorted((data.copy_file_id, data.original_file_id)))
    if isinstance(data, Link):
        bill = state.current_version(data.record_id)
        return ("link", bill.id if bill else data.record_id, data.charge_id)
    return None


def _files_of(record: Record) -> set[str]:
    return {c.file_id for c in citations(record.data)}


def check_new_record(
    new: Record,
    records: Sequence[Record],
    charges: Sequence[Charge],
    files: Sequence[EvidenceFile],
    *,
    default_items: DefaultItems,
) -> list[str]:
    """The problems with a record about to be written, as plain sentences.

    Empty means it can be saved.

    The backend runs this on every write, and the agent sees the problems so it
    can fix them. `records` is everything already written in the workspace, in
    order; `charges` and `files` are everything that has arrived. The citations
    in `new` have already been matched against their files by the server.
    `default_items` gives a charge's default checklist items (W2 provides it).
    """
    problems: list[str] = []
    state = RecordState(records, files)
    charges_by_id = {c.id: c for c in charges}
    data = new.data
    agent = new.author == Author.AGENT

    def pointable(record_id: str, what: str) -> Record | None:
        """A record a new record may point to: current, or new and waiting (a waiting term)."""
        r = state.by_id.get(record_id)
        if r is None:
            problems.append(f"{what} {record_id} doesn't exist")
            return None
        if r.grant_id != new.grant_id:
            problems.append(
                f"for now each grant is isolated, and {what} {record_id} is on another grant"
            )
            return None
        new_and_waiting = state.is_waiting(record_id) and r.replaces_id is None
        if not (state.is_current(record_id) or new_and_waiting):
            problems.append(
                f"{what} {record_id} isn't current: it was replaced, retracted or rejected"
            )
            return None
        return r

    def charge(charge_id: str) -> Charge | None:
        c = charges_by_id.get(charge_id)
        if c is None:
            problems.append(f"charge {charge_id} doesn't exist")
            return None
        if c.grant_id != new.grant_id:
            problems.append(
                f"for now each grant is isolated, and charge {charge_id} is on another grant"
            )
            return None
        return c

    if new.id in state.by_id:
        problems.append(f"the ID {new.id} is already used")

    # Every quoted value appears in its passage, and every citation was matched against its file.
    for path, value in cited_values(data):
        c = value.citation
        if c is not None and c.passage is not None and value.text and value.text not in c.passage:
            problems.append(f"the passage for '{path}' doesn't contain '{value.text}'")
    for c in citations(data):
        if c.match is None:
            problems.append(f"a citation in file {c.file_id} hasn't been matched against its file")
    for file_id in dict.fromkeys(_referenced_files(new)):
        f = state.files.get(file_id)
        if f is None:
            problems.append(f"file {file_id} doesn't exist")
        elif f.grant_id != new.grant_id:
            problems.append(
                f"for now each grant is isolated, and file {file_id} is on another grant"
            )

    # A replacement.
    if new.replaces_id is not None:
        old = state.by_id.get(new.replaces_id)
        if old is None:
            problems.append(f"the replaced record {new.replaces_id} doesn't exist")
        elif old.grant_id != new.grant_id:
            problems.append(
                f"for now each grant is isolated, and the replaced record {old.id} "
                "is on another grant"
            )
            old = None
        else:
            # The accountant may replace a waiting or rejected record of the agent's,
            # for example by typing the right value, so pointers follow their record.
            typed_fix = (
                not agent
                and old.author == Author.AGENT
                and not state.is_replaced(old.id)
                and (state.is_waiting(old.id) or state.decision(old.id) == Decision.REJECTED)
            )
            if not (state.is_current(old.id) or typed_fix):
                problems.append(
                    f"the replaced record {old.id} isn't current: "
                    "it was replaced, retracted or rejected, or it still waits"
                )
                old = None
        if old is not None:
            if new.kind not in (old.kind, RecordKind.RETRACTION):
                problems.append(f"a {new.kind} can't replace a {old.kind}")
            elif agent and old.author == Author.USER:
                allowed = {
                    RecordKind.LINK: (RecordKind.LINK, RecordKind.RETRACTION),
                    RecordKind.JUDGMENT: (RecordKind.JUDGMENT,),
                }
                if new.kind not in allowed.get(old.kind, ()):
                    problems.append(
                        "the agent can only suggest fixes to the accountant's links and answers"
                    )
            if isinstance(data, Judgment) and isinstance(old.data, Judgment):
                same = (data.question, data.charge_id, data.record_id, data.file_id)
                if same != (
                    old.data.question,
                    old.data.charge_id,
                    old.data.record_id,
                    old.data.file_id,
                ):
                    problems.append(
                        "a new answer replaces an answer to the same question about the same thing"
                    )

    # The charge it's about.
    the_charge = charge(new.charge_id) if new.charge_id is not None else None

    # Every record it points to exists, is current and is on its grant.
    pointed = {
        record_id: pointable(record_id, "record")
        for record_id in dict.fromkeys(_referenced_records(new))
        if not isinstance(data, Confirmation)
    }

    if isinstance(data, Link):
        fact = pointed.get(data.record_id)
        if fact is not None:
            if fact.kind not in FACT_KINDS:
                problems.append(f"a link points to a bill, approval or note, not a {fact.kind}")
            fact_files = _files_of(fact)
            if data.part is not None and fact_files and data.part.file_id not in fact_files:
                problems.append("the link's part has to be in the linked record's own file")
            copies = {
                r.data.copy_file_id
                for r in state.current()
                if isinstance(r.data, Duplicate) and state.decision(r.id) == Decision.CONFIRMED
            }
            if fact_files & copies:
                problems.append(
                    "the linked record is read from a copy the accountant confirmed as a duplicate"
                )
        item_amount: int | None = None
        if data.item_record_id is not None:
            item = pointed.get(data.item_record_id)
            if item is not None:
                if (
                    not isinstance(item.data, ChecklistItem)
                    or item.data.charge_id != data.charge_id
                ):
                    problems.append(f"record {item.id} isn't a checklist item on this charge")
                else:
                    item_amount = item.data.amount_cents
        elif data.default_item is not None and the_charge is not None:
            defaults = {d.key: d for d in default_items(the_charge, state.current())}
            if data.default_item not in defaults:
                problems.append(
                    f"'{data.default_item}' isn't one of this charge's default checklist items"
                )
            else:
                item_amount = defaults[data.default_item].amount_cents
        if data.amount_cents is not None and item_amount is None:
            problems.append(
                "a link carries an amount only when the checklist item it fills carries one"
            )
        if (
            data.amount_cents is None
            and item_amount is not None
            and fact is not None
            and fact.kind == RecordKind.BILL
        ):
            problems.append(
                "a link from a bill to an item that carries an amount says how much it uses"
            )

    elif isinstance(data, BudgetAssignment):
        line = pointed.get(data.record_id)
        if line is not None and line.kind != RecordKind.BUDGET_LINE:
            problems.append(f"a budget assignment points to a budget_line, not a {line.kind}")
        if any(
            isinstance(r.data, BudgetAssignment)
            and r.data.charge_id == data.charge_id
            and r.id != new.replaces_id
            for r in state.current()
        ):
            problems.append(
                "this charge already has a current budget assignment: replace it instead"
            )

    elif isinstance(data, Judgment):
        expected = {
            Question.COVERS: RecordKind.APPROVAL,
            Question.UNUSUAL_TERM: RecordKind.OTHER_TERM,
        }
        about = pointed.get(data.record_id) if data.record_id is not None else None
        want = expected.get(data.question)
        if about is not None and want is not None and about.kind != want:
            problems.append(f"a {data.question} question is about an {want}, not a {about.kind}")
        if agent and new.replaces_id is None and data.question != Question.FLAG:
            theirs = [
                r
                for r in state.current()
                if r.author == Author.USER
                and isinstance(r.data, Judgment)
                and (r.data.question, r.data.charge_id, r.data.record_id)
                == (data.question, data.charge_id, data.record_id)
            ]
            if theirs:
                problems.append(
                    f"the accountant answered this question in {theirs[-1].id}: "
                    "suggest a new answer that replaces it"
                )

    elif isinstance(data, ChecklistItem):
        if data.rate is not None and data.rate.rate_id is not None:
            rate = pointed.get(data.rate.rate_id)
            if rate is not None and rate.kind != RecordKind.RATE:
                problems.append(f"an item's rate_id points to a rate term, not a {rate.kind}")

    elif isinstance(data, ChecklistRemoval):
        if data.item_record_id is not None:
            item = pointed.get(data.item_record_id)
            if item is not None and (
                not isinstance(item.data, ChecklistItem) or item.data.charge_id != data.charge_id
            ):
                problems.append(f"record {item.id} isn't a checklist item on this charge")
        elif data.default_item is not None and the_charge is not None:
            keys = {d.key for d in default_items(the_charge, state.current())}
            if data.default_item not in keys:
                problems.append(
                    f"'{data.default_item}' isn't one of this charge's default checklist items"
                )

    elif isinstance(data, Confirmation):
        replaced_by_listed: dict[str, str] = {}
        for record_id in data.record_ids:
            target = state.by_id.get(record_id)
            if target is None:
                problems.append(f"record {record_id} doesn't exist")
                continue
            if target.grant_id != new.grant_id:
                problems.append(
                    f"for now each grant is isolated, and record {record_id} is on another grant"
                )
                continue
            if target.replaces_id is not None:
                other = replaced_by_listed.setdefault(target.replaces_id, record_id)
                if other != record_id:
                    problems.append(
                        f"records {other} and {record_id} replace the same record: "
                        "decide on one at a time"
                    )
            pending = (
                state.waits(record_id)
                and not state.is_replaced(record_id)
                and (target.replaces_id is None or state.is_current(target.replaces_id))
            )
            if not pending:
                if not state.unconfirmed_values(target):
                    problems.append(
                        f"record {record_id} doesn't wait for a confirmation "
                        "and has no unconfirmed value"
                    )
                elif data.decision == Decision.REJECTED:
                    problems.append(
                        f"record {record_id} only has a value nobody could confirm: "
                        "it can be confirmed, or corrected, but not rejected"
                    )
            if data.decision == Decision.CONFIRMED and state.decision(record_id) == (
                Decision.CONFIRMED
            ):
                problems.append(f"record {record_id} is already confirmed")
            elif (
                data.decision == Decision.CONFIRMED
                and target.replaces_id
                and not state.is_current(target.replaces_id)
            ):
                problems.append(f"record {record_id} replaces a record that's no longer current")

    elif isinstance(data, AcceptedReason) and data.reuses_id is not None:
        note = pointed.get(data.reuses_id)
        if note is not None and not (isinstance(note.data, AcceptedReason) and note.data.reusable):
            problems.append(f"record {data.reuses_id} isn't a reusable note")

    # No repeats: a suggestion the accountant rejected isn't raised again without new
    # evidence. It applies only to a record that would wait, and the window for new
    # evidence starts when the accountant rejected the earlier one.
    if agent and new.id not in state.by_id:
        key = _suggestion_key(new, state)
        would_wait = key is not None and RecordState([*state.records, new], files).waits(new.id)
        if key is not None and would_wait:
            for earlier in state.records:
                if (
                    earlier.author != Author.AGENT
                    or not state.waits(earlier.id)
                    or state.decision(earlier.id) != Decision.REJECTED
                    or _suggestion_key(earlier, state) != key
                ):
                    continue
                rejection = state.decided_by(earlier.id)
                if rejection is not None and not state.new_evidence_between(
                    rejection.written_at, new.written_at, new.grant_id
                ):
                    problems.append(
                        f"the accountant rejected the same suggestion ({earlier.id}), "
                        "and no new evidence has arrived since"
                    )
                    break

    return problems
