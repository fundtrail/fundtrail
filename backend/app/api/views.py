"""Builds the screen bodies from one grant as it stands at the workspace's "now".

The server works out everything nothing stores, through the contract functions
(`RecordState`) and the checks' output, and writes the wording. Nothing here writes.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

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
)
from app.contracts.evidence import EvidenceFile
from app.contracts.records import (
    FOUND,
    TERM_KINDS,
    Author,
    BudgetAssignment,
    BudgetLine,
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
from app.contracts.runs import AgentRun, RunStatus, Trigger, TriggerKind
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant, Workspace
from app.db import store, terms
from app.db.platform import Platform
from app.db.pool import transaction, workspace_now
from app.db.store import Conn, Status, StatusRow

from .screens import (
    AnswerView,
    BudgetAssignmentView,
    BudgetLineView,
    BudgetView,
    ChargeDetail,
    ChargeProblemRow,
    CheckItem,
    CloseoutDate,
    DecisionItem,
    DuplicateView,
    EvidenceCard,
    FactView,
    GrantDetail,
    GrantProblem,
    GrantProblemRow,
    GrantSummary,
    HistoryEntry,
    LinkView,
    MessageItem,
    ProblemRow,
    RecordProblemRow,
    RecordStateName,
    SignOffState,
    SuggestionItem,
    SuggestionView,
    TermsWaitingRow,
    TermView,
    Thread,
    ThreadItem,
    ValueState,
)

BUCKET_LABEL = {
    Bucket.EVIDENCE_COMPLETE: "Evidence complete",
    Bucket.POSSIBLE_CONFLICT: "Possible conflict",
    Bucket.MISSING_EVIDENCE: "Missing evidence",
    Bucket.NEEDS_HUMAN: "Needs a human",
}
# The buckets on the problem list, most serious first (answer 1).
_LIST_ORDER = [b for b in SEVERITY if b != Bucket.EVIDENCE_COMPLETE]


def _kind_words(kind: RecordKind) -> str:
    return kind.value.replace("_", " ")


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def _day(at: datetime) -> str:
    return f"{at:%b} {at.day}, {at.year}"


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
    now = workspace_now(workspace)
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
    )


# Records.


def record_state(state: RecordState, record: Record) -> RecordStateName:
    if state.is_waiting(record.id):
        return "waiting"
    if state.is_current(record.id):
        return "counts"
    if state.decision(record.id) == Decision.REJECTED:
        return "rejected"
    retracted = any(
        isinstance(r.data, Retraction) and r.replaces_id == record.id and state.is_effective(r.id)
        for r in state.records
    )
    return "retracted" if retracted else "replaced"


def value_states(state: RecordState, record: Record) -> list[ValueState]:
    unconfirmed = set(state.unconfirmed_values(record))
    decided = state.decided_by(record.id)
    out: list[ValueState] = []
    for path, value in cited_values(record.data):
        if path in unconfirmed:
            out.append(ValueState(path=path, confirmed=False))
        elif value.citation is None:
            out.append(
                ValueState(path=path, confirmed=True, how="typed", confirmed_at=record.written_at)
            )
        elif value.citation.match in FOUND:
            out.append(ValueState(path=path, confirmed=True, how="found"))
        else:
            at = decided.written_at if decided else None
            out.append(
                ValueState(path=path, confirmed=True, how="record_confirmed", confirmed_at=at)
            )
    return out


def _link_view(snap: GrantSnapshot, link: Record) -> LinkView:
    assert isinstance(link.data, Link)
    target = snap.state.current_version(link.data.record_id)
    part_file = link.data.part.file_id if link.data.part else None
    file_id = (
        part_file or next((c.file_id for c in citations(target.data)), None)
        if target
        else part_file
    )
    return LinkView(
        link=link,
        record=target,
        values=value_states(snap.state, target) if target else [],
        file=snap.files_by_id.get(file_id) if file_id else None,
        charge=snap.charges_by_id.get(link.data.charge_id),
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
        record=record, replaces=replaces, charge_ids=_touched_charges(snap, record)
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
        if (status.bucket == Bucket.EVIDENCE_COMPLETE or status.accepted) and not status.snoozed:
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
            (f.arrived_at, TermsWaitingRow(file=f, record_ids=[r.id for r in group], text=text))
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
    rows += [row for _, row in sorted(records, key=lambda x: x[0])]
    # A charge whose only failing reasons point at terms that have their own rows isn't a
    # row of its own: the term's row stands for it.
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
    charges.sort(
        key=lambda cs: (_LIST_ORDER.index(cs[1].bucket), cs[0].posting_date, cs[0].ledger_line_id)
    )
    rows += [ChargeProblemRow(charge=c, status=s) for c, s in charges]
    return rows


def _covered_by_terms(status: ChargeStatus, term_rows: set[str | None]) -> bool:
    failing = [r for r in status.reasons if r.bucket != Bucket.EVIDENCE_COMPLETE]
    return bool(failing) and all(r.record_ids and set(r.record_ids) <= term_rows for r in failing)


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
                    state=want,  # pyright: ignore[reportArgumentType]
                    decision=snap.state.decided_by(r.id),
                    status=snap.record_status(r.id),
                    replaces=snap.state.by_id.get(r.replaces_id) if r.replaces_id else None,
                )
            )
    return out


def budget(snap: GrantSnapshot) -> BudgetView:
    spent = terms.spent_by_line(snap.state, snap.charges)
    lines = []
    for line in terms.budget_lines(snap.state):
        assert isinstance(line.data, BudgetLine)
        lines.append(
            BudgetLineView(
                line=line, amount_cents=line.data.amount.value, spent_cents=spent[line.id]
            )
        )
    return BudgetView(
        lines=lines,
        limit_cents=terms.award_limit(snap.state),
        spent_cents=sum(c.amount_cents for c in snap.charges),
    )


def sign_off_state(conn: Conn, snap: GrantSnapshot) -> SignOffState:
    """Decision 0022: changes since the latest sign-off in a charge's bucket, an accepted
    status, the problem list or the total spent."""
    signed = [r for r in snap.state.current() if isinstance(r.data, SignOff)]
    if not signed:
        return SignOffState(state="not_signed")
    sign_off = signed[-1]
    at = sign_off.written_at
    then = store.statuses_as_of(conn, snap.grant.id, at)
    changes: list[str] = []
    for c in snap.charges:
        before = then.get(("charge", c.id))
        after = snap.charge_status(c.id)
        if not isinstance(before, ChargeStatus):
            if after is not None:
                changes.append(
                    f"{c.ledger_line_id} arrived after sign-off: {BUCKET_LABEL[after.bucket]}"
                )
            continue
        if after is not None and (before.bucket, before.accepted) != (after.bucket, after.accepted):
            was = BUCKET_LABEL[before.bucket] + (" (accepted)" if before.accepted else "")
            now = BUCKET_LABEL[after.bucket] + (" (accepted)" if after.accepted else "")
            changes.append(f"{c.ledger_line_id}: {was} → {now}")
    flagged_then = sum(1 for s in then.values() if s.flagged)
    flagged_now = sum(1 for s in snap.statuses.values() if s.flagged)
    if flagged_then != flagged_now:
        changes.append(f"Problems flagged: {flagged_then} → {flagged_now}")
    spent_then = sum(c.amount_cents for c in snap.charges if c.arrived_at <= at)
    spent_now = sum(c.amount_cents for c in snap.charges)
    if spent_then != spent_now:
        changes.append(f"Spending: {_money(spent_then)} → {_money(spent_now)}")
    return SignOffState(
        state="changed" if changes else "signed", sign_off=sign_off, changes=changes
    )


def grant_detail(conn: Conn, snap: GrantSnapshot) -> GrantDetail:
    return GrantDetail(
        summary=summary(snap),
        terms=term_views(snap),
        budget=budget(snap),
        grant_notes=[n for n in snap.output.notes if n.grant_id == snap.grant.id],
        sign_off=sign_off_state(conn, snap),
    )


# History and threads.


def describe_trigger(snap: GrantSnapshot, trigger: Trigger) -> str:
    if trigger.kind == TriggerKind.CLOCK:
        return "time passed"
    if trigger.kind == TriggerKind.CHARGE:
        c = snap.charges_by_id.get(trigger.id or "")
        return f"ledger line {c.ledger_line_id} arrived" if c else "a ledger line arrived"
    if trigger.kind == TriggerKind.FILE:
        f = snap.files_by_id.get(trigger.id or "")
        return f"{f.name} arrived" if f else "a file arrived"
    if trigger.kind == TriggerKind.THREAD_MESSAGE:
        return "a question in a thread"
    record = snap.state.by_id.get(trigger.id or "")
    if record is None:
        return "a record changed"
    return describe_record(snap, record)


def describe_record(snap: GrantSnapshot, record: Record) -> str:
    who = "the accountant" if record.author == Author.USER else "the agent"
    data = record.data
    if isinstance(data, Confirmation):
        targets = [snap.state.by_id[t] for t in data.record_ids if t in snap.state.by_id]
        verb = "confirmed" if data.decision == Decision.CONFIRMED else "rejected"
        if any(t.kind == RecordKind.PERIOD_OF_PERFORMANCE for t in targets):
            earlier = [
                r
                for r in snap.records
                if r.kind == RecordKind.PERIOD_OF_PERFORMANCE
                and r.id not in data.record_ids
                and r.written_at <= record.written_at
            ]
            return f"new end date {verb}" if earlier else f"period of performance {verb}"
        kinds = sorted({_kind_words(t.kind) for t in targets}) or ["records"]
        return f"{', '.join(kinds)} {verb} by {who}"
    if isinstance(data, Judgment):
        question = data.question.value.replace("_", " ")
        return f"answer on {question} by {who}: {data.answer.value}"
    if isinstance(data, Retraction):
        return f"retracted by {who}"
    if record.replaces_id:
        return f"{_kind_words(record.kind)} corrected by {who}"
    return f"{_kind_words(record.kind)} added by {who}"


def _shared_history_line() -> Callable[..., str] | None:
    """The checks' `history_line(entry, previous, about, records)` (#24), once it's there."""
    try:
        module = importlib.import_module("app.checks.history")
    except ImportError:
        return None
    return getattr(module, "history_line", None)


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


def history_text(
    snap: GrantSnapshot,
    row: StatusRow,
    previous: Bucket | None,
    previous_row: StatusRow | None = None,
) -> str:
    """The wording of one status history line.

    The seam for the one function that words status history for the API and the evidence
    report alike, which the checks (#24) are writing in `app/checks/` (`history_line`).
    Until it lands, this words it: "Apr 10, 2026 · new end date confirmed · Possible
    conflict → Evidence complete".
    """
    shared = _shared_history_line()
    if shared is not None:
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
        return shared(entry, before, _trigger_item(snap, row.trigger), snap.records)
    bucket = row.status.bucket if isinstance(row.status, ChargeStatus) else None
    parts = [_day(row.changed_at), describe_trigger(snap, row.trigger)]
    if bucket is not None:
        parts.append(
            f"{BUCKET_LABEL[previous]} → {BUCKET_LABEL[bucket]}"
            if previous and previous != bucket
            else BUCKET_LABEL[bucket]
        )
    return " · ".join(parts)


def history_entries(snap: GrantSnapshot, rows: Sequence[StatusRow]) -> list[HistoryEntry]:
    out: list[HistoryEntry] = []
    previous: Bucket | None = None
    previous_row: StatusRow | None = None
    for row in rows:
        bucket = row.status.bucket if isinstance(row.status, ChargeStatus) else None
        out.append(
            HistoryEntry(
                changed_at=row.changed_at,
                trigger=row.trigger,
                bucket=bucket,
                previous_bucket=previous,
                text=history_text(snap, row, previous, previous_row),
            )
        )
        previous = bucket or previous
        previous_row = row
    return out


def _check_text(snap: GrantSnapshot, row: StatusRow) -> str:
    status = row.status
    if isinstance(status, ChargeStatus):
        failing = [r.text for r in status.reasons if r.bucket != Bucket.EVIDENCE_COMPLETE]
        head = BUCKET_LABEL[status.bucket]
        return f"{head}. " + " ".join(failing) if failing else f"{head}."
    problems = [p.text for p in status.problems]
    return " ".join(problems) if problems else "No problems."


def thread(
    snap: GrantSnapshot,
    *,
    charge_id: str | None = None,
    record_ids: Sequence[str] = (),
    history: Sequence[StatusRow] = (),
) -> Thread:
    """One thread in time order: code's check results when the status changed, the agent's
    messages and suggestions, and the accountant's decisions and messages."""
    subject = set(record_ids)
    items: list[tuple[datetime, int, ThreadItem]] = []
    for row in history:
        items.append((row.changed_at, 1, CheckItem(at=row.changed_at, text=_check_text(snap, row))))
    messages = [
        m
        for m in snap.messages
        if (charge_id and m.charge_id == charge_id) or (m.record_id and m.record_id in subject)
    ]
    for m in messages:
        items.append((m.written_at, 2, MessageItem(at=m.written_at, message=m)))
    for r in _records_about(snap, charge_id, subject):
        if r.author == Author.AGENT and snap.state.waits(r.id):
            items.append(
                (
                    r.written_at,
                    0,
                    SuggestionItem(
                        at=r.written_at,
                        record=r,
                        state=record_state(snap.state, r),
                        text=describe_record(snap, r),
                    ),
                )
            )
        elif r.author == Author.USER:
            items.append(
                (
                    r.written_at,
                    0,
                    DecisionItem(at=r.written_at, record=r, text=describe_record(snap, r)),
                )
            )
    items.sort(key=lambda x: (x[0], x[1]))
    asked = {m.id for m in messages if m.author == Author.USER}
    run = next(
        (
            r
            for r in snap.pending
            if r.trigger.kind == TriggerKind.THREAD_MESSAGE and r.trigger.id in asked
        ),
        None,
    )
    return Thread(items=[i for _, _, i in items], agent=run.status if run else None, agent_run=run)


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
    questions = [q for q in snap.output.questions if q.charge_id == charge.id]
    open_keys = {(q.question, q.record_id) for q in questions}
    answers = [
        AnswerView(judgment=r, out_of_date=(r.data.question, r.data.record_id) in open_keys)
        for r in state.current()
        if isinstance(r.data, Judgment) and r.data.charge_id == charge.id
    ]
    return ChargeDetail(
        charge=charge,
        status=snap.charge_status(charge.id),
        budget=BudgetAssignmentView(assignment=assignment, line=line)
        if assignment and line
        else None,
        account_categories=list(p.checks.account_categories(charge.account)),
        history=history_entries(snap, rows),
        links=[
            _link_view(snap, r)
            for r in state.current()
            if isinstance(r.data, Link) and r.data.charge_id == charge.id
        ],
        answers=answers,
        questions=questions,
        waiting=[
            _suggestion(snap, r)
            for r in state.waiting()
            if r.author == Author.AGENT and charge.id in _touched_charges(snap, r)
        ],
        thread=thread(snap, charge_id=charge.id, history=rows),
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
        if mark and mark_state in ("waiting", "counts"):
            assert isinstance(mark.data, Duplicate)
            duplicate = DuplicateView(
                mark=mark,
                state=mark_state,
                original=snap.files_by_id.get(mark.data.original_file_id),
            )
        cards.append(
            EvidenceCard(
                file=f,
                facts=[
                    FactView(
                        record=r,
                        state=record_state(state, r),
                        values=value_states(state, r),
                        links=[_link_view(snap, link) for link in links_by_record.get(r.id, [])],
                        status=snap.record_status(r.id),
                    )
                    for r in facts_by_file.get(f.id, [])
                ],
                status=snap.file_status(f.id),
                duplicate=duplicate,
            )
        )
    return cards


def has_running_or_queued(snap: GrantSnapshot) -> bool:
    return any(r.status in (RunStatus.QUEUED, RunStatus.RUNNING) for r in snap.pending)


def sign_off_refusals(p: Platform, grant: Grant, data: SignOff) -> list[str]:
    """Decision 0022: nothing blocks a sign-off except a run in progress or queued, and a
    sign-off with anything still open needs a note."""
    with transaction(p.pool) as conn:
        snap = load_snapshot(p, conn, grant)
    if snap.pending:
        return ["The agent is still working on this grant. Sign off once it's done."]
    if problem_rows(snap) and not (data.note and data.note.strip()):
        return ["Something is still open, so a sign-off needs a note."]
    return []
