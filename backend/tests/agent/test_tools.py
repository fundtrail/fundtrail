"""The write tools against the contract's write check, one tool call at a time."""

from datetime import datetime
from typing import Any

from anthropic.types import CitationCharLocation

from app.agent.citations import LabelLine
from app.agent.context import REPEAT_LIMIT, RunContext
from app.agent.inputs import batch_charge_ids
from app.agent.rulebook import load_rulebook, parse_rulebook
from app.agent.tools import run_tool, tool_definitions
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import Record
from app.contracts.runs import Trigger

from .fakes import sample_inputs

SAMPLE = load_sample_grant()
BY_ID = {r.id: r for r in SAMPLE.records}
INVOICE = SAMPLE.document("file-invoice-1001")


def records_until(record_id: str) -> list[Record]:
    out: list[Record] = []
    for r in SAMPLE.records:
        if r.id == record_id:
            return out
        out.append(r)
    return out


def context(
    now: str = "2025-11-14T00:00:00+00:00", until: str = "rec-link-l-1001", **extra: Any
) -> RunContext:
    inputs = sample_inputs(
        now=datetime.fromisoformat(now),
        trigger=Trigger(kind="charge", id="chg-l-1001"),  # pyright: ignore[reportArgumentType]
        records=records_until(until),
        charge_ids=["chg-l-1001"],
        **extra,
    )
    return RunContext(inputs=inputs, rulebook=load_rulebook())


def open_invoice(ctx: RunContext) -> None:
    content, error = run_tool(ctx, "open_file", {"file_id": "file-invoice-1001"})
    assert not error and any(b.get("type") == "document" for b in content)


def label(ctx: RunContext, name: str, value: str, chunk: str | None, index: int = 0) -> None:
    cites = []
    if chunk is not None:
        start = INVOICE.find(chunk)
        cites = [
            CitationCharLocation(
                type="char_location",
                cited_text=chunk,
                document_index=index,
                start_char_index=start,
                end_char_index=start + len(chunk),
            )
        ]
    ctx.labels[name] = LabelLine(label=name, text=value, citations=cites)


def test_every_tool_has_a_plain_json_schema():
    tools = tool_definitions()
    assert {t["name"] for t in tools} >= {
        "write_fact",
        "write_term",
        "link",
        "answer",
        "flag",
        "finish",
    }
    for t in tools:
        assert "$defs" not in str(t["input_schema"]) and "$ref" not in str(t["input_schema"])


def test_a_bill_is_staged_with_its_citations_and_takes_effect():
    ctx = context(until="rec-bill-inv-1001", now="2025-11-12T18:00:00+00:00")
    open_invoice(ctx)
    label(ctx, "total", "$1,240.00", "Total Due: $1,240.00")
    label(ctx, "number", "INV-1001", "Example Lab Supply Co.\nINVOICE\nInvoice Number: INV-1001")
    result, error = run_tool(
        ctx,
        "write_fact",
        {
            "kind": "bill",
            "values": [
                {"field": "total", "label": "total", "value": 124000},
                {"field": "document_number", "label": "number"},
            ],
        },
    )
    assert not error, result
    assert "takes effect" in result
    data = ctx.staged[-1].record.data
    assert data.total.value == 124000  # pyright: ignore[reportAttributeAccessIssue]
    number = data.document_number  # pyright: ignore[reportAttributeAccessIssue]
    assert number is not None and number.citation is not None
    assert number.citation.passage == "Invoice Number: INV-1001"


def test_a_value_that_doesnt_match_its_text_is_refused():
    ctx = context(until="rec-bill-inv-1001", now="2025-11-12T18:00:00+00:00")
    open_invoice(ctx)
    label(ctx, "total", "$1,240.00", "Total Due: $1,240.00")
    result, error = run_tool(
        ctx,
        "write_fact",
        {"kind": "bill", "values": [{"field": "total", "label": "total", "value": "124"}]},
    )
    assert error and "doesn't match its text" in result and not ctx.staged


def test_a_label_never_written_is_refused():
    ctx = context(until="rec-bill-inv-1001", now="2025-11-12T18:00:00+00:00")
    result, error = run_tool(
        ctx, "write_fact", {"kind": "bill", "values": [{"field": "total", "label": "nope"}]}
    )
    assert error and "message of their own" in result


def test_an_uncited_value_is_refused_then_accepted_as_uncited_which_the_contract_still_refuses():
    """Answer 1. The contract (#14) doesn't take an uncited agent value yet, so the last write is
    refused by the contract's own rule. Once #14 allows it, this expects an unconfirmed value."""
    ctx = context(until="rec-bill-inv-1001", now="2025-11-12T18:00:00+00:00")
    open_invoice(ctx)
    label(ctx, "total", "$1,240.00", None)
    args = {"kind": "bill", "values": [{"field": "total", "label": "total"}]}
    for _ in range(REPEAT_LIMIT - 1):
        result, error = run_tool(ctx, "write_fact", args)
        assert error and "came back with no citation" in result
    result, error = run_tool(ctx, "write_fact", args)
    assert error and "needs a citation" in result
    assert any(e["event"] == "uncited_accepted" for e in ctx.log["events"])
    assert not ctx.staged


def test_the_same_problem_three_times_suggests_a_flag():
    ctx = context()
    args = {
        "record_id": "rec-nope",
        "charge_id": "chg-l-1001",
        "part": {"record_id": "rec-bill-inv-1001", "field": "total"},
    }
    results = [run_tool(ctx, "link", args) for _ in range(REPEAT_LIMIT)]
    assert all(error for _, error in results)
    assert "flag" not in results[0][0] and "flag" in results[-1][0]


def test_a_link_takes_the_bills_total_as_its_part_by_default():
    ctx = context()
    result, error = run_tool(
        ctx,
        "link",
        {
            "record_id": "rec-bill-inv-1001",
            "charge_id": "chg-l-1001",
            "amount_cents": 124000,
            "default_item": "bill",
        },
    )
    assert not error, result
    assert ctx.staged[-1].record.data.part == BY_ID["rec-link-l-1001"].data.part  # pyright: ignore[reportAttributeAccessIssue]


def test_a_second_link_between_the_same_bill_and_charge_waits():
    ctx = context(until="rec-budget-l-1001")
    result, error = run_tool(
        ctx,
        "link",
        {
            "record_id": "rec-bill-inv-1001",
            "charge_id": "chg-l-1001",
            "amount_cents": 124000,
            "default_item": "bill",
        },
    )
    assert not error and "waits for the accountant" in result


def test_only_a_question_code_asked_can_be_answered():
    ctx = context(until="rec-link-l-1001")
    result, error = run_tool(
        ctx,
        "answer",
        {
            "charge_id": "chg-l-1001",
            "question": "allowable",
            "answer": "supports",
            "reasoning": "Fine.",
        },
    )
    assert error and "code hasn't asked" in result
    ctx = context(until="rec-budget-l-1001")
    result, error = run_tool(
        ctx,
        "answer",
        {
            "charge_id": "chg-l-1001",
            "question": "allowable",
            "answer": "supports",
            "reasoning": "Fine.",
        },
    )
    assert not error, result


def test_an_answer_names_a_rule_from_the_rulebook():
    """Answer 6: judgment.rule is the rulebook's ID, and an unknown ID is refused."""
    ctx = context(until="rec-allowable-l-1001")
    args = {
        "charge_id": "chg-l-1001",
        "question": "allowable",
        "answer": "contradicts",
        "reasoning": "Beer.",
    }
    result, error = run_tool(ctx, "answer", {**args, "rule": "NSF-NO-SUCH-RULE"})
    assert error and "isn't a rule ID" in result
    result, error = run_tool(ctx, "answer", {**args, "rule": "NSF-NEVER-ALCOHOL"})
    assert not error, result
    assert ctx.staged[-1].record.data.rule == "NSF-NEVER-ALCOHOL"  # pyright: ignore[reportAttributeAccessIssue]


def test_a_new_answer_replaces_the_agents_own_and_a_milder_one_waits():
    ctx = context(until="rec-bill-seq-0207", now="2026-02-21T17:30:00+00:00")
    args = {
        "charge_id": "chg-l-1001",
        "question": "allowable",
        "answer": "contradicts",
        "reasoning": "On second look.",
    }
    result, error = run_tool(ctx, "answer", args)
    assert not error and "takes effect" in result
    assert ctx.staged[-1].record.replaces_id == "rec-allowable-l-1001"
    result, error = run_tool(ctx, "answer", {**args, "answer": "supports"})
    assert not error and "waits for the accountant" in result


def test_a_flag_is_always_unsure_and_can_be_about_a_file():
    ctx = context()
    result, error = run_tool(
        ctx,
        "flag",
        {
            "file_id": "file-invoice-1001",
            "question": "Is this a duplicate?",
            "reasoning": "Looks familiar.",
        },
    )
    assert not error, result
    data = ctx.staged[-1].record.data
    assert data.answer == "unsure" and data.question == "flag"  # pyright: ignore[reportAttributeAccessIssue]


def test_a_budget_assignment_replaces_the_current_one_and_waits():
    ctx = context(until="rec-allowable-l-1001")
    result, error = run_tool(
        ctx,
        "assign_budget_line",
        {"charge_id": "chg-l-1001", "budget_line_id": "rec-budget-other", "reason": "Recharge."},
    )
    assert not error and "waits" in result
    assert ctx.staged[-1].record.replaces_id == "rec-budget-l-1001"


def test_a_budget_line_needs_its_nsf_category():
    """Answer 9: each budget line carries its NSF category from the fixed list."""
    ctx = context(until="rec-period", now="2023-01-12T15:00:00+00:00")
    content, error = run_tool(ctx, "open_file", {"file_id": "file-award-letter"})
    assert not error
    award = SAMPLE.document("file-award-letter")
    line = "G. Other Direct Costs                                    $100,000"
    start = award.find(line)
    cite = [
        CitationCharLocation(
            type="char_location",
            cited_text=line,
            document_index=0,
            start_char_index=start,
            end_char_index=start + len(line),
        )
    ]
    dated = "Amendment Date: January 10, 2023"
    d = award.find(dated)
    ctx.labels["odc"] = LabelLine("odc", "Other Direct Costs", cite)
    ctx.labels["odc_amount"] = LabelLine("odc_amount", "$100,000", cite)
    ctx.labels["dated"] = LabelLine(
        "dated",
        "January 10, 2023",
        [
            CitationCharLocation(
                type="char_location",
                cited_text=dated,
                document_index=0,
                start_char_index=d,
                end_char_index=d + len(dated),
            )
        ],
    )
    values = [
        {"field": "name", "label": "odc"},
        {"field": "amount", "label": "odc_amount"},
        {"field": "dated", "label": "dated"},
    ]
    result, error = run_tool(ctx, "write_term", {"kind": "budget_line", "values": values})
    assert error and "category" in result
    result, error = run_tool(
        ctx,
        "write_term",
        {"kind": "budget_line", "values": values, "category": "other_direct_costs"},
    )
    assert not error and "waits for the accountant" in result


def test_a_checklist_item_from_a_rate_is_rechecked():
    ctx = context()
    open_invoice(ctx)
    label(ctx, "count", "50", "Sediment core liners, 50 count: $1,240.00")
    label(ctx, "each", "$24.80", None)
    result, error = run_tool(
        ctx,
        "add_checklist_item",
        {
            "charge_id": "chg-l-1001",
            "needed": "Packing slip",
            "amount_cents": 99999,
            "rate": {"quantity": {"field": "quantity", "label": "count"}, "rate_id": "rec-nope"},
        },
    )
    assert error  # the rate term doesn't exist


def test_read_tools_see_the_whole_grant_and_this_runs_writes():
    ctx = context(until="rec-allowable-l-1001")
    text, error = run_tool(ctx, "list_charges", {})
    assert not error and "chg-l-1001" in text
    text, error = run_tool(ctx, "search", {"query": "INV-1001"})
    assert not error and "file-invoice-1001" in text
    text, error = run_tool(ctx, "get_charge", {"charge_id": "chg-l-1001"})
    assert "rec-link-l-1001" in text and "Checklist" in text
    run_tool(ctx, "flag", {"charge_id": "chg-l-1001", "question": "Odd?", "reasoning": "Hm."})
    text, _ = run_tool(ctx, "get_charge", {"charge_id": "chg-l-1001"})
    assert ctx.staged[-1].record.id in text
    text, error = run_tool(ctx, "get_record", {"record_id": "rec-bill-inv-1001"})
    assert not error and "INV-1001" in text
    _, error = run_tool(ctx, "open_file", {"file_id": "nope"})
    assert error


def test_a_thread_message_is_kept_aside_until_the_run_saves():
    ctx = context()
    result, error = run_tool(
        ctx, "post_message", {"charge_id": "chg-l-1001", "text": "Linked the invoice."}
    )
    assert not error and len(ctx.messages_out) == 1 and not ctx.staged
    assert ctx.messages_out[0].run_id == ctx.inputs.run_id


def test_bad_input_comes_back_as_a_tool_error():
    ctx = context()
    result, error = run_tool(ctx, "link", {"charge_id": "chg-l-1001", "surprise": 1})
    assert error and "doesn't fit" in result
    result, error = run_tool(ctx, "no_such_tool", {})
    assert error


def test_charges_that_arrive_together_are_batched():
    """Answer 8: one run, or batches on a large upload, each its own run."""
    assert batch_charge_ids(["a", "b", "c"], 2) == [["a", "b"], ["c"]]
    assert batch_charge_ids([f"c{i}" for i in range(5)]) == [[f"c{i}" for i in range(5)]]


def test_the_rulebook_gives_each_rules_kind():
    book = parse_rulebook(
        "NSF", "### NSF-A\n\nText.\n\n- Kind: not allowed\n\n### NSF-B\n\n- Kind: judgment\n"
    )
    assert book.kinds == {"NSF-A": "not allowed", "NSF-B": "judgment"}
    assert "NSF-END-DATE-PURCHASES" in load_rulebook().ids
