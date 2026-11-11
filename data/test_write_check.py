"""Every record in each sample's agent_records.json passes the save's write check.

The checks-only play stores the agent's records straight into the database, so it
never runs the write check a real save runs. This test does: it takes each
sample's records in file order and runs every one through the contract's
`check_new_record`, with the checks' own `default_items` (W2), over the charges
and files that have arrived by the record's time and the records written before
it, as an agent run writing it would.

A real save also matches each citation against its file. For a PDF that's the
quote finder, so `write_check_problems` ends with test_seed's check that the
finder finds every passage the records cite into a PDF, with its value.

It needs the backend's dependencies, so run it from backend/:

    cd backend && uv run python ../data/test_write_check.py
    cd backend && uv run pytest ../data/test_write_check.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent
sys.path.insert(0, str(DATA.parent / "backend"))
sys.path.insert(0, str(DATA))

import test_seed  # noqa: E402

from app.checks import default_items  # noqa: E402
from app.contracts.charges import Charge  # noqa: E402
from app.contracts.evidence import EvidenceFile, storage_path  # noqa: E402
from app.contracts.records import Record  # noqa: E402
from app.contracts.rules import check_new_record  # noqa: E402
from app.contracts.runs import Trigger, TriggerKind  # noqa: E402

WORKSPACE = "ws-sample"

MEDIA = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".eml": "message/rfc822",
    ".txt": "text/plain",
}


def write_check_problems(folder: Path, grant) -> list[str]:
    """The write check's problems with each of the sample's agent records, in file order."""
    grant_id = f"grant-{grant.slug}"
    charges = [
        (
            grant.line_arrival(ln),
            Charge(
                id=f"chg-{ln.line_id}",
                workspace_id=WORKSPACE,
                grant_id=grant_id,
                ledger_line_id=ln.line_id,
                transaction_date=ln.transaction_date,
                posting_date=ln.posting_date,
                arrived_at=grant.line_arrival(ln),
                amount_cents=ln.amount_cents,
                description=ln.description,
                account=ln.account,
                vendor=ln.vendor or None,
                reference=ln.reference or None,
                original_line_id=ln.original_line_id or None,
            ),
        )
        for ln in grant.lines
    ]
    files = []
    for d in grant.docs:
        file_id = f"file-{d.name}"
        arrived = grant.file_arrival(d.name)
        files.append(
            (
                arrived,
                EvidenceFile(
                    id=file_id,
                    workspace_id=WORKSPACE,
                    grant_id=grant_id,
                    source=d.source,
                    name=d.name,
                    media_type=MEDIA[Path(d.name).suffix],
                    storage_path=storage_path(WORKSPACE, grant_id, file_id, d.name),
                    sha256="0" * 64,
                    arrived_at=arrived,
                    sender=d.sender,
                ),
            )
        )

    raw = json.loads((folder / "agent_records.json").read_text(encoding="utf-8"))["records"]
    problems: list[str] = []
    written: list[Record] = []
    for r in raw:
        record = Record.model_validate({**r, "read_through_seq": len(written)})
        at = record.written_at
        cited = [c["file_id"] for c in test_seed.citations(r["data"])]
        charge_id = r["data"].get("charge_id")
        trigger = (
            Trigger(kind=TriggerKind.FILE, id=cited[0])
            if cited
            else Trigger(kind=TriggerKind.CHARGE, id=charge_id)
            if charge_id
            else Trigger(kind=TriggerKind.CLOCK)
        )
        found = check_new_record(
            record,
            written,
            [c for t, c in charges if t <= at],
            [f for t, f in files if t <= at],
            default_items=default_items,
            trigger=trigger,
        )
        problems += [f"{folder.name}: {record.id}: {p}" for p in found]
        written.append(record)
    test_seed.check_pdf_citations(folder, grant, problems)
    return problems


def test_agent_records_pass_the_write_check() -> None:
    g = test_seed.gen()
    problems: list[str] = []
    for folder in (test_seed.LARGER, test_seed.SMALL):
        problems += write_check_problems(folder, g[folder])
    assert not problems, "\n".join(problems[:30])


if __name__ == "__main__":
    try:
        test_agent_records_pass_the_write_check()
        print("ok    test_agent_records_pass_the_write_check")
    except AssertionError as exc:
        print(f"FAIL  test_agent_records_pass_the_write_check\n{exc}")
        sys.exit(1)
