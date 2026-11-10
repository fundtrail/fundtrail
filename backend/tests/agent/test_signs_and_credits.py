"""Doubtful signs, credit memos, and a per diem filled only by rate math (issues #75 and #87).

Recorded replays: a fake model plays the agent's turns, and the real checks (app.checks) give
the buckets. Everything is synthetic.
"""

from dataclasses import replace
from datetime import date, datetime
from typing import Any

import pytest

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
from app.contracts.records import Bill, Link, Record
from app.contracts.runs import Trigger, TriggerKind

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


# Doubtful exactly where the quote finder accepts a value of either sign (its
# sign_reads_either_way, provisional call 31).
@pytest.mark.parametrize(
    ("passage", "value"),
    [
        ("Hotel - $612.40", "$612.40"),
        ("Refund \u2013 $45.00", "$45.00"),
        # Judged from the amount's place in the passage, whatever the value's text carries.
        ("Credit amount - $248.00", "- $248.00"),
        ("Credit amount - $248.00", "$248.00"),
        ("Credit amount - $248.00", "248.00"),
        # Any run of spaces or tabs after the dash.
        ("Hotel -    $612.40", "612.40"),
        ("Hotel -\t$612.40", "$612.40"),
        # A dash at the start of a line.
        ("Paid\n- $45.00", "$45.00"),
        # Any white space, not only a space or a tab (PR 105's recheck).
        ("Credit amount -\u00a0$248.00", "248.00"),
        ("Credit amount \u2009- $248.00", "248.00"),
        ("Credit amount -\u2009$248.00", "$248.00"),
        ("Credit\u00a0-\u00a0$248.00", "248.00"),
        # The finder reads these either way too, so the agent asks (the coordinator's call).
        ("Credit amount -- $248.00", "248.00"),
        ("Credit amount -- $248.00", "$248.00"),
        ("Credit- $248.00", "248.00"),
        ("Credit- $248.00", "$248.00"),
        ("Hotel- $612.40", "$612.40"),
        ("Year 2-\u00a0$50,000", "$50,000"),
        # A currency code between a spaced dash and the amount (ruling 3, the coordinator's call).
        ("Hotel \u2013 USD 612.40", "612.40"),
        ("Hotel - US$612.40", "612.40"),
        ("Credit amount \u2013 USD 248.00", "\u2013 USD 248.00"),
        ("Credit amount \u2013 usd 248.00", "248.00"),
    ],
)
def test_a_sign_that_reads_either_way_is_doubtful(passage: str, value: str):
    assert sign_is_doubtful(passage, value)


@pytest.mark.parametrize(
    ("passage", "value"),
    [
        ("Credit amount -$248.00", "-$248.00"),  # attached: clearly a minus (call 31)
        ("Total: -$450.00", "-$450.00"),
        ("\u2212 $45.00", "$45.00"),  # the true minus is always a minus
        ("Total: ($450.00)", "($450.00)"),  # brackets read as a minus
        ("Total:\u00a0($450.00)", "($450.00)"),
        ("Total Due: $1,240.00", "$1,240.00"),
        ("Year 2-$50,000", "$50,000"),  # a hyphen after a digit
        # The finder reads these one way, so they don't ask for a reason: brackets in prose
        # still read as a minus until the follow-up on prose brackets lands, and a line break
        # between the dash and the amount ends the dash's reach.
        ("the fee ($450.00) was paid", "($450.00)"),
        ("the fee, ($450.00), was paid", "($450.00)"),
        ("Credit amount -\n$248.00", "248.00"),
    ],
)
def test_a_sign_that_reads_one_way_is_not_doubtful(passage: str, value: str):
    assert not sign_is_doubtful(passage, value)


@pytest.mark.parametrize(
    ("passage", "value"),
    [
        ("Credit amount -- $248.00", "248.00"),
        ("Credit- $248.00", "$248.00"),
        ("Hotel \u2013 USD 612.40", "612.40"),
        ("Total: -$450.00", "-$450.00"),
        ("Hotel - $612.40", "$612.40"),
    ],
)
def test_doubt_is_the_quote_finders_own_reading(passage: str, value: str):
    """No separate rule: the agent's doubt is the finder's either-way, at the value's place."""
    from app.quotes.text_match import clean, sign_reads_either_way

    page = clean(passage).text
    at = page.index(value)
    assert sign_is_doubtful(passage, value) == sign_reads_either_way(page, at, at + len(value))


MEMO_NOW = datetime.fromisoformat("2025-12-01T18:00:00+00:00")
MEMO_DB = records_until("rec-bill-seq-0207")  # L-1001 linked, assigned and answered
MEMO_FILE = text_file("file-memo", "credit_memo_2001.txt", "2025-12-01T18:00:00+00:00")


def memo_run(
    total_text: str, cents: int, chunk: str = "Credit amount - $248.00", memo: str = MEMO
) -> tuple[RunSaved, list[Charge], list[EvidenceFile]]:
    """The agent reads CM-2001, cites its total as `total_text`, and links it to L-1001.

    Its first link has no reason, which is refused because the sign reads either way; the next
    gives the reason. Returns the run and what the checks need.
    """
    trigger = Trigger(kind=TriggerKind.FILE, id="file-memo")
    base = sample_inputs(now=MEMO_NOW, trigger=trigger, records=MEMO_DB)
    files = [*base.files, MEMO_FILE]
    inputs = replace(
        base,
        files=files,
        read_file=lambda f: (
            memo.encode() if f.id == "file-memo" else (DOCUMENTS_DIR / f.name).read_bytes()
        ),
        run_checks=run_checks,
        default_items=default_items,
        new_id=iter(["rec-bill-cm-2001", "rec-link-cm-2001", "rec-allowable-again"]).__next__,
    )
    link = {
        "record_id": "rec-bill-cm-2001",
        "charge_id": "chg-l-1001",
        "amount_cents": cents,
        "default_item": "bill",
    }

    def read(request: ModelRequest):
        return label_message(
            request,
            [
                ("cm_total", total_text, "file-memo", chunk),
                ("cm_number", "CM-2001", "file-memo", "CREDIT MEMO CM-2001"),
            ],
        )

    def write(request: ModelRequest):
        return calls(
            tool(
                "write_fact",
                kind="bill",
                values=[
                    {"field": "total", "label": "cm_total", "value": cents},
                    {"field": "document_number", "label": "cm_number"},
                ],
            ),
            tool("link", **link),
            tool("finish", summary="Read the credit memo."),
        )

    def give_reason(request: ModelRequest):
        results = results_of(request)
        assert not results[0].get("is_error"), results[0]
        assert "can be read either way" in results[0]["content"]
        assert results[1]["is_error"] and "say what you read the sign from" in results[1]["content"]
        reason = 'Read the sign from "CREDIT MEMO" and "Credits invoice INV-1001".'
        return calls(tool("link", **link, reason=reason), tool("finish", summary="Linked CM-2001."))

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
    return result, list(base.charges), files


def test_a_credit_memo_is_linked_with_its_negative_amount_and_its_sign_reason():
    assert (
        bucket(
            "chg-l-1001",
            MEMO_DB,
            list(SAMPLE.charges[:1]),
            [*SAMPLE.files[:2], MEMO_FILE],
            MEMO_NOW,
        )
        == Bucket.EVIDENCE_COMPLETE
    )
    result, charges, files = memo_run("- $248.00", -24800)
    bill, link, _ = result.records
    assert bill.data.total.value == -24800  # pyright: ignore[reportAttributeAccessIssue]
    assert link.data.amount_cents == -24800 and "credit memo" in (link.data.reason or "").lower()  # pyright: ignore[reportAttributeAccessIssue]
    # Linked before the ledger's credit line posts, the charge's bill item adds up to less than
    # the charge: the checks' own rule for a sum that's under gives Missing evidence.
    out = run_checks(
        ChecksInput(
            now=MEMO_NOW,
            charges=tuple(charges),
            files=tuple(files),
            records=(*MEMO_DB, *result.records),
        )
    )
    status = next(s for s in out.charges if s.charge_id == "chg-l-1001")
    assert status.bucket == Bucket.MISSING_EVIDENCE
    assert [
        (r.check, r.problem) for r in status.reasons if r.bucket == Bucket.MISSING_EVIDENCE
    ] == [("checklist", "missing:bill")]


def test_citing_only_the_digits_still_asks_where_the_sign_came_from():
    """The review's case: "248.00" cited out of "Credit amount - $248.00" carries no dash, but the
    amount's place in the passage still reads either way, so the link still needs a reason."""
    result, _, _ = memo_run("248.00", 24800)
    bill, link, _ = result.records
    assert isinstance(bill.data, Bill) and isinstance(link.data, Link)
    assert bill.data.total.value == 24800  # the agent's reading stands
    assert "sign" in (link.data.reason or "")


def test_a_non_breaking_space_after_the_dash_still_asks_where_the_sign_came_from():
    """PR 105's recheck: "Credit amount -\u00a0$248.00" cited as "248.00", end to end."""
    line = "Credit amount -\u00a0$248.00"
    memo = MEMO.replace("Credit amount - $248.00", line)
    result, _, _ = memo_run("248.00", 24800, chunk=line, memo=memo)
    bill, link, _ = result.records
    assert isinstance(bill.data, Bill) and isinstance(link.data, Link)
    assert "sign" in (link.data.reason or "")


def test_the_ledgers_credit_line_brings_the_charge_back():
    result, charges, files = memo_run("- $248.00", -24800)
    credit_line = SAMPLE.charges[0].model_copy(
        update={
            "id": "chg-l-1003",
            "ledger_line_id": "L-1003",
            "amount_cents": -24800,
            "description": "Credit, damaged liners",
            "reference": "CM-2001",
            "original_line_id": "L-1001",
            "transaction_date": date(2025, 12, 3),
            "posting_date": date(2025, 12, 5),
            "arrived_at": datetime.fromisoformat("2025-12-05T00:00:00+00:00"),
        }
    )
    later = datetime.fromisoformat("2025-12-05T12:00:00+00:00")
    records = [*MEMO_DB, *result.records]
    assert (
        bucket("chg-l-1001", records, [*charges, credit_line], files, later)
        == Bucket.EVIDENCE_COMPLETE
    )


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


# Code's reading of the money and the finder's reading of the page agree on the sign.


@pytest.mark.parametrize(("text", "cents"), [("\u2013 USD 248.00", -24800), ("USD 248.00", 24800)])
def test_a_code_after_a_spaced_dash_takes_either_sign_and_asks_for_the_reason(
    text: str, cents: int
):
    """PR 105's review: "Credit amount \u2013 USD 248.00" cited as "\u2013 USD 248.00" parsed as
    -$248.00 while the finder read it positive, and was saved with no reason. Now the finder reads
    it either way: both signs are saved, and the link asks where the sign came from."""
    line = "Credit amount \u2013 USD 248.00"
    memo = MEMO.replace("Credit amount - $248.00", line)
    result, _, _ = memo_run(text, cents, chunk=line, memo=memo)
    bill, link, _ = result.records
    assert isinstance(bill.data, Bill) and isinstance(link.data, Link)
    assert bill.data.total.value == cents
    assert "sign" in (link.data.reason or "")


def test_money_whose_sign_disagrees_with_the_finder_is_refused(monkeypatch: pytest.MonkeyPatch):
    """Positive needs at least 0 and negative needs less than 0; either way allows both."""
    from app.agent import citations
    from app.quotes.text_match import EITHER, NEGATIVE, POSITIVE

    for sign, cents, agrees in [
        (POSITIVE, 24800, True),
        (POSITIVE, -24800, False),
        (NEGATIVE, -24800, True),
        (NEGATIVE, 24800, False),
        (EITHER, 24800, True),
        (EITHER, -24800, True),
    ]:
        monkeypatch.setattr(citations, "amount_sign", lambda *a, s=sign: s)  # pyright: ignore[reportUnknownLambdaType]
        assert citations.money_sign_agrees(cents, "Total: $248.00", "$248.00") is agrees
