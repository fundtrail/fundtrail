"""Database access for sample grants (issue 165): what a sample grant was opened from, and
the moves of its timeline. The rest of a sample grant is an ordinary grant's."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from psycopg.types.json import Jsonb

from app.contracts.workspaces import Grant, GrantSample

from . import store
from .jobs import grant_lock
from .store import Conn


@dataclass(frozen=True)
class SampleMove:
    moved_from: datetime | None  # None when the sample was opened
    moved_to: datetime


def set_sample(conn: Conn, grant_id: str, sample: GrantSample) -> None:
    conn.execute(
        "update public.grants set sample = %s where id = %s",
        (Jsonb(sample.model_dump(mode="json")), grant_id),
    )


def insert_move(conn: Conn, grant_id: str, moved_from: datetime | None, moved_to: datetime) -> None:
    conn.execute(
        "insert into public.sample_moves (grant_id, moved_from, moved_to) values (%s, %s, %s)",
        (grant_id, moved_from, moved_to),
    )


def last_move(conn: Conn, grant_id: str) -> SampleMove | None:
    row = conn.execute(
        """select moved_from, moved_to from public.sample_moves
           where grant_id = %s order by id desc limit 1""",
        (grant_id,),
    ).fetchone()
    return SampleMove(row["moved_from"], row["moved_to"]) if row else None


def users_sample_grants(conn: Conn, user_id: str) -> list[Grant]:
    """Every sample grant in the workspaces this user may reach."""
    return [
        g
        for w in store.list_workspaces(conn, user_id)
        for g in store.list_grants(conn, w.id)
        if g.sample is not None
    ]


def catch_up_runs_pending(conn: Conn, grant_id: str) -> int:
    """How many agent runs from moves of the grant's clock (catch-up runs) are queued or
    running, retries included."""
    row = conn.execute(
        """select count(*) as n from procrastinate_jobs
           where lock = %s and status in ('todo', 'doing') and (args ->> 'catch_up')::boolean""",
        (grant_lock(grant_id),),
    ).fetchone()
    assert row is not None
    return int(row["n"])
