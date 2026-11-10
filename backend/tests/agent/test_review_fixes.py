"""The fixes from the review of PR 49 and the main coordinator's rulings, one test each."""

import json
from datetime import datetime
from typing import Any

import pytest
from anthropic.types import CitationCharLocation

from app.agent import RunFailed, RunSaved, run_once
from app.agent import citations as citations_module
from app.agent import graph as graph_module
from app.agent.citations import LabelLine, SentDocument, resolve_citation, value_lines
from app.agent.context import RunContext
from app.agent.desk import first_message
from app.agent.fields import FACT_FIELDS
from app.agent.files import open_file
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool, tool_definitions
from app.contracts.fixtures import DOCUMENTS_DIR, load_sample_grant
from app.contracts.records import Record
from app.contracts.runs import Trigger
from app.contracts.threads import ThreadMessage
from app.quotes.types import HighlightRect, PdfQuoteMatch, QuoteOccurrence

from .fakes import FakeModel, calls, label_message, message, results_of, sample_inputs, text, tool

SAMPLE = load_sample_grant()
INVOICE = SAMPLE.document("file-invoice-1001")
AWARD = SAMPLE.document("file-award-letter")


def records_until(record_id: str) -> list[Record]:
    out: list[Record] = []
    for r in SAMPLE.records:
        if r.id == record_id:
            break
        out.append(r)
    return out


def invoice_context() -> RunContext:
    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-12T18:00:00+00:00"),
        trigger=Trigger(kind="file", id="file-invoice-1001"),  # pyright: ignore[reportArgumentType]
        records=records_until("rec-bill-inv-1001"),
    )
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook())
    _, error = run_tool(ctx, "open_file", {"file_id": "file-invoice-1001"})
    assert not error
    return ctx


def label(ctx: RunContext, name: str, value: str, chunk: str) -> None:
    start = INVOICE.find(chunk)
    cite = CitationCharLocation(
        type="char_location",
        cited_text=chunk,
        document_index=0,
        start_char_index=start,
        end_char_index=start + len(chunk),
    )
    ctx.labels[name] = LabelLine(label=name, text=value, citations=[cite])


HEAD = "Invoice Number: INV-1001\nInvoice Date: November 12, 2025"


# 1. A value has to come from its own text (trust rules 2 and 3).


@pytest.mark.parametrize(
    ("field", "value", "label_text", "chunk", "problem"),
    [
        ("total", 9999999, "INV-1001", HEAD, "can't be read as an amount of money"),
        ("dated", "2020-01-01", "INV-1001", HEAD, "can't be read as a date"),
        ("document_number", "INV-9999", "INV-1001", HEAD, "a text value is the text"),
        ("total", 12400, "$1,24", "Total Due: $1,240.00", "none of the passages"),
        # The right amount, cut from a longer number on the page.
        ("total", 24000, "240.00", "Total Due: $1,240.00", "none of the passages"),
        ("dated", "2025-11-13", "November 12, 2025", HEAD, "doesn't match its text"),
        ("total", 124001, "$1,240.00", "Total Due: $1,240.00", "doesn't match its text"),
    ],
)
def test_a_value_has_to_come_from_its_own_text(
    field: str, value: Any, label_text: str, chunk: str, problem: str
):
    ctx = invoice_context()
    label(ctx, "v", label_text, chunk)
    values = [{"field": field, "label": "v", "value": value}]
    if field != "total":
        label(ctx, "t", "$1,240.00", "Total Due: $1,240.00")
        values.append({"field": "total", "label": "t"})
    result, error = run_tool(ctx, "write_fact", {"kind": "bill", "values": values})
    assert error and problem in result, result
    assert not ctx.staged


def test_quantities_and_rates_are_checked_against_their_text():
    ctx = invoice_context()
    label(ctx, "count", "50", "Sediment core liners, 50 count: $1,240.00")
    args: dict[str, Any] = {
        "charge_id": "chg-l-1001",
        "needed": "Packing slip",
        "rate": {
            "quantity": {"field": "quantity", "label": "count", "value": "51"},
            "rate_id": "x",
        },
    }
    result, error = run_tool(ctx, "add_checklist_item", args)
    assert error and "doesn't match its text" in result
    from app.agent.citations import parse_quantity, parse_rate

    assert str(parse_rate("36.6%")) == "0.366" and parse_rate("$100 a day") == 10000
    assert parse_quantity("5 days") == 5 and parse_quantity("INV-1001") is None


# 2. Thread runs reply and suggest.


def thread_inputs(text_in: str, db: list[Record]):
    msg = ThreadMessage(
        id="msg-1",
        workspace_id=SAMPLE.workspace.id,
        grant_id=SAMPLE.grant.id,
        charge_id="chg-l-1001",
        author="user",  # pyright: ignore[reportArgumentType]
        author_user_id=SAMPLE.user.id,
        text=text_in,
        written_at=datetime.fromisoformat("2025-11-14T12:00:00+00:00"),
    )
    return sample_inputs(
        now=datetime.fromisoformat("2025-11-14T12:00:00+00:00"),
        trigger=Trigger(kind="thread_message", id="msg-1"),  # pyright: ignore[reportArgumentType]
        records=db,
        thread_messages=[msg],
    )


def test_please_link_this_in_a_thread_gives_a_link_that_waits():
    model = FakeModel(
        [
            lambda r: calls(
                tool(
                    "link",
                    record_id="rec-bill-inv-1001",
                    charge_id="chg-l-1001",
                    amount_cents=124000,
                    default_item="bill",
                ),
                tool("post_message", charge_id="chg-l-1001", text="Linked; it waits for you."),
                tool("finish", summary="Suggested the link."),
            )
        ]
    )
    result = run_once(
        thread_inputs("Please link INV-1001.", records_until("rec-link-l-1001")), model
    )
    assert isinstance(result, RunSaved) and [r.kind for r in result.records] == ["link"]
    link_result = results_of_turn(result, "link")
    assert "waits for the accountant" in link_result
    prompt = " ".join(model.requests[0].messages[0]["content"][-1]["text"].split())
    assert "every record you write waits for the accountant, whatever its kind" in prompt


def results_of_turn(result: RunSaved, name: str) -> str:
    return next(
        e["result"] for e in result.log["events"] if e["event"] == "tool" and e["name"] == name
    )


def test_a_question_that_needs_no_change_gives_a_message_and_no_record():
    model = FakeModel(
        [
            lambda r: calls(
                tool("post_message", charge_id="chg-l-1001", text="Yes, INV-1001 matches."),
                tool("finish", summary="Replied."),
            )
        ]
    )
    result = run_once(
        thread_inputs("Is this the right invoice?", records_until("rec-allowable-l-1001")), model
    )
    assert isinstance(result, RunSaved) and result.records == []
    assert [m.text for m in result.messages] == ["Yes, INV-1001 matches."]


def test_an_open_question_on_the_threads_charge_goes_to_an_ordinary_run():
    """The thread run isn't held up: the open Allowable question comes back for the platform."""
    model = FakeModel(
        [
            lambda r: calls(
                tool("post_message", charge_id="chg-l-1001", text="Looking."),
                tool("finish", summary="x"),
            )
        ]
    )
    result = run_once(
        thread_inputs("Anything missing?", records_until("rec-allowable-l-1001")), model
    )
    assert isinstance(result, RunSaved)
    assert [(q.charge_id, q.question) for q in result.other_open_questions] == [
        ("chg-l-1001", "allowable")
    ]
    assert len(model.requests) == 1


# 3. Highlights: one range per line, and each PDF box on its own page.


def test_each_line_stating_a_repeated_value_is_its_own_range():
    start = AWARD.find("FUNDING INFORMATION")
    end = AWARD.find("PROJECT PERSONNEL")
    lines = [AWARD[s:e] for s, e in value_lines(AWARD, start, end, "$120,000")]
    assert lines == [
        "Amount Obligated by this Amendment: $120,000",
        "Total Intended Award Amount: $120,000",
        "Total Amount Obligated to Date: $120,000",
    ]
    assert "Cost Share: $0" not in lines


def test_a_pdf_highlight_takes_each_boxs_own_page(monkeypatch: pytest.MonkeyPatch):
    occurrence = QuoteOccurrence(
        rects=(HighlightRect(1, 0.1, 0.9, 0.5, 0.95), HighlightRect(2, 0.1, 0.05, 0.5, 0.1)),
        matched_text="across the break $450.00",
        value_found=True,
    )
    found = PdfQuoteMatch(
        match="exact", method="exact", occurrences=(occurrence,), value_found=True
    )
    monkeypatch.setattr(citations_module, "find_pdf_quote", lambda *a, **k: found)  # pyright: ignore[reportUnknownLambdaType]
    raw = {
        "type": "page_location",
        "cited_text": "across the break $450.00",
        "document_index": 0,
        "start_page_number": 1,
        "end_page_number": 3,
    }
    c = resolve_citation("$450.00", [raw], [SentDocument("file-pdf", "pdf", pdf=b"%PDF")])
    assert [box["page"] for box in c["highlight"]] == [1, 2]


# 4. A refused write in the finishing turn goes back to the model.


def test_a_refused_write_with_finish_goes_back_to_the_model():
    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-14T00:00:00+00:00"),
        trigger=Trigger(kind="charge", id="chg-l-1001"),  # pyright: ignore[reportArgumentType]
        records=records_until("rec-bill-seq-0207"),
        charge_ids=["chg-l-1001"],
    )
    model = FakeModel(
        [
            lambda r: calls(
                tool("link", record_id="rec-nope", charge_id="chg-l-1001"),
                tool("finish", summary="x"),
            ),
            lambda r: calls(tool("finish", summary="Done.")),
        ]
    )
    result = run_once(inputs, model)
    assert isinstance(result, RunSaved) and result.summary == "Done."
    finish = results_of(model.requests[1])[-1]
    assert finish["is_error"] and "a write in this turn was refused" in finish["content"]


# 5. The field guide lists a bill's items.


def test_the_field_guide_lists_bill_items():
    assert "items[i].description (cited text); items[i].amount (cited money)" in FACT_FIELDS


# 6. The desk uses the actual sums.


def test_a_link_with_no_amount_isnt_shown_as_zero():
    from app.agent.desk import bill_line, money_nobody_charged

    db = records_until("rec-budget-l-1001")
    bill = next(r for r in db if r.id == "rec-bill-inv-1001")
    link = next(r for r in db if r.id == "rec-link-l-1001")
    no_amount = link.model_copy(
        update={"data": link.data.model_copy(update={"amount_cents": None})}
    )
    from app.contracts.rules import RecordState

    state = RecordState([*db[:-1], no_amount], SAMPLE.files)
    assert "1 link(s) with no amount" in bill_line(state, bill)
    assert money_nobody_charged(state, bill) is None
    assert money_nobody_charged(RecordState(db, SAMPLE.files), bill) == 0


# Nits and missing tests.


def test_a_model_that_never_finishes_fails_the_run(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(graph_module, "MAX_TURNS", 3)
    model = FakeModel([lambda r: calls(tool("list_charges"))] * 3)
    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-14T00:00:00+00:00"),
        trigger=Trigger(kind="file", id="file-invoice-1001"),  # pyright: ignore[reportArgumentType]
        records=records_until("rec-link-l-1001"),
    )
    result = run_once(inputs, model)
    assert isinstance(result, RunFailed) and "more than 3 model turns" in result.error


@pytest.mark.parametrize("stop", ["pause_turn", "model_context_window_exceeded"])
def test_a_stop_that_isnt_a_finish_fails_the_run(stop: str):
    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-14T00:00:00+00:00"),
        trigger=Trigger(kind="file", id="file-invoice-1001"),  # pyright: ignore[reportArgumentType]
        records=records_until("rec-link-l-1001"),
    )
    result = run_once(inputs, FakeModel([lambda r: message(text("..."), stop=stop)]))
    assert isinstance(result, RunFailed) and stop in result.error


def test_the_larger_output_limit_is_for_the_retried_turn_only():
    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-14T00:00:00+00:00"),
        trigger=Trigger(kind="file", id="file-invoice-1001"),  # pyright: ignore[reportArgumentType]
        records=records_until("rec-link-l-1001"),
    )
    model = FakeModel(
        [
            lambda r: message(text("..."), stop="max_tokens"),
            lambda r: calls(tool("list_charges")),
            lambda r: message(text("..."), stop="max_tokens"),
            lambda r: message(text("Done.")),
        ]
    )
    assert isinstance(run_once(inputs, model), RunSaved)
    limits = [r.max_tokens for r in model.requests]
    assert limits[0] == limits[2] < limits[1] == limits[3]


def test_the_agent_has_no_way_to_set_a_status_or_write_the_accountants_kinds():
    tools = tool_definitions()
    assert not any("status" in t["name"] for t in tools)
    schemas = json.dumps([t["input_schema"] for t in tools])
    for kind in ("confirmation", "accepted_reason", "snooze", "sign_off", "bucket"):
        assert f'"{kind}"' not in schemas
    ctx = invoice_context()
    for tool_name, kind in [
        ("write_fact", "confirmation"),
        ("write_term", "sign_off"),
        ("write_fact", "snooze"),
    ]:
        result, error = run_tool(ctx, tool_name, {"kind": kind, "values": []})
        assert error and "doesn't fit" in result
    result, error = run_tool(
        ctx, "set_status", {"charge_id": "chg-l-1001", "bucket": "evidence_complete"}
    )
    assert error and not ctx.staged


def test_a_label_already_used_is_refused_not_overwritten():
    def read(request: Any):
        return label_message(
            request, [("total", "$1,240.00", "file-invoice-1001", "Total Due: $1,240.00")]
        )

    def again(request: Any):
        assert "Recorded with citations: total." == request.messages[-1]["content"]
        return label_message(
            request, [("total", "INV-1001", "file-invoice-1001", "Invoice Number: INV-1001")]
        )

    def write(request: Any):
        assert "Already used in this run" in request.messages[-1]["content"]
        return calls(
            tool("write_fact", kind="bill", values=[{"field": "total", "label": "total"}]),
            tool("finish", summary="Read it."),
        )

    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-12T18:00:00+00:00"),
        trigger=Trigger(kind="file", id="file-invoice-1001"),  # pyright: ignore[reportArgumentType]
        records=records_until("rec-bill-inv-1001"),
    )
    result = run_once(inputs, FakeModel([read, again, write]))
    assert isinstance(result, RunSaved)
    assert result.records[0].data.total.value == 124000  # pyright: ignore[reportAttributeAccessIssue]


def test_an_image_is_sent_so_the_api_errors_rather_than_resize_it():
    from io import BytesIO

    from PIL import Image

    out = BytesIO()
    Image.new("RGB", (4000, 1000), "white").save(out, format="PNG")
    photo = SAMPLE.files[1].model_copy(
        update={
            "id": "file-photo",
            "name": "photo.png",
            "media_type": "image/png",
            "storage_path": "x",
        }
    )
    opened = open_file(photo, out.getvalue())
    block = next(b for b in opened.blocks if b["type"] == "image")
    assert block["transformations"] == {"oversized_image": "error"}
    assert opened.image is not None and max(opened.image.width, opened.image.height) == 2576


def test_no_file_contents_go_in_the_debug_log():
    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-12T18:00:00+00:00"),
        trigger=Trigger(kind="file", id="file-invoice-1001"),  # pyright: ignore[reportArgumentType]
        records=records_until("rec-bill-inv-1001"),
    )
    result = run_once(inputs, FakeModel([lambda r: message(text("Done."))]))
    logged = json.dumps(result.log)
    assert "Total Due" not in logged and "omitted_bytes" in logged
    assert (DOCUMENTS_DIR / "invoice_1001.txt").read_text().count("Total Due") == 1
    from app.agent.context import _loggable  # pyright: ignore[reportPrivateUsage]

    short = _loggable({"source": {"type": "text", "data": "Total: $5"}})
    assert "Total: $5" not in json.dumps(short)  # short files too, not only long ones
    assert first_message  # the desk still sent the file to the model


def test_award_notice_guidance_says_what_an_approval_rule_applies_to():
    """The main coordinator's ruling: every_charge or moved_out, read from the clause and cited;
    an unclear clause is flagged, not picked. The field itself arrives with #39."""
    from app.agent.desk import AWARD_NOTICE_GUIDANCE

    flat = " ".join(AWARD_NOTICE_GUIDANCE.split())
    assert "every_charge" in flat and "moved_out" in flat
    assert "may not be diverted" in flat and "every equipment purchase" in flat
    assert "don't pick one: flag the term" in flat
    assert "moves participant support money" in flat and "nsf_standing_list" in flat
