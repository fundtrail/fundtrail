"""The search for bills that look like the same one (architecture.md, "Structure over memory").

When a bill arrives, code finds the bills already on the grant that look like
it, and the agent compares the saved facts. The agent's run preparation calls
`likely_duplicates`. It's pure: no database, no model.

The rule (provisional, owned by the checks). A bill already on the grant is a
likely duplicate of the new one when any of these holds:

1. It was read from a file with the exact same bytes (the same SHA-256).
2. Both state a document number, and the numbers are the same once case,
   spaces and punctuation are dropped ("INV-1001" and "inv 1001").
3. Both state the same total to the cent, nothing on them disagrees, and at
   least one other thing agrees. Disagreeing means different document numbers,
   different vendors, or dates more than DATE_WINDOW_DAYS apart. Agreeing means
   the same vendor, or dates within DATE_WINDOW_DAYS.

A bill from the same file as the new one, a bill read from a copy the
accountant confirmed as a duplicate, and a bill that's no longer current are
left out. Matches by rule 1 or 2 come first, then the rest, newest first, and
the list stops at MAX_CANDIDATES. A long list means the rule is too loose.

Fourteen days keeps a monthly fee from the same vendor (about 30 days apart)
out, and still catches an invoice and its copy or a reprint sent a week later.
"""

import re
from collections.abc import Sequence
from datetime import date

from app.checks.text import norm
from app.contracts.evidence import EvidenceFile
from app.contracts.records import Bill, Decision, Duplicate, Record, citations
from app.contracts.rules import RecordState

DATE_WINDOW_DAYS = 14
MAX_CANDIDATES = 5


def _number(bill: Bill) -> str | None:
    if bill.document_number is None:
        return None
    key = re.sub(r"[^0-9a-z]", "", bill.document_number.value.lower())
    return key or None


def _vendor(bill: Bill) -> str | None:
    return norm(bill.vendor.value) if bill.vendor is not None else None


def _dated(bill: Bill) -> date | None:
    return bill.dated.value if bill.dated is not None else None


def _files(record: Record) -> set[str]:
    return {c.file_id for c in citations(record.data)}


def _total_match(new: Bill, old: Bill) -> bool:
    if new.total.value != old.total.value:
        return False
    agrees = False
    numbers = (_number(new), _number(old))
    if None not in numbers and numbers[0] != numbers[1]:
        return False
    vendors = (_vendor(new), _vendor(old))
    if None not in vendors:
        if vendors[0] != vendors[1]:
            return False
        agrees = True
    a, b = _dated(new), _dated(old)
    if a is not None and b is not None:
        if abs((a - b).days) > DATE_WINDOW_DAYS:
            return False
        agrees = True
    return agrees


def likely_duplicates(
    bill: Record, records: Sequence[Record], files: Sequence[EvidenceFile]
) -> list[str]:
    """The IDs of the bills on the grant that look like `bill`, strongest first, at most five.

    `bill` may be new (not in `records` yet). `records` and `files` are what's
    visible on the workspace, records in the order they were written.
    """
    new = bill.data
    if not isinstance(new, Bill):
        return []
    state = RecordState(records, files)
    sha = {f.id: f.sha256 for f in files}
    new_files = _files(bill)
    new_hashes = {sha[f] for f in new_files if f in sha}
    copies = {
        r.data.copy_file_id
        for r in state.current()
        if isinstance(r.data, Duplicate) and state.decision(r.id) == Decision.CONFIRMED
    }
    strong: list[str] = []
    weak: list[str] = []
    for r in reversed(state.current()):  # newest first
        old = r.data
        if r.id == bill.id or r.grant_id != bill.grant_id or not isinstance(old, Bill):
            continue
        old_files = _files(r)
        if old_files & new_files or (old_files and old_files <= copies):
            continue
        same_bytes = bool({sha[f] for f in old_files if f in sha} & new_hashes)
        same_number = _number(new) is not None and _number(new) == _number(old)
        if same_bytes or same_number:
            strong.append(r.id)
        elif _total_match(new, old):
            weak.append(r.id)
    return (strong + weak)[:MAX_CANDIDATES]
