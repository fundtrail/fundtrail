"""Doubtful signs, credit memos, and a per diem filled only by rate math (issues #75 and #87).

Recorded replays: a fake model plays the agent's turns, and the real checks (app.checks) give
the buckets. Everything is synthetic.
"""

from dataclasses import replace
from datetime import date, datetime
from typing import Any

from app.agent import RunSaved, run_once
from app.agent.citations import sign_is_doubtful
from app.agent.model import ModelRequest
from app.agent.prompts import SYSTEM_PROMPT
from app.checks.checklist import default_items
from app.checks.run import run_checks
from app.contracts.charges import Charge
from app.contracts.checks import Bucket, ChecksInput
from app.contracts.evidence import EvidenceFile
from app.contracts.fixtures import DOCUMENTS_DIR, load_sample_grant
from app.contracts.records import Record
from app.contracts.runs import Trigger

from .fakes import FakeModel, calls, label_message, results_of, sample_inputs, tool

SAMPLE = load_sample_grant()
ACCOUNTANT = SAMPLE.user.id


def records_until(record_id: str) -> list[Record]:
    out: list[Record] = []
    for r in SAMPLE.records:
        if r.id == record_id:
            break
        out.append(r)
    return out


def text_file(file_id: str, name: str, arrived: str) -> EvidenceFile:
    return SAMPLE.files[1].model_copy(
        update={
            "id": file_id,
            "name": name,
            "storage_path": f"{SAMPLE.workspace.id}/{SAMPLE.grant.id}/{file_id}/{name}",
            "sha256": file_id,
            "arrived_at": datetime.fromisoformat(arrived),
        }
    )


def bucket(
    charge_id: str,
    records: list[Record],
    charges: list[Charge],
    files: list[EvidenceFile],
    now: datetime,
):
    out = run_checks(
        ChecksInput(now=now, charges=tuple(charges), files=tuple(files), records=tuple(records))
    )
    return next(s.bucket for s in out.charges if s.charge_id == charge_id)


# A doubtful sign, and a credit memo linked before the ledger's credit line posts.

MEMO = (
    "SYNTHETIC DEMO DOCUMENT. Created for the FundTrail sample grant.\n\n"
    "Example Lab Supply Co.\n"
    "CREDIT MEMO CM-2001\n"
    "Credits invoice INV-1001 for 10 damaged liners.\n\n"
    "Credit amount - $248.00\n"
)


def test_a_spaced_dash_is_a_doubtful_sign_and_an_attached_one_is_not():
    assert sign_is_doubtful("Hotel - $612.40", "$612.40")
    assert sign_is_doubtful("Credit amount - $248.00", "- $248.00")
    assert sign_is_doubtful("Refund – $45.00", "$45.00")
    assert not sign_is_doubtful("Credit amount -$248.00", "-$248.00")
    assert not sign_is_doubtful("Total Due: $1,240.00", "$1,240.00")
    assert not sign_is_doubtful("Year 2-$50,000", "$50,000")


def test_a_credit_memo_is_linked_with_its_negative_amount_and_its_sign_reason():
    now = datetime.fromisoformat("2025-12-01T18:00:00+00:00")
    memo = text_file("file-memo", "credit_memo_2001.txt", "2025-12-01T18:00:00+00:00")
    db = records_until("rec-bill-seq-0207")  # L-1001 linked, assigned and answered
    base = sample_inputs(now=now, trigger=Trigger(kind="file", id="file-memo"), records=db)  # pyright: ignore[reportArgumentType]
    files = [*base.files, memo]
    inputs = replace(
        base,
        files=files,
        read_file=lambda f: (
            MEMO.encode() if f.id == "file-memo" else (DOCUMENTS_DIR / f.name).read_bytes()
        ),
        run_checks=run_checks,
        default_items=default_items,
        new_id=iter(["rec-bill-cm-2001", "rec-link-cm-2001", "rec-allowable-again"]).__next__,
    )
    assert bucket("chg-l-1001", db, list(base.charges), files, now) == Bucket.EVIDENCE_COMPLETE

    def read(request: ModelRequest):
        return label_message(
            request,
            [
                ("cm_total", "- $248.00", "file-memo", "Credit amount - $248.00"),
                ("cm_number", "CM-2001", "file-memo", "CREDIT MEMO CM-2001"),
            ],
        )

    def write(request: ModelRequest):
        return calls(
            tool(
                "write_fact",
                kind="bill",
                values=[
                    {"field": "total", "label": "cm_total", "value": -24800},
                    {"field": "document_number", "label": "cm_number"},
                ],
            ),
            tool(
                "link",
                record_id="rec-bill-cm-2001",
                charge_id="chg-l-1001",
                amount_cents=-24800,
                default_item="bill",
            ),
            tool("finish", summary="Read the credit memo."),
        )

    def give_reason(request: ModelRequest):
        results = results_of(request)
        assert "can be read either way" in results[0]["content"]
        assert results[1]["is_error"] and "say what you read the sign from" in results[1]["content"]
        return calls(
            tool(
                "link",
                record_id="rec-bill-cm-2001",
                charge_id="chg-l-1001",
                amount_cents=-24800,
                default_item="bill",
                reason='Read the sign from "CREDIT MEMO" and "Credits invoice INV-1001".',
            ),
            tool("finish", summary="Linked the credit memo to L-1001."),
        )

    def answer_again(request: ModelRequest):
        # The new link makes the charge's Allowable answer out of date, so the gate asks again.
        finish = results_of(request)[-1]
        assert finish["is_error"] and "allowable on charge chg-l-1001" in finish["content"]
        return calls(
            tool(
                "answer",
                charge_id="chg-l-1001",
                question="allowable",
                answer="supports",
                reasoning="The liners are for the survey; ten damaged ones were credited back.",
            ),
            tool("finish", summary="Linked the credit memo to L-1001."),
        )

    result = run_once(inputs, FakeModel([read, write, give_reason, answer_again]))
    assert isinstance(result, RunSaved), getattr(result, "error", result)
    bill, link, _ = result.records
    assert bill.data.total.value == -24800  # pyright: ignore[reportAttributeAccessIssue]
    assert link.data.amount_cents == -24800 and "credit memo" in (link.data.reason or "").lower()  # pyright: ignore[reportAttributeAccessIssue]
    # Linked before the ledger's credit line posts: the charge waits for it with the accountant.
    after = bucket("chg-l-1001", [*db, *result.records], list(base.charges), files, now)
    assert after != Bucket.EVIDENCE_COMPLETE


def test_the_prompt_says_how_to_link_a_credit_memo_and_report_a_doubtful_sign():
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "link it to that charge with its own negative amount" in flat
    assert "A memo that names no invoice or charge: link nothing" in flat
    assert "say in the link's reason what you read the sign from" in flat


# A per diem filled only by rate math (PR 91's nit).

TRAVEL = "57211 In-State Travel - Air Fare"
PER_DIEM = "Per diem: 5 days at $100 a day"


def _record(id: str, author: str, data: dict[str, Any], when: datetime) -> Record:
    envelope: dict[str, Any] = {
        "id": id,
        "workspace_id": SAMPLE.workspace.id,
        "grant_id": SAMPLE.grant.id,
        "author": author,
        "written_at": when,
        "data": data,
    }
    if author == "user":
        envelope["author_user_id"] = ACCOUNTANT
    return Record.model_validate(envelope)


def _cited(value: Any, text: str) -> dict[str, Any]:
    """A value cited from the trip memo's one line."""
    assert text in PER_DIEM
    location = {"type": "char_location", "start_char_index": 0, "end_char_index": len(PER_DIEM)}
    citation = {"file_id": "file-trip", "passage": PER_DIEM, "location": location, "match": "exact"}
    return {"value": value, "text": text, "citation": citation}


def test_a_per_diem_filled_only_by_rate_math_leaves_evidence_complete_when_flagged():
    now = datetime.fromisoformat("2025-11-20T12:00:00+00:00")
    when = datetime.fromisoformat("2025-11-20T00:00:00+00:00")
    trip = text_file("file-trip", "trip_memo.txt", "2025-11-19T00:00:00+00:00")
    charge = SAMPLE.charges[0].model_copy(
        update={
            "id": "chg-diem",
            "ledger_line_id": "L-3001",
            "transaction_date": date(2025, 11, 18),
            "posting_date": date(2025, 11, 19),
            "arrived_at": datetime.fromisoformat("2025-11-19T00:00:00+00:00"),
            "amount_cents": 50000,
            "description": "Per diem, field trip",
            "account": TRAVEL,
            "vendor": None,
            "reference": None,
        }
    )
    confirmed = [r for r in SAMPLE.records[:11]]
    looked_at = [
        _record(
            "rec-line-travel",
            "user",
            {
                "kind": "budget_line",
                "dated": {"value": "2023-01-10"},
                "name": {"value": "Travel"},
                "amount": {"value": 1000000},
                "category": "travel",
            },
            when,
        ),
        _record(
            "rec-diem-budget",
            "agent",
            {
                "kind": "budget_assignment",
                "charge_id": "chg-diem",
                "record_id": "rec-line-travel",
                "reason": "A trip.",
            },
            when,
        ),
        _record(
            "rec-diem-item",
            "agent",
            {
                "kind": "checklist_item",
                "charge_id": "chg-diem",
                "needed": "Per diem, 5 days at $100 a day",
                "amount_cents": 50000,
                "rate": {"quantity": _cited("5", "5 days"), "rate": _cited("10000", "$100 a day")},
            },
            when,
        ),
        _record(
            "rec-diem-removal",
            "user",
            {
                "kind": "checklist_removal",
                "charge_id": "chg-diem",
                "default_item": "expense_report",
            },
            when,
        ),
    ]
    db = [*confirmed, *looked_at]
    files = [*SAMPLE.files[:1], trip]
    assert bucket("chg-diem", db, [charge], files, now) == Bucket.EVIDENCE_COMPLETE

    inputs = replace(
        sample_inputs(now=now, trigger=Trigger(kind="charge", id="chg-diem"), records=db),  # pyright: ignore[reportArgumentType]
        charges=[charge],
        files=files,
        charge_ids=["chg-diem"],
        read_file=lambda f: (
            PER_DIEM.encode() if f.id == "file-trip" else (DOCUMENTS_DIR / f.name).read_bytes()
        ),
        run_checks=run_checks,
        default_items=default_items,
    )
    flag = tool(
        "flag",
        charge_id="chg-diem",
        question="Does a 5-day per diem fit this trip?",
        reasoning="The trip memo's dates cover three days, not five.",
    )
    result = run_once(
        inputs, FakeModel([lambda r: calls(flag, tool("finish", summary="Flagged the per diem."))])
    )
    assert isinstance(result, RunSaved), getattr(result, "error", result)
    assert bucket("chg-diem", [*db, *result.records], [charge], files, now) == Bucket.NEEDS_HUMAN
