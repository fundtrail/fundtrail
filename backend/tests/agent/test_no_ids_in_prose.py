"""The accountant reads the agent's reasoning, so it names records by what they are (#275).

QA found an answer's reasoning ending "...and I've filed a correction (rec-afbc6f36)". A write
whose reasoning, reason, question, message or other prose names an ID the run knows is refused
with what to write instead; a ledger line number, which the accountant knows, passes.
"""

from datetime import datetime

import pytest

from app.agent.context import RunContext
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import Judgment
from app.contracts.runs import Trigger, TriggerKind

from .fakes import sample_inputs

SAMPLE = load_sample_grant()


def context() -> RunContext:
    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-14T00:00:00+00:00"),
        trigger=Trigger(kind=TriggerKind.CHARGE, id="chg-l-1001"),
        records=[r for r in SAMPLE.records if r.id in {"rec-period", "rec-bill-inv-1001"}],
        charge_ids=["chg-l-1001"],
    )
    return RunContext(inputs=inputs, rulebook=load_rulebook())


def flag(ctx: RunContext, reasoning: str, question: str = "Is this for the project?"):
    return run_tool(
        ctx,
        "flag",
        {"charge_id": "chg-l-1001", "question": question, "reasoning": reasoning},
    )


@pytest.mark.parametrize(
    "reasoning",
    [
        "The bill rec-bill-inv-1001 doesn't name the project.",  # a saved record
        "The file file-invoice-1001 doesn't name the project.",  # a file
        "Charge chg-l-1001 has no project named on its bill.",  # a charge
    ],
)
def test_reasoning_that_names_an_id_is_refused_with_what_to_write(reasoning: str):
    ctx = context()
    result, error = flag(ctx, reasoning)
    assert error and "an ID means nothing to them" in result
    assert "the invoice from Example Lab Supply Co." in result and "reasoning (" in result
    assert not ctx.staged


def test_the_same_reasoning_in_plain_words_is_saved():
    ctx = context()
    result, error = flag(
        ctx, "The invoice from Example Lab Supply Co. for ledger line L-1001 names no project."
    )
    assert not error, result
    assert isinstance(ctx.staged[-1].record.data, Judgment)


def test_a_record_written_in_this_run_counts_too_and_other_prose_fields_are_checked():
    ctx = context()
    result, error = flag(ctx, "The invoice from Example Lab Supply Co. names no project.")
    assert not error, result
    own = ctx.staged[-1].record.id
    result, error = run_tool(
        ctx, "retract", {"replaces_id": own, "reason": f"Replacing {own}: it was wrong."}
    )
    assert error and f"reason ({own})" in result
    result, error = flag(ctx, "Plain words.", question=f"Does {own} still hold?")
    assert error and f"question ({own})" in result


def test_the_prompt_says_to_name_records_by_what_they_are():
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "Name records and files by what they are" in flat
    assert "never by their IDs" in flat
