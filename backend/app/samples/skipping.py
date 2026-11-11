"""Skipping the human steps (ruling 47, first version).

With `skip_human_steps`, the workspace's Sample accountant makes the accountant script's
steps a move passes, through the ordinary write paths, as their author. The result is the
same as a user making each step at its own time while the clock walks forward:

- **The walk.** A skipping move doesn't play everything at once. Its events are played in
  time order up to the next scripted decision; the agent's runs before that decision are
  let finish; the decision is made at its own time; then the walk goes on. So an email
  that arrives after the user confirms the letter's terms meets the known-sender hold with
  the people they name already known (ruling 58), and every agent run works as of its own
  time, after everything before it. The grant's clock walks with it, and reaches the
  move's date when the walk is done.
- **When it goes on.** The move starts it; after that, each agent run's save (or failure)
  takes it on as far as it can go without waiting for the agent again, once the run has
  committed and in a transaction of its own (`go_on`), so nothing in the walk can fail or
  undo the run. Each step is made in a savepoint of its own.
- **When it stops short.** A step that fails, or whose write is refused, is left for the
  user and the walk goes on. If playing the events fails, or the walk waits on agent runs
  that no job is left to run (`check_walks`, every minute), it stops where it is: the
  steps it hadn't made are left for the user and its move keeps the reason.
- **A file the user brings in** (`deliver_file`) needs no agent: it arrives at its step's
  time with the events, and the panel tags it delivered by the Sample accountant (ruling
  52).
- **A decision** waits until no catch-up run at or before its time is left (a sign-off
  waits for every run). Its target is found as `script.resolve` finds it at that time. A
  step whose target isn't there, or whose write is refused, is left for the user.
- **A move during a walk** extends it: its events are played by the walk, from where the
  walk has got to.

A scripted step is never a stop: "Go to a date" plays straight through (ruling 60). Each
decision is listed under the move that was the grant's last when it was made.
"""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from app.contracts.runs import AgentRun
from app.contracts.workspaces import Grant
from app.db import clock, sample_store, store
from app.db.actions import WriteRejected, write_record, write_sign_off
from app.db.mail_sink import arrive_files
from app.db.pings import ping_changed, ping_run
from app.db.platform import Platform
from app.db.pool import transaction
from app.db.sample_store import Scripted
from app.db.store import Conn
from app.ingest.incoming import IncomingFile

from .pack import SamplePack
from .script import DeliverFile, SignOff, WriteRecord, resolve

log = logging.getLogger(__name__)


@dataclass
class Walked:
    """What a walk did in one go: whether anything changed on the grant, and the agent
    runs it queued. Pinged once the transaction it did them in has committed."""

    changed: bool = False
    runs: list[AgentRun] = field(default_factory=list)


def ping(p: Platform, grant: Grant, walked: Walked) -> None:
    """After the walk's transaction commits: the grant's screens refresh as after a run's
    save, its charges, files, records, statuses and threads."""
    if not walked.changed:
        return
    for run in walked.runs:
        ping_run(p.pinger, run)
    what = ("charges", "evidence", "records", "statuses", "thread")
    ping_changed(p.pinger, grant.workspace_id, grant.id, *what)


def queue_steps(
    conn: Conn, grant: Grant, pack: SamplePack, move_id: int, after: datetime, until: datetime
) -> None:
    """A skipping move's scripted steps in (after, until], pending for the walk."""
    for n, a in enumerate(pack.actions):
        if after < a.at <= until:
            sample_store.insert_scripted(conn, grant.id, Scripted(n, move_id, a.at, "pending"))


def advance(p: Platform, conn: Conn, grant: Grant) -> Walked:
    """Take the grant's walk as far as it goes without waiting for the agent: play the
    events up to the next scripted decision, make the decision once the agent's runs
    before it are done, and so on to the walk's end. The caller holds the grant's lock.

    It never raises for something in the walk. Each step is made in a savepoint of its
    own: a scripted step that fails is left for the user and the walk goes on; any other
    step that fails is undone and stops the walk where it is, with the reason on its move.
    Returns what it did, for the caller to ping after commit (`ping`)."""
    walked = Walked()
    if grant.sample is None or sample_store.walk_target(conn, grant.id) is None:
        return walked
    from .player import pack_for

    while True:
        try:
            with conn.transaction():  # a savepoint: a failed step is undone, earlier ones stand
                going = _step(p, conn, grant, pack_for(grant.sample.sample), walked)
        except Exception as error:  # noqa: BLE001 - the walk stops; nothing else fails with it
            log.exception("the walk on grant %s stopped", grant.id)
            stop(conn, grant.id, _reason(conn, grant.id, error))
            walked.changed = True
            return walked
        if not going:
            return walked


def _step(p: Platform, conn: Conn, grant: Grant, pack: SamplePack, walked: Walked) -> bool:
    """One step of the walk, noted in `walked`. Returns whether the walk can go on at once."""
    target = sample_store.walk_target(conn, grant.id)
    if target is None:
        return False
    now = clock.grant_now(conn, grant.id)
    pending = sample_store.pending_scripted(conn, grant.id, None)
    decision = next((s for s in pending if pack.actions[s.step].action != "deliver_file"), None)
    until = min(decision.at, target) if decision is not None else target
    if until > now:
        walked.runs.extend(_play(p, conn, grant, pack, pending, now, until))
        walked.changed = True
        return True
    if decision is None:
        sample_store.end_walk(conn, grant.id)
        walked.changed = True
        return False
    action = pack.actions[decision.step]
    if action.action == "sign_off":
        if store.has_pending_run(conn, grant.id):
            return False  # a sign-off waits for every run
    elif sample_store.catch_up_runs_before(conn, grant.id, decision.at):
        return False  # the agent is still reading what came before it
    _make(p, conn, grant, pack, decision)
    walked.changed = True
    return True


def _play(
    p: Platform,
    conn: Conn,
    grant: Grant,
    pack: SamplePack,
    pending: list[Scripted],
    now: datetime,
    until: datetime,
) -> list[AgentRun]:
    """Every event, and every file the user brings in, after `now` up to `until`, and the
    clock to `until`; returns the agent runs it queued. Raises WalkStopped, with the
    reason, if it fails."""
    from .player import store_events

    try:
        played = [e.id for e in pack.events if now < e.at <= until and not e.deliver_by_user]
        store_events(p, conn, grant, pack, played)
        for s in pending:
            if pack.actions[s.step].action == "deliver_file" and s.at <= until:
                _deliver(p, conn, grant, pack, s)
        return clock.set_and_replay(p, conn, grant, now, until)
    except Exception as error:
        raise WalkStopped(
            f"The walk stopped at {_when(now)}: what comes after couldn't be played "
            f"({type(error).__name__})."
        ) from error


def _deliver(p: Platform, conn: Conn, grant: Grant, pack: SamplePack, s: Scripted) -> None:
    """A file the user brings in, at its step's time, as an upload, by the Sample
    accountant. One that can't be brought in is left for the user."""
    a = pack.actions[s.step]
    file_id: str | None = None
    try:
        with conn.transaction():  # a savepoint: a failed delivery brings nothing in
            step = resolve(p, conn, grant, pack, a, a.at)
            if isinstance(step, DeliverFile):
                media_type = mimetypes.guess_type(step.name)[0] or "application/octet-stream"
                incoming = IncomingFile(
                    key=f"sample-step-{s.step}",
                    grant_id=grant.id,
                    workspace_id=grant.workspace_id,
                    source="upload",
                    name=step.name,
                    media_type=media_type,
                    data=pack.file_bytes(step.name),
                )
                [f] = arrive_files(p, conn, grant, [replace(incoming, arrived_at=a.at)])
                file_id = f.id
    except Exception:  # noqa: BLE001 - a delivery that fails is the user's to make
        log.exception("scripted step %s on grant %s failed; left for the user", s.step, grant.id)
    state = "done" if file_id is not None else "left"
    sample_store.finish_scripted(conn, grant.id, s.step, state, file_id=file_id)


def _make(p: Platform, conn: Conn, grant: Grant, pack: SamplePack, s: Scripted) -> None:
    """Make one decision at its time, as the Sample accountant, or leave it for the user.
    The grant's clock stands at the decision's time. It's listed under the grant's last
    move, the one it was made in."""
    action = pack.actions[s.step]
    accountant = store.sample_accountant_id(conn, grant.workspace_id)
    record_id: str | None = None
    try:
        with conn.transaction():  # a savepoint: a refused or failed step writes nothing
            step = resolve(p, conn, grant, pack, action, s.at)
            if isinstance(step, WriteRecord):
                record, _, _ = write_record(
                    p, conn, grant, accountant, step.data, step.replaces_id, catch_up=True
                )
                record_id = record.id
            elif isinstance(step, SignOff):
                record_id = _sign_off(p, conn, grant, accountant, step.note).id
    except WriteRejected as refused:
        log.info("scripted step %s on grant %s left for the user: %s", s.step, grant.id, refused)
    except Exception:  # noqa: BLE001 - a step that fails is the user's to make
        log.exception("scripted step %s on grant %s failed; left for the user", s.step, grant.id)
    last = sample_store.last_move(conn, grant.id)
    state = "done" if record_id is not None else "left"
    sample_store.finish_scripted(
        conn, grant.id, s.step, state, record_id, move_id=last.id if last else None
    )


# Stopping.


class WalkStopped(Exception):
    """The walk can't go on; the message is the reason the panel shows."""


def stop(conn: Conn, grant_id: str, reason: str) -> None:
    """Stop the walk where it is: the clock stays, the steps not yet made whose time has
    come are left for the user, later ones are dropped (a later skipping move queues them
    again), and the grant's last move keeps `reason`."""
    sample_store.stop_walk(conn, grant_id, clock.grant_now(conn, grant_id), reason)


def _when(at: datetime) -> str:
    return f"{at.astimezone(UTC):%Y-%m-%d %H:%M} UTC"


def _reason(conn: Conn, grant_id: str, error: Exception) -> str:
    if isinstance(error, WalkStopped):
        return str(error)
    return (
        f"The walk stopped at {_when(clock.grant_now(conn, grant_id))}: "
        f"something went wrong ({type(error).__name__})."
    )


def go_on(p: Platform, grant_id: str) -> None:
    """After an agent run's save or failure has committed: the grant's walk goes on, in a
    transaction of its own, so nothing in the walk can fail or undo the run."""
    try:
        with transaction(p.pool) as conn:
            grant = store.get_grant(conn, grant_id, lock=True)
            if grant is None or grant.sample is None:
                return
            walked = advance(p, conn, grant)
    except Exception:  # noqa: BLE001 - the run stands; check_walks takes the walk on later
        log.exception("the walk on grant %s didn't go on after a run", grant_id)
        return
    ping(p, grant, walked)


# Two checks a minute apart that find a walk waiting on runs no job will run stop it.
IDLE_CHECKS = 2
NO_JOB = "The walk stopped at {}: an agent run it was waiting for has nothing left to run it."


def check_walks(p: Platform) -> None:
    """Every minute: each walk under way goes on if nothing holds it (a walk whose going on
    after a run was lost), and one waiting on agent runs that no job will ever run stops,
    once two checks in a row find it so."""
    with transaction(p.pool) as conn:
        walking = sample_store.walking_grants(conn)
    for grant_id in walking:
        try:
            with transaction(p.pool) as conn:
                grant = store.get_grant(conn, grant_id, lock=True)
                if grant is None or grant.sample is None:
                    continue
                walked = Walked()
                if not store.has_pending_run(conn, grant_id):
                    sample_store.idle_check(conn, grant_id, False)
                    walked = advance(p, conn, grant)
                else:
                    stuck = not sample_store.live_run_jobs(conn, grant_id)
                    if sample_store.idle_check(conn, grant_id, stuck) >= IDLE_CHECKS:
                        now = clock.grant_now(conn, grant_id)
                        stop(conn, grant_id, NO_JOB.format(_when(now)))
                        walked.changed = True
        except Exception:  # noqa: BLE001 - one grant's walk mustn't hold up the others'
            log.exception("checking the walk on grant %s failed", grant_id)
            continue
        ping(p, grant, walked)


def _sign_off(p: Platform, conn: Conn, grant: Grant, user_id: str, note: str):  # noqa: ANN202
    from app.api.report import signed_report_maker
    from app.api.views import open_check

    return write_sign_off(
        p, conn, grant, user_id, note, signed_report_maker(p, user_id), open_check(p)
    )
