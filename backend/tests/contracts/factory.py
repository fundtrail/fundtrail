"""Small hand-written records for the contract tests: one grant, one charge, a few files."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from app.contracts.charges import Charge
from app.contracts.evidence import EvidenceFile, Source
from app.contracts.records import DefaultItem, Record
from app.contracts.rules import check_new_record
from app.contracts.runs import Trigger, TriggerKind

T0 = datetime(2026, 1, 5, 12, tzinfo=UTC)
ACCOUNTANT = "00000000-0000-4000-8000-0000000000aa"


def at(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


def file(id: str, arrived_hours: float = -100, grant_id: str = "g") -> EvidenceFile:
    name = f"{id}.txt"
    return EvidenceFile(
        id=id,
        workspace_id="w",
        grant_id=grant_id,
        source=Source.UPLOAD,
        name=name,
        media_type="text/plain",
        storage_path=f"w/{grant_id}/{id}/{name}",
        sha256=id,
        arrived_at=at(arrived_hours),
        # Stored in arrival order, ahead of any record in these tests.
        stored_seq=int((arrived_hours + 1000) * 100),
    )


FILES = [file("f1"), file("f2"), file("f3")]

# A run's read point in these tests: it read everything stored.
RUN_READ_THROUGH = 10**9

CHARGE = Charge(
    id="c1",
    workspace_id="w",
    grant_id="g",
    ledger_line_id="L-1",
    transaction_date=T0.date(),
    posting_date=T0.date(),
    arrived_at=at(-50),
    amount_cents=1200,
    description="Pipette tips",
    account="55016 Lab Instruments and Supplies",
)
CHARGES = [CHARGE, CHARGE.model_copy(update={"id": "c2", "ledger_line_id": "L-2"})]


def citation(
    passage: str = "Total Due: $12.00", file_id: str = "f1", match: str | None = "exact"
) -> dict[str, Any]:
    c: dict[str, Any] = {
        "file_id": file_id,
        "passage": passage,
        "location": {
            "type": "char_location",
            "start_char_index": 0,
            "end_char_index": len(passage),
        },
    }
    if match is not None:
        c["match"] = match
    return c


def cited(
    value: Any,
    text: str,
    passage: str | None = None,
    file_id: str = "f1",
    match: str | None = "exact",
):
    return {"value": value, "text": text, "citation": citation(passage or text, file_id, match)}


def bill(
    total: int = 1200, text: str = "$12.00", file_id: str = "f1", match: str | None = "exact"
) -> dict[str, Any]:
    return {"kind": "bill", "total": cited(total, text, f"Total Due: {text}", file_id, match)}


def approval(file_id: str = "f2") -> dict[str, Any]:
    return {
        "kind": "approval",
        "approver_email": cited("po@funder.example", "po@funder.example", file_id=file_id),
        "covers": cited("travel", "travel", "Approved: travel", file_id=file_id),
    }


def budget_line(name: str = "Materials and Supplies", file_id: str = "f3") -> dict[str, Any]:
    passage = f"{name} $40,000"
    return {
        "kind": "budget_line",
        "dated": cited("2023-01-10", "January 10, 2023", file_id=file_id),
        "name": cited(name, name, passage, file_id),
        "amount": cited(4000000, "$40,000", passage, file_id),
        "category": "materials_and_supplies",
    }


def other_term(file_id: str = "f3") -> dict[str, Any]:
    return {
        "kind": "other_term",
        "dated": cited("2023-01-10", "January 10, 2023", file_id=file_id),
        "label": "PI on leave",
        "statement": cited("The PI is on leave.", "The PI is on leave.", file_id=file_id),
    }


def link(
    record_id: str = "b1", charge_id: str = "c1", amount: int | None = 1200, **changes: Any
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "kind": "link",
        "record_id": record_id,
        "charge_id": charge_id,
        "amount_cents": amount,
        "part": citation(),
        "default_item": "bill",
    }
    return data | changes


def answer(
    answer: str, question: str = "allowable", charge_id: str | None = "c1", **changes: Any
) -> dict[str, Any]:
    data = {
        "kind": "judgment",
        "charge_id": charge_id,
        "question": question,
        "text": "Is this cost necessary and reasonable, and is it for this project?",
        "answer": answer,
        "reasoning": "Because.",
    }
    return data | changes


def confirm(*record_ids: str, decision: str = "confirmed") -> dict[str, Any]:
    return {"kind": "confirmation", "record_ids": list(record_ids), "decision": decision}


def agent(
    id: str, data: dict[str, Any], hours: float = 0, replaces_id: str | None = None
) -> Record:
    return Record.model_validate(
        {
            "id": id,
            "workspace_id": "w",
            "grant_id": "g",
            "author": "agent",
            "written_at": at(hours),
            "replaces_id": replaces_id,
            "data": data,
        }
    )


def user(id: str, data: dict[str, Any], hours: float = 0, replaces_id: str | None = None) -> Record:
    return Record.model_validate(
        {
            "id": id,
            "workspace_id": "w",
            "grant_id": "g",
            "author": "user",
            "author_user_id": ACCOUNTANT,
            "written_at": at(hours),
            "replaces_id": replaces_id,
            "data": data,
        }
    )


def defaults(charge: Charge, records: Sequence[Record]) -> list[DefaultItem]:
    """A supplies charge's one default: a bill that adds up to the charge."""
    return [
        DefaultItem(
            key="bill", needed="A bill that adds up to the charge", amount_cents=charge.amount_cents
        )
    ]


def problems(
    new: Record, written: Sequence[Record], files: Sequence[EvidenceFile] = FILES
) -> list[str]:
    trigger = Trigger(kind=TriggerKind.CLOCK) if new.author == "agent" else None
    if new.author == "agent" and new.read_through_seq is None:
        new = new.model_copy(update={"read_through_seq": RUN_READ_THROUGH})
    return check_new_record(new, written, CHARGES, files, default_items=defaults, trigger=trigger)


def ids(records: Sequence[Record]) -> list[str]:
    return [r.id for r in records]


def sign_off(note: str | None = None) -> dict[str, Any]:
    """A stored sign-off, with what the server fills in."""
    totals = {
        "ledger_total_cents": 1200,
        "charges_total": 1,
        "charges_ready": 1,
        "accepted": 0,
        "reversed": 0,
        "bucket_counts": {"evidence_complete": 1},
    }
    snapshot = {
        "charges": [
            {"charge_id": "c1", "bucket": "evidence_complete", "accepted": False, "reversed": False}
        ],
        "problem_rows": [],
        "totals": totals,
    }
    return {
        "kind": "sign_off",
        "note": note,
        "report_path": "w/g/reports/s1.pdf",
        "report_sha256": "0" * 64,
        "snapshot": snapshot,
    }
