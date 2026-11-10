"""The pool's sessions run in UTC whatever the server's TimeZone, so a datetime read back
is UTC and its .date() is the UTC day (PR 203's review: status dates and the clock's
midnights shifted a day in a Los Angeles session)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import psycopg
from psycopg import conninfo, sql

from app.db.pool import open_pool, transaction
from tests.db.platform_fixtures import platform_database_url  # noqa: F401 - fixture

LATE_EVENING_IN_LA = datetime(2026, 4, 10, 2, 0, tzinfo=UTC)  # Apr 9, 19:00 in Los Angeles


def test_a_los_angeles_server_still_reads_utc_days(platform_database_url: str) -> None:  # noqa: F811
    name = conninfo.conninfo_to_dict(platform_database_url)["dbname"]
    assert isinstance(name, str)
    with psycopg.connect(platform_database_url, autocommit=True) as admin:
        admin.execute(
            sql.SQL("alter database {} set timezone = 'America/Los_Angeles'").format(
                sql.Identifier(name)
            )
        )
    try:
        # A session left at the server's default reads the evening of the 9th.
        with psycopg.connect(platform_database_url) as raw:
            row = raw.execute("select %s::timestamptz", (LATE_EVENING_IN_LA,)).fetchone()
        assert row is not None and row[0].date() == date(2026, 4, 9)
        # The pool's sessions read the 10th, in UTC.
        pool = open_pool(platform_database_url, max_size=1)
        try:
            with transaction(pool) as conn:
                got = conn.execute(
                    "select %s::timestamptz as at, current_setting('TimeZone') as tz",
                    (LATE_EVENING_IN_LA,),
                ).fetchone()
        finally:
            pool.close()
        assert got is not None and got["tz"] == "UTC"
        assert got["at"].utcoffset() == timedelta(0)
        assert got["at"].date() == date(2026, 4, 10)
    finally:
        with psycopg.connect(platform_database_url, autocommit=True) as admin:
            admin.execute(sql.SQL("alter database {} reset timezone").format(sql.Identifier(name)))
