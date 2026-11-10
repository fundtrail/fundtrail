"""The connection pool and the workspace clock."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.contracts.workspaces import Workspace


def open_pool(
    database_url: str, *, max_size: int = 10
) -> ConnectionPool[Connection[dict[str, Any]]]:
    pool = ConnectionPool(
        database_url,
        min_size=1,
        max_size=max_size,
        kwargs={"row_factory": dict_row, "autocommit": False},
        connection_class=Connection[dict[str, Any]],
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


def workspace_now(workspace: Workspace) -> datetime:
    """The workspace clock's "now". A workspace with no clock set runs on the real date."""
    return workspace.clock_now or datetime.now(UTC)
