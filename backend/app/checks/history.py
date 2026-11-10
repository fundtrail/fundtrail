"""How one status change reads in the status history (product.md, "What the user sees").

    Apr 10, 2026 · new end date confirmed · Possible conflict → Evidence complete

The date the status changed, what triggered it, and the change itself. The API
and the evidence report both call `history_line`, so the history reads the same
everywhere. It's pure, and imports nothing from the API.

The caller passes the object the trigger names (the record, charge, file or
thread message), because a StatusEntry carries only its ID. For a change saved
from an agent run, the trigger is what started the run. To word a confirmation
("new end date confirmed"), the caller also passes the records it may list.
"""

from collections.abc import Iterable

from app.checks.text import day
from app.contracts.charges import Charge
from app.contracts.checks import Bucket, ChargeStatus, GrantStatus, RecordStatus, StatusEntry
from app.contracts.evidence import EvidenceFile
from app.contracts.records import (
    TERM_KINDS,
    Author,
    ChecklistRemoval,
    Confirmation,
    Decision,
    Judgment,
    PeriodOfPerformance,
    Question,
    Record,
    RecordKind,
)
from app.contracts.runs import TriggerKind
from app.contracts.threads import ThreadMessage

BUCKET_LABELS = {
    Bucket.EVIDENCE_COMPLETE: "Evidence complete",
    Bucket.POSSIBLE_CONFLICT: "Possible conflict",
    Bucket.MISSING_EVIDENCE: "Missing evidence",
    Bucket.NEEDS_HUMAN: "Needs a human",
}

_KIND_LABELS = {
    RecordKind.BUDGET_LINE: "a budget line",
    RecordKind.PERSON: "a person on the grant",
    RecordKind.APPROVAL_RULE: "an approval rule",
    RecordKind.RATE: "a rate",
    RecordKind.NOTICE: "a funding notice",
    RecordKind.OTHER_TERM: "a grant term",
    RecordKind.BILL: "a bill",
    RecordKind.APPROVAL: "an approval",
    RecordKind.NOTE: "a supporting document",
    RecordKind.LINK: "a link",
    RecordKind.BUDGET_ASSIGNMENT: "a budget line assignment",
    RecordKind.JUDGMENT: "an answer",
    RecordKind.CHECKLIST_ITEM: "a checklist item",
    RecordKind.CHECKLIST_REMOVAL: "a checklist item's removal",
    RecordKind.DISPUTE: "a dispute",
    RecordKind.DUPLICATE: "a duplicate mark",
    RecordKind.CONFIRMATION: "a confirmation",
    RecordKind.ACCEPTED_REASON: "an accepted reason",
    RecordKind.SNOOZE: "a snooze",
    RecordKind.SIGN_OFF: "a sign-off",
    RecordKind.RETRACTION: "a withdrawal",
}

_QUESTION_LABELS = {
    Question.ALLOWABLE: "Allowable",
    Question.COVERS: "Covers",
    Question.UNUSUAL_TERM: "Unusual term",
}


def _kind_label(record: Record) -> str:
    data = record.data
    if isinstance(data, PeriodOfPerformance):
        return "the grant's dates" if data.start is not None else "a new end date"
    return _KIND_LABELS[record.kind]


def _who(record: Record) -> str:
    return "the agent" if record.author == Author.AGENT else "the accountant"


def _confirmed(data: Confirmation, by_id: dict[str, Record]) -> str:
    verb = "confirmed" if data.decision == Decision.CONFIRMED else "rejected"
    targets = [by_id[i] for i in data.record_ids if i in by_id]
    labels = list(dict.fromkeys(_kind_label(t) for t in targets))
    if len(labels) == 1:
        label = labels[0]
        for article in ("a ", "an "):
            if label.startswith(article):
                label = label[len(article) :]
        return f"{label} {verb}"
    if targets and all(t.kind in TERM_KINDS for t in targets):
        return f"grant terms {verb}"
    return f"{len(data.record_ids)} records {verb}"


def _record_event(record: Record, by_id: dict[str, Record]) -> str:
    data = record.data
    who = _who(record)
    if isinstance(data, Confirmation):
        return _confirmed(data, by_id)
    if record.kind == RecordKind.RETRACTION:
        old = by_id.get(record.replaces_id or "")
        return f"{who} withdrew {_kind_label(old) if old else 'a record'}"
    if record.replaces_id is not None:
        return f"{who} corrected {_kind_label(record)}"
    if isinstance(data, Judgment):
        if data.question == Question.FLAG:
            return f"{who} flagged it" if record.author == Author.AGENT else f"{who} settled a flag"
        return f"{who} answered {_QUESTION_LABELS[data.question]}: {data.answer.value}"
    if isinstance(data, ChecklistRemoval):
        verb = "suggested removing" if record.author == Author.AGENT else "removed"
        return f"{who} {verb} a checklist item"
    events = {
        RecordKind.LINK: "linked evidence",
        RecordKind.BUDGET_ASSIGNMENT: "assigned a budget line",
        RecordKind.CHECKLIST_ITEM: "added a checklist item",
        RecordKind.DISPUTE: "disputed a check",
        RecordKind.DUPLICATE: "marked a file as a copy",
        RecordKind.ACCEPTED_REASON: "accepted a reason",
        RecordKind.SNOOZE: "snoozed it",
        RecordKind.SIGN_OFF: "signed off",
    }
    if record.kind in events:
        return f"{who} {events[record.kind]}"
    return f"{who} read {_kind_label(record)}"


def describe_trigger(
    entry: StatusEntry,
    about: Record | Charge | EvidenceFile | ThreadMessage | None = None,
    records: Iterable[Record] = (),
) -> str:
    """What triggered a status change, in a few words."""
    kind = entry.trigger.kind
    if kind == TriggerKind.CLOCK:
        return "time passed"
    if isinstance(about, Charge) and kind == TriggerKind.CHARGE:
        return f"ledger line {about.ledger_line_id} arrived"
    if isinstance(about, EvidenceFile) and kind == TriggerKind.FILE:
        return f"{about.name} arrived"
    if isinstance(about, ThreadMessage) and kind == TriggerKind.THREAD_MESSAGE:
        who = "the agent" if about.author == Author.AGENT else "the accountant"
        return f"{who} wrote in the thread"
    if isinstance(about, Record) and kind == TriggerKind.RECORD:
        by_id = {r.id: r for r in records}
        by_id.setdefault(about.id, about)
        return _record_event(about, by_id)
    return {
        TriggerKind.CHARGE: "a ledger line arrived",
        TriggerKind.FILE: "a file arrived",
        TriggerKind.THREAD_MESSAGE: "a message in the thread",
        TriggerKind.RECORD: "a record was written",
    }[kind]


def _state(status: ChargeStatus | RecordStatus | GrantStatus) -> str:
    if isinstance(status, ChargeStatus):
        label = BUCKET_LABELS[status.bucket]
        if status.accepted:
            label += " (accepted)"
        elif status.snoozed:
            label += " (snoozed)"
        return label
    n = len(status.problems)
    label = "no problems" if n == 0 else ("1 problem" if n == 1 else f"{n} problems")
    if n and status.accepted:
        label += " (accepted)"
    elif n and status.snoozed:
        label += " (snoozed)"
    return label


def history_line(
    entry: StatusEntry,
    previous: StatusEntry | None = None,
    about: Record | Charge | EvidenceFile | ThreadMessage | None = None,
    records: Iterable[Record] = (),
) -> str:
    """One line of status history: "Apr 10, 2026 · new end date confirmed · Possible conflict →
    Evidence complete". The change shows only the new state when there's no earlier one, or when
    the state reads the same (for example when only the reasons changed)."""
    before = _state(previous.status) if previous is not None else None
    after = _state(entry.status)
    change = after if before is None or before == after else f"{before} → {after}"
    trigger = describe_trigger(entry, about, records)
    return f"{day(entry.changed_at.date())} · {trigger} · {change}"
