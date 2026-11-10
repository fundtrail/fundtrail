"""Issue 165: sample grants, their clock and their timeline."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts import api
from app.contracts.fixtures import load_sample_grant
from app.contracts.timeline import (
    PlayedEvent,
    TimelineEvent,
    TimelineEventKind,
    TimelineMove,
    TimelineNow,
    TimelineStartOver,
    TimelineView,
    UserDelivery,
)
from app.contracts.workspaces import Grant, GrantSample, MemberRole, SampleChoice
from tests.contracts.factory import agent, at, bill

SAMPLE = load_sample_grant()


def sample_grant() -> Grant:
    return SAMPLE.grant.model_copy(
        update={
            "clock_now": at(0),
            "sample": GrantSample(sample="nitrate-sensors", choice=SampleChoice.SMALL_LIVE),
        }
    )


def test_a_sample_grant_has_its_own_clock_and_says_what_it_was_opened_from():
    g = Grant.model_validate_json(sample_grant().model_dump_json())
    assert g.clock_now == at(0) and g.sample is not None and g.sample.choice == "small_live"
    assert SAMPLE.grant.clock_now is None and SAMPLE.grant.sample is None  # a real grant
    with pytest.raises(ValidationError):
        GrantSample.model_validate({"sample": "x", "choice": "huge"})
    with pytest.raises(ValidationError):  # no opening date: every sample opens at its start
        GrantSample.model_validate({"sample": "x", "choice": "small_live", "opens_at": at(0)})
    assert [m.value for m in MemberRole] == ["owner", "sample"]


def test_every_grant_summary_carries_the_grants_now():
    fields: dict[str, Any] = {
        "grant": sample_grant(),
        "charges_ready": 0,
        "charges_total": 0,
        "on_problem_list": 0,
        "waiting": 0,
        "bucket_counts": {},
    }
    with pytest.raises(ValidationError):
        api.GrantSummary.model_validate(fields)
    assert api.GrantSummary.model_validate(fields | {"now": at(0)}).now == at(0)


def test_the_sample_options_and_the_create_body():
    option = api.SampleOption(
        choice=SampleChoice.LARGER_LIVE,
        name="Larger sample, live",
        description="Placeholder until the docs give the words.",
        needs_confirm=True,
        available=False,
        unavailable_reason="Another larger sample is still playing.",
    )
    assert option.needs_confirm and not option.available
    assert api.SampleCreate(choice=SampleChoice.SMALL_LIVE).confirmed is False


def test_a_timeline_view_round_trips():
    arrival = TimelineEvent(
        id="e1",
        at=at(1),
        kind=TimelineEventKind.ARRIVAL,
        source=api.ArrivalSource.LEDGER,
        name="L-1001",
    )
    delivery = TimelineEvent(
        id="e2", at=at(2), kind=TimelineEventKind.USER_DELIVERY, name="receipt.jpg"
    )
    view = TimelineView(
        just_happened=(
            PlayedEvent(event=arrival, agent_records=(agent("b1", bill()),), charge_ids=("c1",)),
        ),
        now=TimelineNow(
            now=at(2),
            stopped_on=delivery,
            deliveries=(UserDelivery(event=delivery, delivered=False),),
            waiting_on_problem_list=1,
        ),
        coming_up=(
            TimelineEvent(
                id="e3", at=at(5), kind=TimelineEventKind.CHECKS_DATE, name="Closeout window opens"
            ),
        ),
        finished=False,
        catching_up=True,
    )
    assert TimelineView.model_validate_json(view.model_dump_json()) == view
    assert TimelineMove().to is None and TimelineMove(to=at(3)).to == at(3)
    with pytest.raises(ValidationError):
        TimelineStartOver.model_validate({})  # the start-over needs its confirm
    TimelineView.model_json_schema()


def test_a_sample_refusal_names_why_and_the_grant_still_reading():
    blocking = api.GrantSummary(
        grant=sample_grant(),
        charges_ready=0,
        charges_total=0,
        on_problem_list=0,
        waiting=0,
        bucket_counts={},
        now=at(0),
    )
    refusal = api.SampleRefusal(
        reason=api.SampleRefusalReason.ANOTHER_SAMPLE_WORKING,
        message="Another larger sample is still working through its last move.",
        grant=blocking,
    )
    assert api.SampleRefusal.model_validate_json(refusal.model_dump_json()) == refusal
    confirm = api.SampleRefusal(
        reason=api.SampleRefusalReason.NEEDS_CONFIRM, message="Confirm first."
    )
    assert confirm.grant is None
    with pytest.raises(ValidationError):
        api.SampleRefusal.model_validate({"reason": "too_many", "message": "x"})
    with pytest.raises(ValidationError):  # renamed: the limit is on the clock move
        api.SampleRefusal.model_validate({"reason": "history_reading", "message": "x"})


def test_skipping_the_human_steps_and_the_run_through():
    """Ruling 47: the move can skip the human steps; played events say who decided and
    whether the result was loaded; a prerun sample says whether it's on the run-through."""
    assert TimelineMove().skip_human_steps is False
    assert TimelineMove(skip_human_steps=True).skip_human_steps
    arrival = TimelineEvent(id="e1", at=at(1), kind=TimelineEventKind.ARRIVAL, name="L-1001")
    decision = agent("b1", bill())
    played = PlayedEvent(event=arrival, scripted_decisions=(decision,), loaded=True)
    assert PlayedEvent.model_validate_json(played.model_dump_json()) == played
    assert PlayedEvent(event=arrival).loaded is False
    now = TimelineNow(now=at(1), waiting_on_problem_list=0)
    live = TimelineView(now=now, finished=False, catching_up=False)
    assert live.on_run_through is None  # a sample read live
    prerun = TimelineView(now=now, finished=False, catching_up=False, on_run_through=True)
    assert prerun.on_run_through is True
