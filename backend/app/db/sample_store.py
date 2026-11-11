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
    """One move of a sample grant's clock. `moved_from` is the clock when the move was
    made (None when the sample was opened): what the clock passes from there while the
    move is the grant's last is what the move played, a walk's later steps included.
    `moved_to` is where it's going."""

    moved_from: datetime | None
    moved_to: datetime
    id: int = 0
    walk_stopped: str | None = None  # why its walk stopped short of moved_to
    reached: str | None = None  # a Next highlight move: the highlight it went to (ruling 85)


@dataclass(frozen=True)
class Scripted:
    """One step of the accountant script a skipping move made, or will make."""

    step: int  # its place in the pack's script
    move_id: int
    at: datetime
    state: str  # pending, done, left, or held (by a Next highlight move, ruling 77)
    record_id: str | None = None
    file_id: str | None = None


def set_sample(conn: Conn, grant_id: str, sample: GrantSample) -> None:
    conn.execute(
        "update public.grants set sample = %s where id = %s",
        (Jsonb(sample.model_dump(mode="json")), grant_id),
    )


def insert_move(conn: Conn, grant_id: str, moved_from: datetime | None, moved_to: datetime) -> int:
    row = conn.execute(
        """insert into public.sample_moves (grant_id, moved_from, moved_to)
           values (%s, %s, %s) returning id""",
        (grant_id, moved_from, moved_to),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def last_move(conn: Conn, grant_id: str) -> SampleMove | None:
    row = conn.execute(
        """select id, moved_from, moved_to, walk_stopped, reached from public.sample_moves
           where grant_id = %s order by id desc limit 1""",
        (grant_id,),
    ).fetchone()
    if row is None:
        return None
    return SampleMove(
        row["moved_from"], row["moved_to"], int(row["id"]), row["walk_stopped"], row["reached"]
    )


def set_reached(conn: Conn, move_id: int, highlight: str) -> None:
    """The highlight a Next highlight move went to (ruling 85)."""
    conn.execute("update public.sample_moves set reached = %s where id = %s", (highlight, move_id))


_SCRIPTED = "step, move_id, at, state, record_id, file_id"


def insert_scripted(conn: Conn, grant_id: str, s: Scripted) -> None:
    """A step a move queued. One already on the grant (held, taken up, made or left) stays
    as it is: a step is queued at most once per grant."""
    conn.execute(
        f"""insert into public.sample_scripted (grant_id, {_SCRIPTED})
            values (%s, %s, %s, %s, %s, %s, %s)
            on conflict (grant_id, step) do nothing""",
        (grant_id, s.step, s.move_id, s.at, s.state, s.record_id, s.file_id),
    )


def finish_scripted(
    conn: Conn,
    grant_id: str,
    step: int,
    state: str,
    record_id: str | None = None,
    *,
    file_id: str | None = None,
    move_id: int | None = None,
) -> None:
    """A step made (done) or left for the user. `move_id` moves it under the move it was
    made in, when that's a later move than the one that passed it."""
    conn.execute(
        """update public.sample_scripted
             set state = %s, record_id = %s, file_id = coalesce(%s, file_id),
                 move_id = coalesce(%s, move_id)
           where grant_id = %s and step = %s""",
        (state, record_id, file_id, move_id, grant_id, step),
    )


def walk_target(conn: Conn, grant_id: str) -> datetime | None:
    """Where a skipping move's walk is going, while it's under way."""
    row = conn.execute(
        "select target from public.sample_walks where grant_id = %s", (grant_id,)
    ).fetchone()
    return row["target"] if row else None


def start_walk(conn: Conn, grant_id: str, target: datetime) -> None:
    conn.execute(
        """insert into public.sample_walks (grant_id, target) values (%s, %s)
           on conflict (grant_id) do update
             set target = greatest(sample_walks.target, excluded.target)""",
        (grant_id, target),
    )


def end_walk(conn: Conn, grant_id: str) -> None:
    conn.execute("delete from public.sample_walks where grant_id = %s", (grant_id,))


def stop_walk(conn: Conn, grant_id: str, now: datetime, reason: str) -> None:
    """End the walk short of its date at `now`, the grant's clock: its steps not yet made
    whose time has come are left for the user; later ones are dropped, as no move has
    passed them, so a later skipping move queues them again. The grant's last move keeps
    the reason."""
    end_walk(conn, grant_id)
    conn.execute(
        """update public.sample_scripted set state = 'left'
           where grant_id = %s and state = 'pending' and at <= %s""",
        (grant_id, now),
    )
    conn.execute(
        """delete from public.sample_scripted
           where grant_id = %s and state = 'pending' and at > %s""",
        (grant_id, now),
    )
    conn.execute(
        """update public.sample_moves set walk_stopped = %s
           where id = (select max(id) from public.sample_moves where grant_id = %s)""",
        (reason, grant_id),
    )


def walking_grants(conn: Conn) -> list[str]:
    """The grants with a walk under way."""
    rows = conn.execute("select grant_id from public.sample_walks order by grant_id").fetchall()
    return [r["grant_id"] for r in rows]


def idle_check(conn: Conn, grant_id: str, idle: bool) -> int:
    """Count one more check that found the walk waiting on runs no job will run (`idle`),
    or start the count again. Returns the count."""
    row = conn.execute(
        """update public.sample_walks
             set idle_checks = case when %s then idle_checks + 1 else 0 end
           where grant_id = %s returning idle_checks""",
        (idle, grant_id),
    ).fetchone()
    return int(row["idle_checks"]) if row else 0


def live_run_jobs(conn: Conn, grant_id: str) -> bool:
    """Whether a job of the grant's agent runs is waiting to start or running."""
    row = conn.execute(
        """select 1 from procrastinate_jobs
           where lock = %s and status in ('todo', 'doing') limit 1""",
        (grant_lock(grant_id),),
    ).fetchone()
    return row is not None


def catch_up_runs_before(conn: Conn, grant_id: str, at: datetime) -> bool:
    """Whether an agent run working as of `at` or earlier is still queued or running."""
    row = conn.execute(
        """select 1 from public.agent_runs
           where grant_id = %s and status in ('queued', 'running') and clock_now <= %s limit 1""",
        (grant_id, at),
    ).fetchone()
    return row is not None


def pending_scripted(conn: Conn, grant_id: str, before: datetime | None) -> list[Scripted]:
    """The steps still to make, in time order: before `before`, or all with None."""
    rows = conn.execute(
        f"""select {_SCRIPTED} from public.sample_scripted
            where grant_id = %s and state = 'pending' and (%s::timestamptz is null or at < %s)
            order by at, step""",
        (grant_id, before, before),
    ).fetchall()
    return [Scripted(**r) for r in rows]


def held_scripted(conn: Conn, grant_id: str) -> list[Scripted]:
    """The steps a Next highlight move held for the user (ruling 77), in time order."""
    rows = conn.execute(
        f"""select {_SCRIPTED} from public.sample_scripted
            where grant_id = %s and state = 'held' order by at, step""",
        (grant_id,),
    ).fetchall()
    return [Scripted(**r) for r in rows]


def take_up_scripted(conn: Conn, grant_id: str, step: int, move_id: int) -> None:
    """A held step, pending again for a later skipping move's walk, under that move."""
    conn.execute(
        """update public.sample_scripted set state = 'pending', move_id = %s
           where grant_id = %s and step = %s and state = 'held'""",
        (move_id, grant_id, step),
    )


def grant_scripted(conn: Conn, grant_id: str) -> list[Scripted]:
    """Every scripted step on the grant, in time order."""
    rows = conn.execute(
        f"select {_SCRIPTED} from public.sample_scripted where grant_id = %s order by at, step",
        (grant_id,),
    ).fetchall()
    return [Scripted(**r) for r in rows]


def move_scripted(conn: Conn, move_id: int) -> list[Scripted]:
    """The steps one move made or will make, in time order."""
    rows = conn.execute(
        f"select {_SCRIPTED} from public.sample_scripted where move_id = %s order by at, step",
        (move_id,),
    ).fetchall()
    return [Scripted(**r) for r in rows]


def scripted_files(conn: Conn, grant_id: str) -> dict[str, int]:
    """The files the Sample accountant brought in on the grant, with the move each is
    listed under: the grant's last move when it was brought."""
    rows = conn.execute(
        """select file_id, move_id from public.sample_scripted
           where grant_id = %s and file_id is not null""",
        (grant_id,),
    ).fetchall()
    return {r["file_id"]: int(r["move_id"]) for r in rows}


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
