"""Builds the screen bodies from one grant as it stands at the workspace's "now".

The server works out everything nothing stores, through the contract functions
(`RecordState`) and the checks' output, and writes the wording. Nothing here writes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

from app.checks import budget_figures, note_limit
from app.checks.benefits import waiting_on
from app.checks.history import history_line
from app.contracts.api import (
    AnswerView,
    BudgetLineView,
    BudgetView,
    ChargeDetail,
    ChargeProblemRow,
    CloseoutDate,
    DuplicateView,
    EvidenceCard,
    FactLink,
    FactView,
    GrantDetail,
    GrantProblem,
    GrantProblemRow,
    GrantSummary,
    HeldMailRow,
    HistoryEntry,
    LinkView,
    MessageThreadEntry,
    ProblemRow,
    RecordProblemRow,
    RecordThreadEntry,
    ReusableNoteView,
    SignOffState,
    StatusThreadEntry,
    SuggestionView,
    TermsWaitingRow,
    TermView,
    Thread,
    ThreadEntry,
    ValueHow,
    ValueState,
    problem_row_key,
)
from app.contracts.api import RecordState as RecordStateName
from app.contracts.charges import Charge
from app.contracts.checks import (
    SEVERITY,
    Bucket,
    ChargeStatus,
    ChecksInput,
    ChecksOutput,
    GrantStatus,
    Problem,
    RecordStatus,
    StatusEntry,
    ready_for_closeout,
    snapshot_of,
)
from app.contracts.evidence import EvidenceFile
from app.contracts.mail import HeldMail
from app.contracts.records import (
    FOUND,
    TERM_KINDS,
    AcceptedReason,
    Author,
    BudgetAssignment,
    Confirmation,
    Decision,
    Duplicate,
    Judgment,
    Link,
    Record,
    RecordKind,
    Retraction,
    SignOff,
    citations,
    cited_values,
)
from app.contracts.rules import RecordState
from app.contracts.runs import AgentRun, RunStatus, Trigger, TriggerKind, batch_for
from app.contracts.signoff import SignOffSnapshot, changes_since
from app.contracts.signoff import sign_off_state as signed_state
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant, Workspace
from app.db import store, terms
from app.db.clock import grant_now
from app.db.held_mail import still_held_mail
from app.db.platform import Platform
from app.db.store import Conn, Status, StatusRow

# The buckets on the problem list, most serious first (answer 1).
_LIST_ORDER = [b for b in SEVERITY if b != Bucket.EVIDENCE_COMPLETE]


@dataclass
class GrantSnapshot:
    workspace: Workspace
    grant: Grant
    now: datetime
    charges: list[Charge]
    files: list[EvidenceFile]
    records: list[Record]
    statuses: dict[tuple[str, str | None], Status]
    pending: list[AgentRun]
    messages: list[ThreadMessage]
    output: ChecksOutput
    held: list[HeldMail]  # the grant's messages still held at "now" (rules.still_held)
    state: RecordState = field(init=False)

    def __post_init__(self) -> None:
        self.state = RecordState(self.records, self.files)
        self.charges_by_id = {c.id: c for c in self.charges}
        self.files_by_id = {f.id: f for f in self.files}

    def charge_status(self, charge_id: str) -> ChargeStatus | None:
        return cast(ChargeStatus | None, self.statuses.get(("charge", charge_id)))

    def record_status(self, record_id: str) -> RecordStatus | None:
        return cast(RecordStatus | None, self.statuses.get(("record", record_id)))

    def file_status(self, file_id: str) -> RecordStatus | None:
        return cast(RecordStatus | None, self.statuses.get(("file", file_id)))


def load_snapshot(p: Platform, conn: Conn, grant: Grant) -> GrantSnapshot:
    workspace = store.workspace_by_id(conn, grant.workspace_id)
    now = grant_now(conn, grant.id)
    charges = store.list_charges(conn, grant.id, now)
    files = store.list_files(conn, grant.id, now)
    records = store.list_records(conn, grant.id, now)
    output = p.checks.run_checks(
        ChecksInput(
            now=now,
            charges=tuple(charges),
            files=tuple(files),
            records=tuple(records),
            failed_runs=tuple(store.failed_runs(conn, grant.id)),
            skipped_files=tuple(store.list_skipped(conn, grant.id, now)),
        )
    )
    return GrantSnapshot(
        workspace=workspace,
        grant=grant,
        now=now,
        charges=charges,
        files=files,
        records=records,
        statuses=store.current_statuses(conn, grant.id),
        pending=store.pending_runs(conn, grant.id),
        messages=store.grant_messages(conn, grant.id, now),
        output=output,
        held=still_held_mail(conn, grant, now, RecordState(records, files)),
    )


# Records.


def record_state(state: RecordState, record: Record) -> RecordStateName:
    if state.is_waiting(record.id):
        return RecordStateName.WAITING
    if state.is_current(record.id):
        return RecordStateName.COUNTS
    if state.decision(record.id) == Decision.REJECTED:
        return RecordStateName.REJECTED
    retracted = any(
        isinstance(r.data, Retraction) and r.replaces_id == record.id and state.is_effective(r.id)
        for r in state.records
    )
    return RecordStateName.RETRACTED if retracted else RecordStateName.REPLACED


def value_states(state: RecordState, record: Record) -> list[ValueState]:
    unconfirmed = set(state.unconfirmed_values(record))
    decided = state.decided_by(record.id)
    out: list[ValueState] = []
    for path, value in cited_values(record.data):
        if path in unconfirmed:
            out.append(ValueState(path=path, confirmed=False))
        elif value.citation is None:
            out.append(
                ValueState(
                    path=path, confirmed=True, how=ValueHow.TYPED, confirmed_at=record.written_at
                )
            )
        elif value.citation.match in FOUND:
            out.append(ValueState(path=path, confirmed=True, how=ValueHow.FOUND))
        else:
            at = decided.written_at if decided else None
            out.append(
                ValueState(
                    path=path, confirmed=True, how=ValueHow.RECORD_CONFIRMED, confirmed_at=at
                )
            )
    return out


def _link_view(snap: GrantSnapshot, link: Record) -> LinkView | None:
    """A link with the record it points to now, after corrections. None when that record no
    longer counts (retracted, or rejected with nothing in its place)."""
    assert isinstance(link.data, Link)
    target = snap.state.current_version(link.data.record_id)
    if target is None:
        return None
    part_file = link.data.part.file_id if link.data.part else None
    file_id = part_file or next((c.file_id for c in citations(target.data)), None)
    return LinkView(
        link=link,
        record=target,
        values=tuple(value_states(snap.state, target)),
        file=snap.files_by_id.get(file_id) if file_id else None,
    )


def _touched_charges(snap: GrantSnapshot, record: Record) -> list[str]:
    ids = [record.charge_id]
    if record.replaces_id and (old := snap.state.by_id.get(record.replaces_id)):
        ids.append(old.charge_id)
    if isinstance(record.data, Duplicate):
        copy = record.data.copy_file_id
        for r in snap.state.current():
            if isinstance(r.data, Link):
                target = snap.state.by_id.get(r.data.record_id)
                if target and any(c.file_id == copy for c in citations(target.data)):
                    ids.append(r.data.charge_id)
    return sorted({i for i in ids if i})


def _suggestion(snap: GrantSnapshot, record: Record) -> SuggestionView:
    replaces = snap.state.by_id.get(record.replaces_id) if record.replaces_id else None
    return SuggestionView(
        record=record, replaces=replaces, charge_ids=tuple(_touched_charges(snap, record))
    )


# The grant.


def summary(snap: GrantSnapshot) -> GrantSummary:
    end = terms.end_date(snap.state, snap.grant.id)
    counts = dict.fromkeys(Bucket, 0)
    ready = 0
    for c in snap.charges:
        status = snap.charge_status(c.id)
        if status is None:
            continue
        counts[status.bucket] += 1
        if ready_for_closeout(status):  # Evidence complete, accepted or fully reversed
            ready += 1
    step = terms.next_closeout(end, snap.now.date())
    return GrantSummary(
        grant=snap.grant,
        end_date=end,
        charges_ready=ready,
        charges_total=len(snap.charges),
        on_problem_list=len(problem_rows(snap)),
        waiting=sum(1 for r in snap.state.waiting() if r.author == Author.AGENT),
        bucket_counts=counts,
        next_closeout=CloseoutDate(date=step.date, label=step.label) if step else None,
        now=snap.now,
    )


def _waiting_terms_by_file(snap: GrantSnapshot) -> dict[str, list[Record]]:
    groups: dict[str, list[Record]] = {}
    for r in snap.state.waiting():
        if r.kind in TERM_KINDS:
            file_id = next((c.file_id for c in citations(r.data)), None)
            if file_id in snap.files_by_id:
                groups.setdefault(file_id, []).append(r)  # pyright: ignore[reportArgumentType]
    return groups


# The checks' own problem on a term that waits for the accountant (check "terms",
# problem "waiting"). It's what the waiting-terms row stands for, so it isn't a flag.
WAITING_TERM_PROBLEM = ("terms", "waiting")


def _own_problems(snap: GrantSnapshot, record_id: str) -> list[Problem]:
    """A record's problems beyond waiting to be confirmed."""
    status = snap.record_status(record_id)
    if status is None or not status.flagged:
        return []
    return [p for p in status.problems if (p.check, p.problem) != WAITING_TERM_PROBLEM]


def problem_rows(snap: GrantSnapshot) -> list[ProblemRow]:
    """Grant problems first, then records and files, then charges by bucket, oldest first.

    A waiting term stays on its document's waiting-terms row even when it has a problem of
    its own; the row's text counts those ("8 terms waiting, 1 flagged"), and the terms page
    shows each one beside the term. Once confirmed, a term's problem is its own row.
    """
    rows: list[ProblemRow] = []
    grant_status = snap.statuses.get(("grant", None))
    if isinstance(grant_status, GrantStatus) and grant_status.flagged:
        for problem in grant_status.problems:
            rows.append(
                GrantProblemRow(
                    problem=GrantProblem(
                        **problem.model_dump(),
                        flagged=True,
                        accepted=grant_status.accepted,
                        snoozed=grant_status.snoozed,
                    )
                )
            )
    waiting = _waiting_terms_by_file(snap)
    in_groups = {r.id for group in waiting.values() for r in group}
    records: list[tuple[datetime, ProblemRow]] = []
    for file_id, group in waiting.items():
        f = snap.files_by_id[file_id]
        n = len(group)
        flagged = sum(1 for r in group if _own_problems(snap, r.id))
        text = f"{n} term{'s' if n != 1 else ''} waiting to be confirmed"
        if flagged:
            text = f"{n} term{'s' if n != 1 else ''} waiting, {flagged} flagged"
        records.append(
            (
                f.arrived_at,
                TermsWaitingRow(file=f, record_ids=tuple(r.id for r in group), text=text),
            )
        )
    for key, status in snap.statuses.items():
        if not isinstance(status, RecordStatus) or not status.flagged:
            continue
        if key[0] == "record" and key[1] in in_groups:
            continue  # shown on its document's waiting-terms row
        record = snap.state.by_id.get(status.record_id) if status.record_id else None
        f = snap.files_by_id.get(status.file_id) if status.file_id else None
        if record is None and f is None:
            continue  # not visible at "now"
        at = record.written_at if record else f.arrived_at  # pyright: ignore[reportOptionalMemberAccess]
        records.append((at, RecordProblemRow(status=status, record=record, file=f)))
    records += [(h.held_at, HeldMailRow(held=h)) for h in snap.held]
    rows += [row for _, row in sorted(records, key=lambda x: x[0])]
    # A charge whose only failing reasons are Needs a human reasons pointing at terms that
    # have their own rows (a term code can't place, or one waiting) isn't a row of its own:
    # the term's row stands for it (checks-rulings 3). Any other reason keeps its row.
    term_rows = in_groups | {
        key[1]
        for key, status in snap.statuses.items()
        if key[0] == "record"
        and isinstance(status, RecordStatus)
        and status.flagged
        and (r := snap.state.by_id.get(key[1] or "")) is not None
        and r.kind in TERM_KINDS
    }
    charges = [
        (c, s)
        for c in snap.charges
        if (s := snap.charge_status(c.id)) is not None
        and s.flagged
        and s.bucket in _LIST_ORDER
        and not _covered_by_terms(s, term_rows)
    ]
    # Ruling 62: a benefit charge whose only open problem is waiting on its salary lines
    # shows with a salary line's row. The checks give such a charge Missing evidence,
    # unflagged, so it has no row of its own; the filter only guards against one.
    statuses = [st for c in snap.charges if (st := snap.charge_status(c.id)) is not None]
    on_list = {c.id for c, _ in charges}
    benefits_waiting = {k: v for k, v in waiting_on(statuses).items() if k in on_list}
    shown_with = {b for v in benefits_waiting.values() for b in v}
    charges = [(c, s) for c, s in charges if c.id not in shown_with]
    charges.sort(
        key=lambda cs: (_LIST_ORDER.index(cs[1].bucket), cs[0].posting_date, cs[0].ledger_line_id)
    )
    rows += [
        ChargeProblemRow(charge=c, status=s, waiting_charge_ids=benefits_waiting.get(c.id, ()))
        for c, s in charges
    ]
    return rows


def _covered_by_terms(status: ChargeStatus, term_rows: set[str | None]) -> bool:
    failing = [r for r in status.reasons if r.bucket != Bucket.EVIDENCE_COMPLETE]
    return bool(failing) and all(
        r.bucket == Bucket.NEEDS_HUMAN and r.record_ids and set(r.record_ids) <= term_rows
        for r in failing
    )


def term_views(snap: GrantSnapshot) -> list[TermView]:
    """Waiting first, then in force, each with what it replaced (answer 5)."""
    out: list[TermView] = []
    for want in ("waiting", "counts"):
        for r in snap.records:
            if r.kind not in TERM_KINDS or record_state(snap.state, r) != want:
                continue
            out.append(
                TermView(
                    record=r,
                    state=RecordStateName(want),
                    decision=snap.state.decided_by(r.id),
                    status=snap.record_status(r.id),
                    replaces=snap.state.by_id.get(r.replaces_id) if r.replaces_id else None,
                    values=tuple(value_states(snap.state, r)),
                )
            )
    return out


def budget(snap: GrantSnapshot) -> BudgetView:
    """The budget figures from the checks' public budget_figures (issue 106), the same ones
    the grant notes come from: one row per NSF category, its amount added up per notice,
    its spending counting its sub-lines. Each row shows the category's latest budget_line
    term in force."""
    figures = budget_figures(snap.grant.id, snap.records, snap.charges)
    return BudgetView(
        lines=tuple(
            BudgetLineView(
                line=snap.state.by_id[f.record_ids[-1]],
                amount_cents=f.budget_cents,
                spent_cents=f.spent_cents,
            )
            for f in figures.categories
        ),
        limit_cents=figures.limit_cents,
        spent_cents=figures.spent_cents,
    )


def snapshot_now(snap: GrantSnapshot) -> SignOffSnapshot:
    statuses = [st for c in snap.charges if (st := snap.charge_status(c.id)) is not None]
    return snapshot_of(statuses, snap.charges, (problem_row_key(r) for r in problem_rows(snap)))


def sign_off_view(snap: GrantSnapshot) -> SignOffState:
    """Decision 0022: not signed, signed, or changed since, comparing the snapshot the
    sign-off stored with one taken now (each charge's bucket, accepted and reversed state,
    the problem list row by row, and the totals)."""
    signed = [r for r in snap.state.current() if isinstance(r.data, SignOff)]
    if not signed:
        return SignOffState(state=signed_state(None, snapshot_now(snap)))
    sign_off = signed[-1]
    assert isinstance(sign_off.data, SignOff)
    now = snapshot_now(snap)
    return SignOffState(
        state=signed_state(sign_off.data.snapshot, now),
        sign_off=sign_off,
        changes=changes_since(sign_off.data.snapshot, now),
    )


def reusable_notes(snap: GrantSnapshot) -> list[ReusableNoteView]:
    """Each reusable note: what it excuses, who wrote it and when (its record), and every
    charge it covers now. Code does the matching (the checks mark a reason accepted_by the
    note, or by an accepted offer that reuses it); nothing stores it per charge."""
    notes = [
        r
        for r in snap.state.current()
        if isinstance(r.data, AcceptedReason) and r.data.reusable and r.data.charge_id
    ]
    out: list[ReusableNoteView] = []
    for note in notes:
        assert isinstance(note.data, AcceptedReason)
        written_on = snap.charges_by_id.get(note.data.charge_id or "")
        if written_on is None:
            continue
        under = {note.id} | {
            r.id
            for r in snap.state.current()
            if isinstance(r.data, AcceptedReason) and r.data.reuses_id == note.id
        }
        covered = [
            c
            for c in snap.charges
            if c.id != written_on.id
            and (st := snap.charge_status(c.id)) is not None
            and any(reason.accepted_by in under for reason in st.reasons)
        ]
        # The checks' own rule (issue 106): the note's charge, raised by acceptances of
        # the offer as "this and similar charges".
        limit = note_limit(note.id, snap.records, snap.charges, snap.now)
        if limit is None:
            continue
        out.append(
            ReusableNoteView(
                note=note,
                charge=written_on,
                amount_limit_cents=limit,
                covered=tuple(covered),
            )
        )
    return out


def grant_detail(conn: Conn, snap: GrantSnapshot) -> GrantDetail:
    return GrantDetail(
        summary=summary(snap),
        terms=tuple(term_views(snap)),
        budget=budget(snap),
        grant_notes=tuple(n for n in snap.output.notes if n.grant_id == snap.grant.id),
        reusable_notes=tuple(reusable_notes(snap)),
        sign_off=sign_off_view(snap),
    )


# History and threads.


def _trigger_item(
    snap: GrantSnapshot, trigger: Trigger
) -> Record | Charge | EvidenceFile | ThreadMessage | None:
    if trigger.id is None:
        return None
    return {
        TriggerKind.RECORD: snap.state.by_id,
        TriggerKind.CHARGE: snap.charges_by_id,
        TriggerKind.FILE: snap.files_by_id,
        TriggerKind.THREAD_MESSAGE: {m.id: m for m in snap.messages},
    }.get(trigger.kind, {}).get(trigger.id)


def history_text(snap: GrantSnapshot, row: StatusRow, previous_row: StatusRow | None) -> str:
    """One status history line, worded by the checks' `history_line`, the one function the
    API and the evidence report share: "Apr 10, 2026 · new end date confirmed · Possible
    conflict → Evidence complete"."""
    entry = StatusEntry(changed_at=row.changed_at, trigger=row.trigger, status=row.status)
    before = (
        StatusEntry(
            changed_at=previous_row.changed_at,
            trigger=previous_row.trigger,
            status=previous_row.status,
        )
        if previous_row is not None
        else None
    )
    return history_line(entry, before, _trigger_item(snap, row.trigger), snap.records)


def history_entries(snap: GrantSnapshot, rows: Sequence[StatusRow]) -> list[HistoryEntry]:
    out: list[HistoryEntry] = []
    previous: Bucket | None = None
    previous_row: StatusRow | None = None
    for row in rows:
        bucket = row.status.bucket if isinstance(row.status, ChargeStatus) else None
        out.append(
            HistoryEntry(
                entry=StatusEntry(
                    changed_at=row.changed_at, trigger=row.trigger, status=row.status
                ),
                text=history_text(snap, row, previous_row),
            )
        )
        previous = bucket or previous
        previous_row = row
    return out


def thread(
    snap: GrantSnapshot,
    *,
    charge_id: str | None = None,
    record_ids: Sequence[str] = (),
    history: Sequence[StatusRow] = (),
) -> Thread:
    """One thread in time order (answer 10): code's check results when the status changed,
    the agent's suggestions, and the accountant's decisions and messages. At the same moment
    a record comes first, then the status it caused, then messages."""
    subject = set(record_ids)
    items: list[tuple[datetime, int, ThreadEntry]] = []
    for row in history:
        entry = StatusEntry(changed_at=row.changed_at, trigger=row.trigger, status=row.status)
        items.append((row.changed_at, 1, StatusThreadEntry(entry=entry)))
    messages = [
        m
        for m in snap.messages
        if (charge_id and m.charge_id == charge_id) or (m.record_id and m.record_id in subject)
    ]
    for m in messages:
        items.append((m.written_at, 2, MessageThreadEntry(message=m)))
    for r in _records_about(snap, charge_id, subject):
        if (r.author == Author.AGENT and snap.state.waits(r.id)) or r.author == Author.USER:
            items.append(
                (r.written_at, 0, RecordThreadEntry(record=r, state=record_state(snap.state, r)))
            )
    items.sort(key=lambda x: (x[0], x[1]))
    return Thread(
        entries=tuple(i for _, _, i in items),
        agent_run=run_reaching(snap, charge_id=charge_id, record_ids=subject),
    )


def run_reaching(
    snap: GrantSnapshot, *, charge_id: str | None, record_ids: set[str]
) -> AgentRun | None:
    """A queued or running run that will reach this thread (answer 12): one its own
    messages started, one triggered by its charge (or a charge in the same batch), its
    record, or a question open on it, and any closeout review or catch-up of the grant.
    The running one first, then the earliest queued."""

    def reaches(run: AgentRun) -> bool:
        t = run.trigger
        if t.kind == TriggerKind.CLOCK:
            return True
        if t.kind == TriggerKind.THREAD_MESSAGE:
            return (charge_id is not None and run.thread_charge_id == charge_id) or (
                run.thread_record_id in record_ids
            )
        if t.kind == TriggerKind.CHARGE and charge_id is not None and t.id:
            return charge_id in {c.id for c in batch_for(t.id, snap.charges)}
        if t.kind == TriggerKind.FILE:
            return True  # a file's run reads it and can link it to any charge
        return t.id is not None and (t.id == charge_id or t.id in record_ids)

    reaching = [r for r in snap.pending if reaches(r)]
    reaching.sort(key=lambda r: (r.status != RunStatus.RUNNING, r.queued_at))
    return reaching[0] if reaching else None


def _records_about(
    snap: GrantSnapshot, charge_id: str | None, subject: set[str]
) -> Iterable[Record]:
    about: set[str] = set()
    for r in snap.records:
        if (
            (charge_id and r.charge_id == charge_id)
            or r.record_id in subject
            or r.replaces_id in subject
        ):
            about.add(r.id)
    for r in snap.records:
        if isinstance(r.data, Confirmation) and any(
            t in about or t in subject for t in r.data.record_ids
        ):
            about.add(r.id)
    return [r for r in snap.records if r.id in about]


def record_chain(snap: GrantSnapshot, record_id: str) -> list[str]:
    """A record and every record it replaced, so a record's thread follows its corrections
    (answer 13)."""
    chain: list[str] = []
    current: str | None = record_id
    while current and current not in chain:
        chain.append(current)
        r = snap.state.by_id.get(current)
        current = r.replaces_id if r else None
    return chain


def charge_detail(
    p: Platform, snap: GrantSnapshot, charge: Charge, rows: Sequence[StatusRow]
) -> ChargeDetail:
    state = snap.state
    assignment = next(
        (
            r
            for r in state.current()
            if isinstance(r.data, BudgetAssignment) and r.data.charge_id == charge.id
        ),
        None,
    )
    line = None
    if assignment is not None and isinstance(assignment.data, BudgetAssignment):
        line = state.current_version(assignment.data.record_id)
    status = snap.charge_status(charge.id)
    questions = [q for q in snap.output.questions if q.charge_id == charge.id]
    open_keys = {(q.question, q.record_id) for q in questions}
    answers = [
        AnswerView(judgment=r, out_of_date=(r.data.question, r.data.record_id) in open_keys)
        for r in state.current()
        if isinstance(r.data, Judgment) and r.data.charge_id == charge.id
    ]
    links = [
        view
        for r in state.current()
        if isinstance(r.data, Link)
        and r.data.charge_id == charge.id
        and (view := _link_view(snap, r)) is not None
    ]
    # Lookups for what the status's reasons rest on, and the links' files.
    rest_on = {i for reason in (status.reasons if status else ()) for i in reason.record_ids}
    records = {i: state.by_id[i] for i in sorted(rest_on) if i in state.by_id}
    files = {v.file.id: v.file for v in links if v.file is not None}
    corrections = [
        snap.charges_by_id[i]
        for i in (status.corrections if status else ())
        if i in snap.charges_by_id
    ]
    return ChargeDetail(
        charge=charge,
        status=status,
        budget_line=line,
        account_categories=tuple(p.checks.account_categories(charge.account)),
        corrections=tuple(corrections),
        history=tuple(history_entries(snap, rows)),
        links=tuple(links),
        answers=tuple(answers),
        questions=tuple(questions),
        waiting=tuple(
            _suggestion(snap, r)
            for r in state.waiting()
            if r.author == Author.AGENT and charge.id in _touched_charges(snap, r)
        ),
        thread=thread(snap, charge_id=charge.id, history=rows),
        records=records,
        files=files,
    )


# Evidence.


def evidence_cards(snap: GrantSnapshot) -> list[EvidenceCard]:
    """One card per file, newest arrival first."""
    state = snap.state
    facts_by_file: dict[str, list[Record]] = {}
    for r in snap.records:
        if r.kind not in TERM_KINDS and r.kind not in {
            RecordKind.BILL,
            RecordKind.APPROVAL,
            RecordKind.NOTE,
        }:
            continue
        if r.replaces_id is not None:
            continue  # a correction is reached from the record that cited the file
        shown = state.current_version(r.id) or r
        for file_id in {c.file_id for c in citations(r.data)}:
            group = facts_by_file.setdefault(file_id, [])
            if shown not in group:
                group.append(shown)
    links_by_record: dict[str, list[Record]] = {}
    for r in state.current():
        if isinstance(r.data, Link):
            target = state.current_version(r.data.record_id)
            if target:
                links_by_record.setdefault(target.id, []).append(r)
    duplicates = {r.data.copy_file_id: r for r in snap.records if isinstance(r.data, Duplicate)}
    cards: list[EvidenceCard] = []
    for f in sorted(snap.files, key=lambda f: (f.arrived_at, f.id), reverse=True):
        mark = duplicates.get(f.id)
        mark_state = record_state(state, mark) if mark else None
        duplicate = None
        lookups: dict[str, EvidenceFile] = {}
        if (
            mark
            and mark_state is not None
            and mark_state
            in (
                RecordStateName.WAITING,
                RecordStateName.COUNTS,
            )
        ):
            assert isinstance(mark.data, Duplicate)
            duplicate = DuplicateView(mark=mark, state=mark_state)
            original = snap.files_by_id.get(mark.data.original_file_id)
            if original is not None:
                lookups[original.id] = original
        cards.append(
            EvidenceCard(
                file=f,
                facts=tuple(
                    FactView(
                        record=r,
                        state=record_state(state, r),
                        values=tuple(value_states(state, r)),
                        links=tuple(
                            FactLink(link=link, charge=snap.charges_by_id[link.charge_id])
                            for link in links_by_record.get(r.id, [])
                            if link.charge_id is not None and link.charge_id in snap.charges_by_id
                        ),
                        status=snap.record_status(r.id),
                    )
                    for r in facts_by_file.get(f.id, [])
                ),
                status=snap.file_status(f.id),
                duplicate=duplicate,
                files=lookups,
            )
        )
    return cards


def has_running_or_queued(snap: GrantSnapshot) -> bool:
    return any(r.status in (RunStatus.QUEUED, RunStatus.RUNNING) for r in snap.pending)


def anything_open(snap: GrantSnapshot) -> bool:
    """Decision 0022's "open": a charge that isn't ready for closeout (Evidence complete,
    accepted or fully reversed, and not snoozed; a charge with no status yet counts as
    open), or any row on the problem list."""
    for c in snap.charges:
        status = snap.charge_status(c.id)
        if status is None or not ready_for_closeout(status):
            return True
    return bool(problem_rows(snap))


def open_check(p: Platform) -> Callable[[Conn, Grant], bool]:
    """Whether anything is open on a grant, read in the caller's transaction (decision 0022):
    for the sign-off's note check, under the grant's lock."""

    def check(conn: Conn, grant: Grant) -> bool:
        return anything_open(load_snapshot(p, conn, grant))

    return check
