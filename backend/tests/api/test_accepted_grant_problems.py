"""Ruling 84: an accepted grant problem leaves the problem list and shows on the grant
overview, with the problem in the server's words, the note, who accepted it and when."""

from __future__ import annotations

from app.contracts.checks import Problem
from app.contracts.runs import Trigger, TriggerKind
from app.db import store
from app.db.pool import transaction
from app.db.recheck import recheck_grant
from tests.api.conftest import Api
from tests.api.test_screens import (  # pyright: ignore[reportPrivateUsage]
    APRIL_10,
    _checks,
    _get,
    _sample,
)

OVER = Problem(check="budget", problem="over_limit", text="Spending is $50.00 over the limit.")
LATE = Problem(check="runs", problem="failed", text="The agent couldn't read a file.")


def test_an_accepted_grant_problem_moves_to_the_overview(api: Api) -> None:
    checks = _checks(api)
    checks.grant_problems = [OVER, LATE]
    sample = _sample(api)
    grant_id = sample.grant.id
    response = api.client.post(
        f"/grants/{grant_id}/records",
        json={
            "data": {
                "kind": "accepted_reason",
                "reason": {"check": "budget", "problem": "over_limit"},
                "note": "The sponsor approved the overspend.",
            }
        },
        headers=api.headers,
    )
    assert response.status_code == 201, response.text
    acceptance = response.json()
    # The checks mark the problem accepted by it, and the other stays open.
    checks.grant_problems = [OVER.model_copy(update={"accepted_by": acceptance["id"]}), LATE]
    with transaction(api.platform.pool) as conn:
        recheck_grant(conn, checks, sample.grant, APRIL_10, Trigger(kind=TriggerKind.CLOCK))
        user = store.get_user(conn, api.user_id)
    assert user is not None

    rows = _get(api, f"/grants/{grant_id}/problems")["rows"]
    grant_rows = [r["problem"]["problem"] for r in rows if r["kind"] == "grant"]
    assert grant_rows == ["failed"]  # the accepted one left the list

    [accepted] = _get(api, f"/grants/{grant_id}")["accepted_problems"]
    assert accepted["problem"]["text"] == "Spending is $50.00 over the limit."
    assert accepted["problem"]["check"] == "budget"
    assert accepted["acceptance_id"] == acceptance["id"]
    assert accepted["note"] == "The sponsor approved the overspend."
    assert accepted["accepted_by"] == (user.name or user.email)
    assert accepted["accepted_at"] == acceptance["written_at"]


def test_a_grant_with_nothing_accepted_lists_none(api: Api) -> None:
    _checks(api).grant_problems = [OVER]
    sample = _sample(api)
    assert _get(api, f"/grants/{sample.grant.id}")["accepted_problems"] == []
