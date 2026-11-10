"""Database access: records round-trip as contract models in the order written, only
what's arrived by the clock is visible, and a status row is written only when it changes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.contracts.checks import Bucket
from app.contracts.runs import Trigger, TriggerKind
from app.db import store
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


def test_the_sample_grant_round_trips_in_the_order_written(platform: Platform) -> None:  # noqa: F811
    sample = sample_into_db(platform)
    grant = sample.grant
    far = datetime(2100, 1, 1, tzinfo=UTC)
    with transaction(platform.pool) as conn:
        records = store.list_records(conn, grant.id, far)
        charges = store.list_charges(conn, grant.id, far)
        files = store.list_files(conn, grant.id, far)
    assert [r.data for r in records] == [r.data for r in sample.records]
    assert [r.written_at for r in records] == [r.written_at for r in sample.records]
    assert [c.ledger_line_id for c in charges] == ["L-1001", "L-1002"]
    assert {f.name for f in files} == {f.name for f in sample.files}


def test_only_what_has_arrived_by_the_clock_is_visible(platform: Platform) -> None:  # noqa: F811
    grant = sample_into_db(platform).grant
    at = datetime(2025, 11, 14, 12, tzinfo=UTC)
    with transaction(platform.pool) as conn:
        assert [c.ledger_line_id for c in store.list_charges(conn, grant.id, at)] == ["L-1001"]
        records = store.list_records(conn, grant.id, at)
        files = store.list_files(conn, grant.id, at)
    assert all(r.written_at <= at for r in records)
    assert all(f.arrived_at <= at for f in files)


def test_a_status_row_is_written_only_when_the_status_changes(platform: Platform) -> None:  # noqa: F811
    grant = sample_into_db(platform).grant
    checks = platform.checks
    assert isinstance(checks, FakeChecks)
    at = datetime(2026, 2, 24, 12, tzinfo=UTC)
    clock = Trigger(kind=TriggerKind.CLOCK)

    def count() -> int:
        with transaction(platform.pool) as conn:
            row = conn.execute(
                "select count(*) as n from public.statuses where grant_id = %s", (grant.id,)
            ).fetchone()
        assert row is not None
        return row["n"]

    with transaction(platform.pool) as conn:
        recheck_grant(conn, checks, grant, at, clock)
    assert count() == 2
    with transaction(platform.pool) as conn:
        recheck_grant(conn, checks, grant, at + timedelta(hours=1), clock)
    assert count() == 2
    checks.buckets["L-1002"] = Bucket.POSSIBLE_CONFLICT
    record_trigger = Trigger(kind=TriggerKind.RECORD, id="r-1")
    with transaction(platform.pool) as conn:
        recheck_grant(conn, checks, grant, at + timedelta(hours=2), record_trigger)
        statuses = store.current_statuses(conn, grant.id)
        row = conn.execute(
            """select trigger_kind, trigger_id from public.current_statuses
               where grant_id = %s and bucket = 'possible_conflict'""",
            (grant.id,),
        ).fetchone()
    assert count() == 3
    assert row == {"trigger_kind": "record", "trigger_id": "r-1"}
    buckets = sorted(s.bucket for s in statuses.values())  # pyright: ignore[reportAttributeAccessIssue]
    assert buckets == [Bucket.EVIDENCE_COMPLETE, Bucket.POSSIBLE_CONFLICT]
