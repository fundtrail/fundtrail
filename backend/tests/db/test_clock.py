"""The grant's clock: one answer to "what time is it for this grant", and the daily recheck
of every grant at its own now."""

from __future__ import annotations

from datetime import UTC, datetime

from app.contracts.checks import ChecksInput
from app.contracts.runs import Trigger, TriggerKind
from app.contracts.workspaces import Grant, User
from app.db import actions, clock, store
from app.db.jobs import queue_run
from app.db.platform import Platform
from app.db.pool import transaction
from app.db.recheck import recheck_grant
from tests.db.platform_fixtures import (  # noqa: F401 - fixtures
    FakeChecks,
    new_auth_user,
    platform,
    platform_database_url,
    sample_into_db,
)

STILL = datetime(2026, 3, 3, 12, tzinfo=UTC)


def _real_grant(p: Platform) -> Grant:
    user_id = new_auth_user(p)
    with transaction(p.pool) as conn:
        store.upsert_user(conn, User(id=user_id, email="pat@university.example"))
        workspace = store.create_workspace(conn, user_id, "Lab")
    upload = actions.Upload("invoice.txt", "text/plain", b"INVOICE INV-1001\nTotal: $1.00\n")
    return actions.add_grant(p, workspace.id, upload)


def _grants_in(ci: ChecksInput) -> set[str]:
    return (
        {c.grant_id for c in ci.charges}
        | {f.grant_id for f in ci.files}
        | {r.grant_id for r in ci.records}
    )


def _checks(p: Platform) -> FakeChecks:
    assert isinstance(p.checks, FakeChecks)
    return p.checks


def test_grant_now_is_the_stored_clock_or_the_transactions_time(
    platform: Platform,  # noqa: F811
) -> None:
    sample = sample_into_db(platform, clock_now=STILL)
    real = _real_grant(platform)
    with transaction(platform.pool) as conn:
        assert clock.grant_now(conn, sample.grant.id) == STILL
        row = conn.execute("select now() as now").fetchone()
        assert row is not None
        # One real "now" source: the database's time for this transaction, all through it.
        assert clock.grant_now(conn, real.id) == row["now"]
        assert clock.grant_now(conn, real.id) == row["now"]


def test_the_daily_recheck_rechecks_every_grant_at_its_own_now(
    platform: Platform,  # noqa: F811
) -> None:
    sample = sample_into_db(platform, clock_now=STILL)
    real = _real_grant(platform)
    with transaction(platform.pool) as conn:
        recheck_grant(conn, platform.checks, sample.grant, STILL, Trigger(kind=TriggerKind.CLOCK))
    with transaction(platform.pool) as conn:
        before = len(store.grant_status_history(conn, sample.grant.id, STILL))
        started = conn.execute("select now() as now").fetchone()
    assert started is not None
    checks = _checks(platform)
    checks.calls.clear()
    clock.daily_recheck(platform)
    by_grant = {g: ci.now for ci in checks.calls for g in _grants_in(ci)}
    assert by_grant[sample.grant.id] == STILL
    assert by_grant[real.id] >= started["now"]
    with transaction(platform.pool) as conn:
        # A clock that hasn't moved changes nothing, so nothing is written.
        assert len(store.grant_status_history(conn, sample.grant.id, STILL)) == before


def test_the_daily_recheck_leaves_a_catching_up_grant_to_its_runs(
    platform: Platform,  # noqa: F811
) -> None:
    sample = sample_into_db(platform, clock_now=STILL)
    with transaction(platform.pool) as conn:
        queue_run(conn, sample.grant, Trigger(kind=TriggerKind.CLOCK), STILL, catch_up=True)
    checks = _checks(platform)
    checks.calls.clear()
    clock.daily_recheck(platform)
    assert all(sample.grant.id not in _grants_in(ci) for ci in checks.calls)
