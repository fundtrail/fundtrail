"""The Allowable answer doesn't rest on the period of performance (issue #119).

In the first end-to-end run the real model answered L-1002's Allowable "unsure" because the
charge fell after the end date, citing NSF-POST-END-COMMITMENTS. The date is code's own check:
section 15 has L-1002 reach Evidence complete once the extension is confirmed, with no agent
call, because its Allowable answer doesn't rest on the end date.
"""

from datetime import datetime

from app.agent import RunSaved, run_once
from app.agent.prompts import SYSTEM_PROMPT
from app.checks.checklist import default_items
from app.checks.run import run_checks
from app.contracts.checks import Bucket, ChecksInput
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import Judgment, Record
from app.contracts.runs import Trigger, TriggerKind

from .fakes import FakeModel, calls, results_of, sample_inputs, tool

SAMPLE = load_sample_grant()
BY_ID = {r.id: r for r in SAMPLE.records}
NOW = datetime.fromisoformat("2026-02-24T00:00:00+00:00")


def records_until(record_id: str) -> list[Record]:
    out: list[Record] = []
    for r in SAMPLE.records:
        if r.id == record_id:
            break
        out.append(r)
    return out


def l1002_inputs():
    """The L-1002 run: the usage statement is on file, and L-1002 arrives after the end date."""
    from dataclasses import replace

    base = sample_inputs(
        now=NOW,
        trigger=Trigger(kind=TriggerKind.CHARGE, id="chg-l-1002"),
        records=records_until("rec-link-l-1002"),
        charge_ids=["chg-l-1002"],
        ids=iter(["rec-link-l-1002", "rec-budget-l-1002", "rec-allowable-l-1002"]),
    )
    return replace(base, run_checks=run_checks, default_items=default_items)


def link_and_assign():
    return [
        tool(
            "link",
            record_id="rec-bill-seq-0207",
            charge_id="chg-l-1002",
            amount_cents=218000,
            default_item="usage_statement",
        ),
        tool(
            "assign_budget_line",
            charge_id="chg-l-1002",
            budget_line_id="rec-budget-other",
            reason="A campus core facility's recharge.",
        ),
    ]


def allowable(answer: str, **extra: object):
    return tool(
        "answer",
        charge_id="chg-l-1002",
        question="allowable",
        answer=answer,
        reasoning="Sequencing run 7 on the survey's sediment samples.",
        **extra,
    )


def test_an_allowable_answer_that_rests_on_the_end_date_is_refused():
    def first(request: object):
        return calls(*link_and_assign(), tool("finish", summary="Linked."))

    def on_the_date(request: object):
        return calls(
            allowable("unsure", rule="NSF-POST-END-COMMITMENTS"),
            allowable("unsure", rests_on=["rec-period"]),
            tool("finish", summary="Answered."),
        )

    def on_the_cost(request: object):
        results = results_of(request)  # pyright: ignore[reportArgumentType]
        assert results[0]["is_error"] and "dispute of the date check" in results[0]["content"]
        assert (
            results[1]["is_error"] and "rests on the period of performance" in results[1]["content"]
        )
        return calls(
            allowable("supports", rests_on=["rec-bill-seq-0207"]),
            tool("finish", summary="Answered."),
        )

    result = run_once(l1002_inputs(), FakeModel([first, on_the_date, on_the_cost]))
    assert isinstance(result, RunSaved), getattr(result, "error", result)
    answer = result.records[-1].data
    assert isinstance(answer, Judgment) and answer.answer == "supports"


def test_a_flag_on_a_charge_that_rests_on_the_end_date_is_refused():
    def flag_the_date(request: object):
        return calls(
            *link_and_assign(),
            tool(
                "flag",
                charge_id="chg-l-1002",
                question="Was run 7 committed before the end date?",
                reasoning="The charge is after January 31, 2026.",
                rule="NSF-POST-END-COMMITMENTS",
            ),
            allowable("supports"),
            tool("finish", summary="x"),
        )

    def finish(request: object):
        results = results_of(request)  # pyright: ignore[reportArgumentType]
        assert results[2]["is_error"] and "dispute of the date check" in results[2]["content"]
        return calls(tool("finish", summary="Linked and answered."))

    result = run_once(l1002_inputs(), FakeModel([flag_the_date, finish]))
    assert isinstance(result, RunSaved) and [r.kind for r in result.records] == [
        "link",
        "budget_assignment",
        "judgment",
    ]


def test_with_an_answer_on_the_cost_the_extension_clears_the_charge_with_no_agent_call():
    """Section 15: after the extension is confirmed, L-1002 is Evidence complete."""
    model = FakeModel(
        [
            lambda r: calls(
                *link_and_assign(),
                allowable("supports", rests_on=["rec-bill-seq-0207"]),
                tool("finish", summary="x"),
            )
        ]
    )
    result = run_once(l1002_inputs(), model)
    assert isinstance(result, RunSaved)
    later = datetime.fromisoformat("2026-04-10T17:00:00+00:00")
    records = [
        *records_until("rec-link-l-1002"),
        *result.records,
        BY_ID["rec-period-extension"],
        BY_ID["rec-confirm-extension"],
    ]
    out = run_checks(
        ChecksInput(
            now=later,
            charges=tuple(SAMPLE.charges),
            files=tuple(SAMPLE.files),
            records=tuple(records),
        )
    )
    status = next(s for s in out.charges if s.charge_id == "chg-l-1002")
    assert status.bucket == Bucket.EVIDENCE_COMPLETE


def test_the_prompt_keeps_the_date_out_of_the_allowable_answer():
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "A charge's date against the period of performance isn't part of it" in flat
    assert "don't add a checklist item or a flag about where the date falls" in flat
    assert "dispute the check (NSF-POST-END-COMMITMENTS is for that dispute)" in flat
    assert "the flag on a purchase close to the end date (NSF-END-DATE-PURCHASES)" in flat
    assert "a Covers answer on a pre-award approval, which rests on the start date" in flat


def test_the_end_date_purchases_flag_still_saves_and_sends_the_charge_to_a_person():
    """Decision 0015: a purchase close to the end date is the agent's flag, resting on the period."""
    from app.contracts.records import Link

    l1001 = SAMPLE.charges[0]
    late = l1001.model_copy(
        update={
            "id": "chg-late",
            "ledger_line_id": "L-1009",
            "transaction_date": datetime(2026, 1, 20).date(),
            "posting_date": datetime(2026, 1, 22).date(),
            "arrived_at": datetime.fromisoformat("2026-01-22T00:00:00+00:00"),
            "amount_cents": 380000,
            "description": "Laptop",
        }
    )
    from dataclasses import replace

    db = records_until("rec-bill-seq-0207")
    inputs = replace(
        sample_inputs(
            now=datetime.fromisoformat("2026-01-22T00:00:00+00:00"),
            trigger=Trigger(kind=TriggerKind.CHARGE, id="chg-late"),
            records=db,
            charge_ids=["chg-late"],
        ),
        charges=[l1001, late],
        run_checks=run_checks,
        default_items=default_items,
    )
    flag = tool(
        "flag",
        charge_id="chg-late",
        question="A $3,800 laptop bought 11 days before the end date: was it used in the project?",
        reasoning="NSF says the university typically shouldn't buy a computing device this close to the end.",
        rule="NSF-END-DATE-PURCHASES",
        rests_on=["rec-period"],
    )
    assign = tool(
        "assign_budget_line",
        charge_id="chg-late",
        budget_line_id="rec-budget-materials-and-supplies",
        reason="A computer for the lab.",
    )
    result = run_once(
        inputs, FakeModel([lambda r: calls(assign, flag, tool("finish", summary="Flagged."))])
    )
    assert isinstance(result, RunSaved), getattr(result, "error", result)
    saved = result.records[-1].data
    assert isinstance(saved, Judgment) and saved.rule == "NSF-END-DATE-PURCHASES"
    assert not any(isinstance(r.data, Link) for r in result.records)
    out = run_checks(
        ChecksInput(
            now=datetime.fromisoformat("2026-01-22T12:00:00+00:00"),
            charges=(l1001, late),
            files=tuple(SAMPLE.files[:2]),
            records=(*db, *result.records),
        )
    )
    assert next(s for s in out.charges if s.charge_id == "chg-late").bucket == Bucket.NEEDS_HUMAN


def test_the_period_check_is_for_the_allowable_question_only():
    """A Covers answer on a pre-award approval keeps its start date: no period refusal for it."""
    from app.agent.context import RunContext
    from app.agent.rulebook import load_rulebook
    from app.agent.tools import run_tool

    ctx = RunContext(inputs=l1002_inputs(), rulebook=load_rulebook())
    covers = {
        "charge_id": "chg-l-1002",
        "question": "covers",
        "record_id": "rec-bill-seq-0207",
        "answer": "supports",
        "reasoning": "The approval predates the start date by 30 days.",
        "rests_on": ["rec-period"],
    }
    result, error = run_tool(ctx, "answer", covers)
    assert error and "period of performance" not in result  # refused for other reasons only
    result, error = run_tool(ctx, "answer", {**covers, "question": "allowable", "record_id": None})
    assert error and "rests on the period of performance" in result
