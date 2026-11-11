"""Ruling 81's standard conditions, and a per diem as a checklist item at a rate.

The award's standard-conditions sentence is one other_term with standard_conditions true,
recorded once; the checks then never ask the unusual-term question about it. A per diem is a
checklist item whose quantity is cited from the claim and whose rate is cited from the document
that sets it, as the trip eval case expects, not a link of the rate document for an amount.
"""

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from anthropic.types import CitationCharLocation

from app.agent.citations import LabelLine
from app.agent.context import RunContext
from app.agent.desk import AWARD_NOTICE_GUIDANCE
from app.agent.fields import TERM_FIELDS
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import ChecklistItem, OtherTerm, Record
from app.contracts.runs import Trigger, TriggerKind

from .fakes import sample_inputs

SAMPLE = load_sample_grant()
AWARD = SAMPLE.document("file-award-letter")
CONDITIONS = (
    "This award is subject to the Research Terms and Conditions and the NSF Agency Specific "
    "Requirements in effect on the award date."
)
TRIP = Path(__file__).parents[3] / "eval" / "cases" / "trip-airfare-and-per-diem"


def cite(text: str, chunk: str, document: int = 0) -> CitationCharLocation:
    start = text.index(chunk)
    return CitationCharLocation(
        type="char_location",
        cited_text=chunk,
        document_index=document,
        start_char_index=start,
        end_char_index=start + len(chunk),
    )


def award_context() -> RunContext:
    inputs = sample_inputs(
        now=datetime.fromisoformat("2023-01-12T15:00:00+00:00"),
        trigger=Trigger(kind=TriggerKind.FILE, id="file-award-letter"),
        records=[],
    )
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook())
    result, error = run_tool(ctx, "open_file", {"file_id": "file-award-letter"})
    assert not error, result
    ctx.labels["dated"] = LabelLine(
        "dated", "January 10, 2023", [cite(AWARD, "Amendment Date: January 10, 2023")]
    )
    ctx.labels["conditions"] = LabelLine("conditions", CONDITIONS, [cite(AWARD, CONDITIONS)])
    return ctx


def write_conditions(ctx: RunContext, standard: bool | None = True):
    args: dict[str, object] = {
        "kind": "other_term",
        "label": "Standard conditions",
        "values": [
            {"field": "dated", "label": "dated", "value": "2023-01-10"},
            {"field": "statement", "label": "conditions"},
        ],
    }
    if standard is not None:
        args["standard_conditions"] = standard
    return run_tool(ctx, "write_term", args)


def test_the_standard_conditions_are_one_term_marked_as_such_and_recorded_once():
    ctx = award_context()
    result, error = write_conditions(ctx)
    assert not error, result
    term = ctx.staged[-1].record.data
    assert isinstance(term, OtherTerm) and term.standard_conditions is True
    assert term.statement.value == CONDITIONS

    result, error = write_conditions(ctx)
    assert error and "already recorded" in result and "recorded once" in result
    assert len(ctx.staged) == 1


def test_an_ordinary_other_term_stays_unmarked_and_only_an_other_term_takes_the_mark():
    ctx = award_context()
    result, error = write_conditions(ctx, standard=None)
    assert not error, result
    term = ctx.staged[-1].record.data
    assert isinstance(term, OtherTerm) and term.standard_conditions is False

    result, error = run_tool(
        ctx,
        "write_term",
        {
            "kind": "period_of_performance",
            "standard_conditions": True,
            "values": [{"field": "dated", "label": "dated", "value": "2023-01-10"}],
        },
    )
    assert error and "standard_conditions is for an other_term only" in result


def test_the_agent_is_told_how_to_write_the_standard_conditions():
    flat = " ".join(AWARD_NOTICE_GUIDANCE.split())
    assert "one other_term with standard_conditions true" in flat
    assert "not again when a later notice repeats it" in flat
    assert "standard_conditions: the tool's standard_conditions argument, true or false" in (
        TERM_FIELDS
    )


def trip_context() -> RunContext:
    """The trip case's expense report and per diem rates, read on the sample grant."""
    texts = {
        "file-expense-report": (TRIP / "expense_report.txt").read_text(),
        "file-per-diem-rates": (TRIP / "per_diem_rates.txt").read_text(),
    }
    base = sample_inputs(
        now=datetime.fromisoformat("2025-11-14T00:00:00+00:00"),
        trigger=Trigger(kind=TriggerKind.CHARGE, id="chg-l-1001"),
        records=[],
        charge_ids=["chg-l-1001"],
    )
    files = [
        SAMPLE.files[1].model_copy(
            update={
                "id": file_id,
                "name": f"{file_id}.txt",
                "storage_path": f"ws-sample/grant-sample/{file_id}/{file_id}.txt",
            }
        )
        for file_id in texts
    ]
    read = base.read_file
    inputs = replace(
        base,
        files=[*base.files, *files],
        read_file=lambda f: texts[f.id].encode() if f.id in texts else read(f),
    )
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook())
    for file_id in texts:  # documents 0 and 1
        result, error = run_tool(ctx, "open_file", {"file_id": file_id})
        assert not error, result
    days = next(ln.strip() for ln in texts["file-expense-report"].splitlines() if "5 days" in ln)
    rate = "Field site per diem: $100.00 per day"
    ctx.labels["days"] = LabelLine("days", "5", [cite(texts["file-expense-report"], days, 0)])
    ctx.labels["rate"] = LabelLine(
        "rate", "$100.00 per day", [cite(texts["file-per-diem-rates"], rate, 1)]
    )
    return ctx


def test_a_per_diem_is_an_item_at_a_rate_cited_from_the_claim_and_the_rate_document():
    ctx = trip_context()
    result, error = run_tool(
        ctx,
        "add_checklist_item",
        {
            "charge_id": "chg-l-1001",
            "needed": "Per diem: 5 days at the field site rate",
            "amount_cents": 50000,
            "rate": {
                "quantity": {"field": "quantity", "label": "days", "value": "5"},
                "rate": {"field": "rate", "label": "rate", "value": "10000"},
            },
        },
    )
    assert not error, result
    item = ctx.staged[-1].record.data
    assert isinstance(item, ChecklistItem) and item.rate is not None
    assert item.amount_cents == 50000
    assert item.rate.quantity.value == 5 and item.rate.rate is not None
    assert item.rate.rate.value == 10000  # cents a day
    assert item.rate.quantity.citation is not None and item.rate.rate.citation is not None
    assert item.rate.quantity.citation.file_id == "file-expense-report"
    assert item.rate.rate.citation.file_id == "file-per-diem-rates"

    # Four days at that rate isn't $500: the item's amount is checked against its rate math.
    result, error = run_tool(
        ctx,
        "add_checklist_item",
        {
            "charge_id": "chg-l-1001",
            "needed": "Per diem",
            "amount_cents": 40000 + 1,
            "rate": {
                "quantity": {"field": "quantity", "label": "days", "value": "5"},
                "rate": {"field": "rate", "label": "rate", "value": "10000"},
            },
        },
    )
    assert error and "isn't the quantity times the rate" in result


def test_the_prompt_says_a_per_diem_is_an_item_at_a_rate_and_an_expense_report_a_note():
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "A per diem, or any amount paid at a rate instead of receipts, is a checklist item" in (
        flat
    )
    assert "Don't link the rate document for an amount" in flat
    assert "An expense report is a note, linked with no amount" in flat


def test_a_fix_of_the_standard_conditions_while_one_waits_is_accepted():
    """The term confirmed by the accountant, a fix of it waiting, and a second fix of it: all
    one chain, so none is refused as a second recording (PR 325's review)."""
    ctx = award_context()
    result, error = write_conditions(ctx)
    assert not error, result
    term = ctx.staged.pop().record
    confirm = Record.model_validate(
        {
            "id": "rec-confirm",
            "workspace_id": term.workspace_id,
            "grant_id": term.grant_id,
            "author": "user",
            "author_user_id": "00000000-0000-4000-8000-0000000000aa",
            "written_at": "2023-01-12T16:00:00Z",
            "data": {"kind": "confirmation", "record_ids": [term.id], "decision": "confirmed"},
        }
    )
    ctx.inputs = replace(ctx.inputs, records=[term, confirm])
    fix = {
        "kind": "other_term",
        "label": "Standard conditions",
        "standard_conditions": True,
        "replaces_id": term.id,
        "values": [
            {"field": "dated", "label": "dated", "value": "2023-01-10"},
            {"field": "statement", "label": "conditions"},
        ],
    }
    for _ in range(2):  # a fix, then another fix of the confirmed term while the first waits
        result, error = run_tool(ctx, "write_term", fix)
        assert not error, result
        assert ctx.staged[-1].waits

    result, error = write_conditions(ctx)  # a new term with the same sentence
    assert error and f"already recorded ({term.id})" in result
    assert "recorded once: leave this sentence out" in result
    assert "standard_conditions false" not in result
