"""The workspace clock moves onto its grants (issue 165), and its column goes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, LiteralString, cast

from tests.db.conftest import MIGRATIONS_DIR
from tests.db.test_first_migration import insert, make_grant

if TYPE_CHECKING:
    import psycopg

MIGRATION = MIGRATIONS_DIR / "20261111010000_clock_moves_to_grants.sql"
WORKSPACE_CLOCK = datetime(2026, 4, 10, 17, tzinfo=UTC)
GRANT_CLOCK = datetime(2025, 1, 1, tzinfo=UTC)


def _clock(db: psycopg.Connection, grant_id: str) -> datetime | None:
    row = db.execute("select clock_now from public.grants where id = %s", (grant_id,)).fetchone()
    assert row is not None
    return row[0]


def test_the_workspace_clock_moves_onto_its_grants(db: psycopg.Connection) -> None:
    # As the database stood before: the workspace clock column, put back for this test
    # (the test's transaction is rolled back after it).
    db.execute("alter table public.workspaces add column clock_now timestamptz")
    simulated = make_grant(db)
    own = insert(db, "grants", workspace_id=simulated["workspace_id"], clock_now=GRANT_CLOCK)
    real = make_grant(db)
    db.execute(
        "update public.workspaces set clock_now = %s where id = %s",
        (WORKSPACE_CLOCK, simulated["workspace_id"]),
    )

    db.execute(cast(LiteralString, MIGRATION.read_text()))

    assert _clock(db, simulated["grant_id"]) == WORKSPACE_CLOCK
    assert _clock(db, own) == GRANT_CLOCK  # a grant's own clock is kept
    assert _clock(db, real["grant_id"]) is None  # the real date stays the real date
    column = db.execute(
        """select 1 from information_schema.columns
           where table_schema = 'public' and table_name = 'workspaces'
             and column_name = 'clock_now'"""
    ).fetchone()
    assert column is None
