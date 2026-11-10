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


def drop_queued_jobs(conn: Conn, grant_id: str) -> None:
    """Remove the grant's agent-run jobs still waiting to start. One already running
    finishes, and its save finds its run gone."""
    conn.execute(
        "delete from procrastinate_jobs where lock = %s and status = 'todo'",
        (grant_lock(grant_id),),
    )


def remake_grant(conn: Conn, grant: Grant) -> None:
    """Remove the grant's row, and with it everything that hangs off it, and make it again
    with the same ID, workspace, funder, address and Drive folder. What the agent read into
    it (award number and title) goes; its clock and sample are set again by the caller."""
    conn.execute("delete from public.grants where id = %s", (grant.id,))
    conn.execute(
        """insert into public.grants (id, workspace_id, funder, address_code, drive_folder_id)
           values (%s, %s, %s, %s, %s)""",
        (grant.id, grant.workspace_id, grant.funder, grant.address_code, grant.drive_folder_id),
    )


def lock_users_moves(conn: Conn, user_id: str) -> None:
    """Take this user's sample-move lock until the transaction ends: one move of the user's
    sample clocks at a time, so the read-live limit sees every earlier move's runs."""
    conn.execute(
        "select pg_advisory_xact_lock(hashtextextended('read-live:' || %s, 0))", (user_id,)
    )


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
