"""Issue 83: the award limit's over_limit problem and its acceptance carry the amount over."""

import pytest
from pydantic import ValidationError

from app.contracts import api
from app.contracts.checks import GrantStatus, Problem
from app.contracts.records import AcceptedReason
from tests.contracts.factory import problems, user

OVER = {"check": "budget", "problem": "over_limit", "text": "Spending is $5,000.00 over the limit."}


def test_an_over_limit_problem_carries_the_amount_over():
    problem = Problem.model_validate(OVER | {"amount_cents": 500000})
    status = GrantStatus(grant_id="g", problems=(problem,), flagged=True)
    assert (
        GrantStatus.model_validate_json(status.model_dump_json()).problems[0].amount_cents == 500000
    )
    assert Problem.model_validate(OVER).amount_cents is None  # every other problem has none
    with pytest.raises(ValidationError):
        Problem.model_validate(OVER | {"amount_cents": -1})
    row = api.GrantProblem.model_validate(OVER | {"amount_cents": 600000, "flagged": True})
    assert row.amount_cents == 600000


def test_an_acceptance_keeps_the_amount_over_it_accepted():
    accepted = user(
        "a1",
        {
            "kind": "accepted_reason",
            "reason": {"check": "budget", "problem": "over_limit"},
            "note": "A supplement is coming.",
            "amount_cents": 500000,
        },
    )
    assert problems(accepted, []) == []
    assert isinstance(accepted.data, AcceptedReason) and accepted.data.amount_cents == 500000
    with pytest.raises(ValidationError):
        AcceptedReason.model_validate(accepted.data.model_dump() | {"amount_cents": -5})
