"""The connection pool and the workspace clock."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def _utc(conn: Connection[dict[str, Any]]) -> None:
    """Every session reads and writes times in UTC, whatever the server's TimeZone, so a
    datetime read back is UTC and its .date() is the UTC day (status dates, midnights).
    Set with SET on each new connection rather than a startup option, which a connection
    pooler may not pass on."""
    conn.execute("set time zone 'UTC'")
    conn.commit()


def open_pool(
    database_url: str, *, max_size: int = 10
) -> ConnectionPool[Connection[dict[str, Any]]]:
    pool = ConnectionPool(
        database_url,
        min_size=1,
        max_size=max_size,
        kwargs={"row_factory": dict_row, "autocommit": False},
        connection_class=Connection[dict[str, Any]],
        configure=_utc,
        open=False,
    )
    pool.open(wait=True)
    return pool


@contextmanager
def transaction(
    pool: ConnectionPool[Connection[dict[str, Any]]],
) -> Iterator[Connection[dict[str, Any]]]:
    """One transaction: committed when the block ends, rolled back if it raises."""
    with pool.connection() as conn:
        yield conn
