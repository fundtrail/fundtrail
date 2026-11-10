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
in the order they were stored. When every record has its `stored_seq`, they're
put in that order here; a record being checked, which isn't stored yet, comes
last. Whether one of the agent's records waits is decided from what was stored
before it. A record against a record uses stored order, never clock dates.
"""

from collections.abc import Collection, Iterable, Sequence
from datetime import datetime

from .buckets import Bucket
from .charges import Charge
from .evidence import EvidenceFile
from .mail import HeldMail, HoldReason
from .records import (
    FACT_KINDS,
    FOUND,
    OVER_LIMIT_CHECK,
    OVER_LIMIT_PROBLEM,
    TERM_KINDS,
    AcceptedReason,
    Answer,
    Approval,
    Author,
    Bill,
    BudgetAssignment,
    BudgetLine,
    ChecklistItem,
    ChecklistRemoval,
    Confirmation,
    Correction,
    Decision,
    DefaultItems,
    Dispute,
    Duplicate,
    Judgment,
    Link,
    MailAction,
    MailDecision,
    Note,
    Notice,
    Question,
    Record,
    RecordKind,
    Remainder,
    SignOff,
    Snooze,
    citations,
    cited_values,
)
from .runs import Trigger, TriggerKind

# Kinds of the agent's that always wait for the accountant.
_ALWAYS_WAIT = TERM_KINDS | {
    RecordKind.CHECKLIST_REMOVAL,
    RecordKind.DISPUTE,
    RecordKind.DUPLICATE,
    RecordKind.CORRECTION,
    RecordKind.REMAINDER,
}

# How strong a concern an answer raises. Moving down this order clears or weakens a problem.
_CONCERN = {Answer.SUPPORTS: 0, Answer.UNSURE: 1, Answer.CONTRADICTS: 2}


class RecordState:
    """The records and files visible at one moment, with what counts worked out.

    Build it once and ask it many questions. The module's functions wrap it.
    """

    def __init__(self, records: Iterable[Record], files: Iterable[EvidenceFile] = ()):
        self.records: list[Record] = list(records)
        # Records not stored yet come last, in order: the record being checked, or a
        # run's staged records after the stored ones. They come after everything
        # stored. Stored records all carry their order, ahead of that tail; a stored
        # record without one would let a missing order clear a problem. When no record
        # carries an order (test data), only the last counts as not stored yet.
        numbered = [r for r in self.records if r.stored_seq is not None]
        tail = self.records[len(numbered) :]
        if any(r.stored_seq is not None for r in tail) or any(
            r.stored_seq is None for r in self.records[: len(numbered)]
        ):
            raise ValueError(
                "stored records carry their stored_seq, ahead of the records not stored yet"
            )
        if numbered:
            self.records = sorted(numbered, key=lambda r: r.stored_seq or 0) + tail
            self._unstored_ids: set[str] = {r.id for r in tail}
        else:
            self._unstored_ids = {self.records[-1].id} if self.records else set()
        self.files: dict[str, EvidenceFile] = {f.id: f for f in files}
        self.by_id: dict[str, Record] = {}
        self._pos: dict[str, int] = {}
        self._replacers: dict[str, list[str]] = {}
        self._confirmations_of: dict[str, list[str]] = {}
        self._links_of: dict[str, list[str]] = {}  # by charge
        self._answers_of: dict[tuple[str, str | None, str | None], list[str]] = {}
        self._waits: dict[str, bool] = {}
        self._effective_memo: dict[tuple[str, int], bool] = {}
        self._thread_records: list[str] = []  # the agent's records written in thread runs
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
            if r.author == Author.AGENT and r.thread_message_id is not None:
                self._thread_records.append(r.id)
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

    def answers_of(self, answer: Judgment) -> list[str]:
        """The IDs of the answers to the same question about the same things, in order."""
        return self._answers_of.get(_answer_key(answer), [])

    def _is_checking(self, record: Record) -> bool:
        """Whether `record` is the record being checked: not stored yet, so after everything."""
        return record.stored_seq is None and (
            record.id in self._unstored_ids or record.id not in self._pos
        )

    def suggestion_key(self, record: Record, i: int | None = None) -> tuple[str, ...] | None:
        """What makes two of the agent's records "the same one", for the no-repeats rule and
        for a thread run's record written again by another run. As of position `i`."""
        at = self._end if i is None else i
        data = record.data
        if record.replaces_id is not None:
            answer = data.answer.value if isinstance(data, Judgment) else ""
            return ("replace", record.replaces_id, record.kind.value, answer)
        if isinstance(data, Judgment) and data.question == Question.FLAG:
            return ("flag", data.charge_id or "", data.record_id or "", data.file_id or "")
        if isinstance(data, Judgment):
            # An answer beside the agent's own is a new answer over it.
            for old_id in reversed(self._answers_of.get(_answer_key(data), [])):
                old = self.by_id[old_id]
                if (
                    old.author == Author.AGENT
                    and old_id != record.id
                    and self._current_at(old_id, at)
                ):
                    return ("replace", old_id, record.kind.value, data.answer.value)
            question, charge_id, about = _answer_key(data)
            return ("answer", question, charge_id or "", about or "", data.answer.value)
        if isinstance(data, BudgetAssignment):
            line = self._current_version_at(data.record_id, at)
            return ("budget_assignment", data.charge_id, line.id if line else data.record_id)
        if isinstance(data, Bill):
            number = data.document_number.value if data.document_number else ""
            return ("bill", _first_file(record), str(data.total.value), number)
        if isinstance(data, Approval):
            return ("approval", _first_file(record), data.approver_email.value, data.covers.value)
        if isinstance(data, Note):
            return ("note", _first_file(record), data.label, data.statement.value)
        if isinstance(data, ChecklistItem):
            return ("checklist_item", data.charge_id, " ".join(data.needed.split()).casefold())
        if isinstance(data, ChecklistRemoval):
            return ("removal", data.charge_id, data.item_record_id or "", data.default_item or "")
        if isinstance(data, Dispute):
            return ("dispute", data.charge_id, data.check)
        if isinstance(data, Duplicate):
            return ("duplicate", *sorted((data.copy_file_id, data.original_file_id)))
        if isinstance(data, Correction):
            return ("correction", data.charge_id, data.corrects_line_id)
        if isinstance(data, Remainder):
            return ("remainder", data.record_id)
        if isinstance(data, Link):
            bill = self._current_version_at(data.record_id, at)
            return ("link", bill.id if bill else data.record_id, data.charge_id)
        return None

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

    def new_evidence_since(self, since: Record, new: Record, *, before: int | None = None) -> bool:
        """Whether new evidence arrived on `new`'s grant after `since` and before `new`.

        New evidence is (decision call 36, issue 70):
        - a file that arrived later than `since` was written, or at the same time and
          stored after it (the demo clock stands still between moves, so ties are
          common), and not later than `new`;
        - a grant term the accountant typed, or confirmed for the first time, stored
          after `since` and before `new`: stored order only, never clock dates.
        Something the agent links later from what was already on file doesn't count.
        `new` may be the record being checked, not stored yet, which comes after
        everything stored. A missing order otherwise never counts as new.
        When `new` is the agent's record and carries its run's read point (call 40),
        only what was stored up to that point counts: anything stored during the
        run isn't new for that run's answers. And when `since` is the agent's earlier
        answer with its own run's read point, the window runs from that read point to
        this one: new evidence is what the earlier run didn't read and this one did,
        wherever the earlier answer was stored (the main coordinator's ruling on N3).
        What a run read is `read_by_run`: stored at or below its read point, and
        arrived or written by its clock.
        `before` limits it to the records stored before that position.
        """
        read_point = new.read_through_seq if new.author == Author.AGENT else None
        lower = (
            since.read_through_seq
            if read_point is not None and since.author == Author.AGENT
            else None
        )

        def read_by_new(item: Record | EvidenceFile) -> bool:
            return read_point is not None and read_by_run(
                item, read_through_seq=read_point, clock_now=new.written_at
            )

        def read_by_since(item: Record | EvidenceFile) -> bool:
            return lower is not None and read_by_run(
                item, read_through_seq=lower, clock_now=since.written_at
            )

        for f in self.files.values():
            if f.grant_id != new.grant_id:
                continue
            if read_point is not None:
                if not read_by_new(f):
                    continue  # this run didn't read it
                if lower is not None:
                    if not read_by_since(f):
                        return True  # this run read it and the earlier run didn't
                    continue
            after_since = f.arrived_at > since.written_at or (
                f.arrived_at == since.written_at and _stored_after(f.stored_seq, since.stored_seq)
            )
            if read_point is not None:
                before_new = True  # read by this run, checked above
            else:
                before_new = f.arrived_at < new.written_at or (
                    f.arrived_at == new.written_at
                    and (self._is_checking(new) or _stored_after(new.stored_seq, f.stored_seq))
                )
            if after_since and before_new:
                return True
        start = self._pos[since.id] + 1 if since.id in self._pos else 0
        if lower is not None:
            start = 0  # the window is what the runs read, not where `since` was stored
        stop = self._pos[new.id] if new.id in self._pos else len(self.records)
        if before is not None:
            stop = min(stop, before)
        for r in self.records[start:stop]:
            if r.grant_id != new.grant_id or r.author != Author.USER:
                continue
            if read_point is not None and not read_by_new(r):
                continue  # this run didn't read it: stored during the run, or written later
            if read_by_since(r):
                continue  # the earlier run had read it
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
        if r.thread_message_id is not None:
            return True  # written in a run a thread message started
        if r.kind in _ALWAYS_WAIT:
            return True
        if self._repeats_a_waiting_thread_record(r, i):
            return True  # the same as a thread run's record that still waits
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

    def _repeats_a_waiting_thread_record(self, r: Record, i: int) -> bool:
        key = self.suggestion_key(r, i)
        if key is None:
            return False
        for tid in self._thread_records:
            if self._pos[tid] >= i or not self._waits[tid]:
                continue
            if self._decision_at(tid, i) is not None or self._replaced_at(tid, i):
                continue
            if self.suggestion_key(self.by_id[tid], i) == key:
                return True
        return False

    def _new_answer_waits(
        self, old: Record, before: Answer, new: Record, after: Answer, i: int
    ) -> bool:
        if _CONCERN[after] >= _CONCERN[before]:
            return False  # the same answer refreshed, or a change toward a concern
        if before == Answer.CONTRADICTS:
            return True  # contradicts turning into anything milder
        # unsure turning into supports counts right away only once new evidence has arrived
        return not self.new_evidence_since(old, new, before=i)

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


def run_read_point(*stored: Iterable[Record | Charge | EvidenceFile]) -> int:
    """A run's read point (call 40): the highest stored order among what it was given.

    The platform (W4) calls it with the records, charges and files it hands the run
    when the run starts, and stores the result as AgentRun.read_through_seq.
    """
    return max((item.stored_seq or 0 for items in stored for item in items), default=0)


def read_by_run(
    item: Record | Charge | EvidenceFile, *, read_through_seq: int, clock_now: datetime
) -> bool:
    """Whether a run read an item: stored at or below the run's read point, and arrived (a
    file or a charge) or written (a record) by the run's clock. A file stored at a reset
    with a future arrival date isn't read until it arrives."""
    if item.stored_seq is None or item.stored_seq > read_through_seq:
        return False
    when = item.written_at if isinstance(item, Record) else item.arrived_at
    return when <= clock_now


def _stored_after(a: int | None, b: int | None) -> bool:
    """Whether `a` was stored after `b`. Unknown order isn't "after"."""
    return a is not None and b is not None and a > b


def _first_file(record: Record) -> str:
    return next((c.file_id for c in citations(record.data)), "")


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
    elif isinstance(data, Remainder):
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
    if isinstance(data, BudgetLine) and data.notice_file_id is not None:
        ids.append(data.notice_file_id)
    return ids


def _suggestion_key(new: Record, state: RecordState) -> tuple[str, ...] | None:
    return state.suggestion_key(new)


def _files_of(record: Record) -> set[str]:
    return {c.file_id for c in citations(record.data)}


def check_new_record(
    new: Record,
    records: Sequence[Record],
    charges: Sequence[Charge],
    files: Sequence[EvidenceFile],
    *,
    default_items: DefaultItems,
    held_mail: Sequence[HeldMail] = (),
    trigger: Trigger | None,
) -> list[str]:
    """The problems with a record about to be written, as plain sentences.

    Empty means it can be saved.

    The backend runs this on every write, and the agent sees the problems so it
    can fix them. `records` is everything already written in the workspace, in
    order; `charges` and `files` are everything that has arrived. The citations
    in `new` have already been matched against their files by the server.
    `default_items` gives a charge's default checklist items (W2 provides it), and
    `held_mail` is the mail held on the workspace's grants, for a `mail_action`.
    `trigger` is the trigger of the agent run writing the record, or None for the
    accountant's write. It's required, so leaving it out can't turn the rule off:
    in a run a thread message started, the agent's record names that message.
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
    if new.stored_seq is not None:
        problems.append("a new record gets its stored order when it's saved, not before")
    if agent and new.read_through_seq is None:
        problems.append("the agent's record carries the read point of the run writing it")

    # The agent writes inside a run, so its record comes with the run's trigger; the
    # accountant's doesn't.
    if agent and trigger is None:
        problems.append("the agent's record needs the trigger of the run writing it")
    if not agent and trigger is not None:
        problems.append("the accountant's record isn't written by an agent run")

    # A run a thread message started: every record the agent writes in it waits.
    in_thread = trigger is not None and trigger.kind == TriggerKind.THREAD_MESSAGE
    if agent and in_thread and trigger is not None and new.thread_message_id != trigger.id:
        problems.append(
            f"this run was started by thread message {trigger.id}: the record names it, "
            "so it waits for the accountant"
        )
    elif new.thread_message_id is not None and not in_thread:
        problems.append("only a record written in a run a thread message started names one")

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
            # The accountant may replace a new record of the agent's that waits or was
            # rejected, such as a term, for example by typing the right value, so
            # pointers follow it. To fix one of the agent's suggested replacements,
            # the accountant replaces its target instead.
            typed_fix = (
                not agent
                and old.author == Author.AGENT
                and old.replaces_id is None
                and not state.is_replaced(old.id)
                and (state.is_waiting(old.id) or state.decision(old.id) == Decision.REJECTED)
            )
            if (
                new.kind == RecordKind.RETRACTION
                and old.author == Author.AGENT
                and (state.is_waiting(old.id))
            ):
                problems.append(
                    f"record {old.id} waits for the accountant: reject it instead of retracting it"
                )
                old = None
            elif not (state.is_current(old.id) or typed_fix):
                problems.append(
                    f"the replaced record {old.id} isn't current: "
                    "it was replaced, retracted or rejected, or it still waits"
                )
                old = None
        if old is not None and isinstance(old.data, MailDecision):
            if old.data.action == MailAction.LET_IN:
                problems.append(
                    f"held mail {old.data.held_mail_id} was let in and its files have arrived: "
                    "the decision stands"
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

    elif isinstance(data, BudgetLine) and data.notice_file_id is not None:
        # The agent's line belongs to the notice it was read from; naming another
        # would move it to that notice's group. The accountant may name any file.
        if agent and data.notice_file_id not in {c.file_id for c in citations(data)}:
            problems.append(
                f"the agent's budget line belongs to the notice it cites, "
                f"not file {data.notice_file_id}"
            )

    elif isinstance(data, Remainder):
        bill = pointed.get(data.record_id)
        if bill is not None and bill.kind != RecordKind.BILL:
            problems.append(f"the rest belongs to another award on a bill, not on a {bill.kind}")

    elif isinstance(data, Correction):
        if the_charge is not None and data.corrects_line_id == the_charge.ledger_line_id:
            problems.append("a line can't correct itself")
        if the_charge is not None and the_charge.original_line_id is not None:
            named_on_grant = any(
                c.ledger_line_id == the_charge.original_line_id and c.grant_id == new.grant_id
                for c in charges
            )
            if named_on_grant and data.corrects_line_id != the_charge.original_line_id:
                problems.append(
                    f"the ledger says this line corrects {the_charge.original_line_id}, "
                    "which is on this grant"
                )
        if any(
            isinstance(r.data, Correction)
            and r.data.charge_id == data.charge_id
            and r.id != new.replaces_id
            for r in state.current()
        ):
            problems.append("this charge already has a current correction: replace it instead")

    elif isinstance(data, MailDecision):
        held = next((m for m in held_mail if m.id == data.held_mail_id), None)
        if held is None:
            problems.append(f"held mail {data.held_mail_id} doesn't exist")
        elif held.grant_id != new.grant_id:
            problems.append(
                f"for now each grant is isolated, and held mail {held.id} is on another grant"
            )
        if any(
            isinstance(r.data, MailDecision)
            and r.data.held_mail_id == data.held_mail_id
            and r.id != new.replaces_id
            for r in state.current()
        ):
            problems.append("this message already has a current decision: replace it instead")

    elif isinstance(data, SignOff):
        open_items = list(data.snapshot.problem_rows) + [
            c.charge_id
            for c in data.snapshot.charges
            if not (c.bucket == Bucket.EVIDENCE_COMPLETE or c.accepted or c.reversed)
        ]
        if open_items and not (data.note or "").strip():
            problems.append(
                "signing off with anything still open needs a note saying why "
                f"({len(open_items)} open)"
            )

    if isinstance(data, AcceptedReason) and data.amount_cents is not None:
        over_limit = (
            data.reason.check == OVER_LIMIT_CHECK
            and data.reason.problem == OVER_LIMIT_PROBLEM
            and data.charge_id is None
            and data.record_id is None
            and data.file_id is None
        )
        if not over_limit:
            problems.append(
                "an accepted reason carries an amount only for the award limit's over_limit "
                "problem, on the grant"
            )

    if isinstance(data, AcceptedReason) and data.reuses_id is not None:
        note = pointed.get(data.reuses_id)
        if note is not None and not (isinstance(note.data, AcceptedReason) and note.data.reusable):
            problems.append(f"record {data.reuses_id} isn't a reusable note")

    # No repeats: a suggestion the accountant rejected isn't raised again without new
    # evidence. It applies to a record that would wait, and to any record that repeats
    # a rejected record of a thread run (which waited because of its run, whatever its
    # kind). The window for new evidence starts when the accountant rejected it.
    if agent and new.id not in state.by_id:
        key = _suggestion_key(new, state)
        would_wait = key is not None and RecordState([*state.records, new], files).waits(new.id)
        if key is not None:
            for earlier in state.records:
                if (
                    earlier.author != Author.AGENT
                    or not state.waits(earlier.id)
                    or state.decision(earlier.id) != Decision.REJECTED
                    or _suggestion_key(earlier, state) != key
                ):
                    continue
                if not would_wait and earlier.thread_message_id is None:
                    continue
                rejection = state.decided_by(earlier.id)
                if rejection is not None and not state.new_evidence_since(rejection, new):
                    problems.append(
                        f"the accountant rejected the same suggestion ({earlier.id}), "
                        "and no new evidence has arrived since"
                    )
                    break

    return problems


def still_held(held: HeldMail, state: RecordState, known_senders: Collection[str]) -> bool:
    """Whether a message is still held (decision 0025).

    Held until the accountant lets it in or dismisses it (a current `mail_action`), or,
    for an unknown sender, until the sender becomes known: a confirmed person term, one
    the accountant added, or the address of one of the workspace's members who can act,
    given in `known_senders` in lower case. Mail held because a known address
    couldn't be verified stays held until the accountant decides.
    """
    decided = any(
        isinstance(r.data, MailDecision) and r.data.held_mail_id == held.id for r in state.current()
    )
    if decided:
        return False
    if held.reason == HoldReason.UNKNOWN_SENDER and held.sender is not None:
        return held.sender.lower() not in {s.lower() for s in known_senders}
    return True


def award_number_and_title(state: RecordState) -> tuple[str | None, str | None]:
    """The grant's award number and title, from the notices that count (issue 118).

    Read from the current `notice` records, so the agent's count once the accountant
    confirms them. The latest notice by its own date that prints a value wins; on the
    same date, the one stored later. None while no notice that counts prints it.
    """
    notices = [
        (r.data.dated.value, i, r.data)
        for i, r in enumerate(state.records)
        if isinstance(r.data, Notice) and state.is_current(r.id)
    ]
    notices.sort(key=lambda n: (n[0], n[1]), reverse=True)
    number = next((n.award_number.value for _, _, n in notices if n.award_number), None)
    title = next((n.title.value for _, _, n in notices if n.title), None)
    return number, title
