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
    assert "don't add a checklist item or a flag about it" in flat
    assert "dispute the check (NSF-POST-END-COMMITMENTS is for that dispute)" in flat
