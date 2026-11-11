"""Issue 227's first versions: progress while the agent works (ruling 71), why a control
is unavailable (ruling 72), a partly filled item (ruling 73), and a budget sub-line's
parent (ruling 74)."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts import api
from app.contracts.checks import ChecklistEntry, ItemSource
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import BudgetCategory
from app.contracts.signoff import SignOffStateName
from app.contracts.timeline import TimelineNow, TimelineView
from tests.contracts.factory import agent, at, budget_line


def summary(**changes: Any) -> api.GrantSummary:
    fields: dict[str, Any] = {
        "grant": load_sample_grant().grant,
        "charges_ready": 0,
        "charges_total": 2,
        "on_problem_list": 0,
        "waiting": 0,
        "bucket_counts": {},
        "now": at(0),
    }
    return api.GrantSummary.model_validate(fields | changes)


def test_a_grant_says_how_far_the_agent_has_read_and_what_its_last_run_did():
    idle = summary()
    assert idle.reading is None and idle.last_run_summary is None
    working = summary(
        reading={"files_read": 3, "files_total": 8, "lines_read": 0, "lines_total": 2},
        last_run_summary="Read invoice 1001 and linked it to L-1001.",
    )
    assert api.GrantSummary.model_validate_json(working.model_dump_json()) == working
    assert working.reading is not None and working.reading.files_total == 8
    with pytest.raises(ValidationError):  # never more read than to read
        api.ReadingProgress(files_read=9, files_total=8, lines_read=0, lines_total=0)
    with pytest.raises(ValidationError):  # a summary is never empty
        summary(last_run_summary="")


def test_a_control_that_cant_be_used_says_why():
    now = TimelineNow(now=at(1), waiting_on_problem_list=0)
    open_ = TimelineView(now=now, finished=False, catching_up=False)
    assert open_.move_unavailable_reason is None
    assert open_.next_highlight_unavailable_reason is None
    done = TimelineView(
        now=now,
        finished=True,
        catching_up=False,
        move_unavailable_reason="Nothing is left to play.",
        next_highlight_unavailable_reason="No highlight is left to play.",
    )
    assert TimelineView.model_validate_json(done.model_dump_json()) == done
    signing = api.SignOffState(state=SignOffStateName.NOT_SIGNED)
    assert signing.unavailable_reason is None
    busy = api.SignOffState(
        state=SignOffStateName.NOT_SIGNED,
        unavailable_reason="The agent is still working on this grant. Sign off once it's done.",
    )
    assert api.SignOffState.model_validate_json(busy.model_dump_json()) == busy


def item(**changes: Any) -> ChecklistEntry:
    fields: dict[str, Any] = {
        "default_item": "bill",
        "added_by": ItemSource.DEFAULT,
        "needed": "A bill that adds up to the charge",
        "amount_cents": 67600,
        "filled": False,
        "link_ids": ("l1",),
    }
    return ChecklistEntry.model_validate(fields | changes)


def test_a_partly_covered_item_has_words_and_amounts_and_stays_not_filled():
    partly = item(covered_cents=25000, partly_filled_text="Partly filled, $250.00 of $676.00")
    assert not partly.filled and partly.covered_cents == 25000 and partly.amount_cents == 67600
    assert ChecklistEntry.model_validate_json(partly.model_dump_json()) == partly
    assert item().covered_cents is None and item().partly_filled_text is None
    with pytest.raises(ValidationError):  # the amount without its wording
        item(covered_cents=25000)
    with pytest.raises(ValidationError):  # a filled item isn't partly filled
        item(filled=True, covered_cents=25000, partly_filled_text="Partly filled")
    with pytest.raises(ValidationError):  # nor is one with no amount
        item(amount_cents=None, covered_cents=25000, partly_filled_text="Partly filled")


def test_a_budget_sub_line_names_its_parent():
    line = agent("b1", budget_line())
    sub = api.BudgetLineView(
        line=line, amount_cents=4000000, spent_cents=0, parent=BudgetCategory.OTHER_DIRECT_COSTS
    )
    assert api.BudgetLineView.model_validate_json(sub.model_dump_json()) == sub
    top = api.BudgetLineView(line=line, amount_cents=4000000, spent_cents=0)
    assert top.parent is None
