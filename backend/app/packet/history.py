"""The seam for the status history's wording.

One function words a status history entry, and both the API and the report
call it. The checks builder (#24) owns status text and is writing it under
backend/app/checks/. Until it lands, history_text below is a stand-in with the
same job: swap the body for a call to the checks' function, and nothing else
in the report changes.
"""

from collections.abc import Mapping

from app.contracts.charges import Charge
from app.contracts.checks import ChargeStatus, StatusEntry
from app.contracts.evidence import EvidenceFile
from app.contracts.records import Author, Record, RecordKind
from app.contracts.runs import TriggerKind


def history_text(
    entry: StatusEntry,
    *,
    records: Mapping[str, Record],
    files: Mapping[str, EvidenceFile],
    charges: Mapping[str, Charge],
) -> str:
    """What changed a status, in words. Stand-in for the checks' function (#24)."""
    why = _trigger(entry, records, files, charges)
    status = entry.status
    if isinstance(status, ChargeStatus):
        reason = next((r.text for r in status.reasons if r.bucket == status.bucket), "")
        if reason:
            return f"{why}. {reason}"
    return why


def _trigger(
    entry: StatusEntry,
    records: Mapping[str, Record],
    files: Mapping[str, EvidenceFile],
    charges: Mapping[str, Charge],
) -> str:
    t = entry.trigger
    if t.kind == TriggerKind.RECORD:
        r = records.get(t.id or "")
        if r is None:
            return "A record was written"
        by = "the agent" if r.author == Author.AGENT else "the accountant"
        return f"{_kind(r.kind)} by {by}"
    if t.kind == TriggerKind.CHARGE:
        c = charges.get(t.id or "")
        return f"Ledger line {c.ledger_line_id if c else t.id} arrived"
    if t.kind == TriggerKind.FILE:
        f = files.get(t.id or "")
        return f"{f.name if f else t.id} arrived"
    if t.kind == TriggerKind.THREAD_MESSAGE:
        return "A message in the review thread"
    return "Time passed"


def _kind(kind: RecordKind) -> str:
    return kind.value.replace("_", " ").capitalize()
