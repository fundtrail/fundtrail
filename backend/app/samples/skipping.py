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
  takes it on as far as it can go without waiting for the agent again.
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
from dataclasses import replace
from datetime import datetime

from app.contracts.workspaces import Grant
from app.db import clock, sample_store, store
from app.db.actions import WriteRejected, write_record, write_sign_off
from app.db.mail_sink import arrive_files
from app.db.platform import Platform
from app.db.sample_store import Scripted
from app.db.store import Conn
from app.ingest.incoming import IncomingFile

from .pack import SamplePack
from .script import DeliverFile, SignOff, WriteRecord, resolve

log = logging.getLogger(__name__)


def queue_steps(
    conn: Conn, grant: Grant, pack: SamplePack, move_id: int, after: datetime, until: datetime
) -> None:
    """A skipping move's scripted steps in (after, until], pending for the walk."""
    for n, a in enumerate(pack.actions):
        if after < a.at <= until:
            sample_store.insert_scripted(conn, grant.id, Scripted(n, move_id, a.at, "pending"))


def advance(p: Platform, conn: Conn, grant: Grant) -> None:
    """Take the grant's walk as far as it goes without waiting for the agent: play the
    events up to the next scripted decision, make the decision once the agent's runs
    before it are done, and so on to the walk's end. The caller holds the grant's lock."""
    if grant.sample is None:
        return
    target = sample_store.walk_target(conn, grant.id)
    if target is None:
        return
    from .player import pack_for, store_events

    pack = pack_for(grant.sample.sample)
    while True:
        now = clock.grant_now(conn, grant.id)
        pending = sample_store.pending_scripted(conn, grant.id, None)
        decision = next((s for s in pending if pack.actions[s.step].action != "deliver_file"), None)
        until = min(decision.at, target) if decision is not None else target
        if until > now:
            # Every event, and every file the user brings in, up to the next decision.
            played = [e.id for e in pack.events if now < e.at <= until and not e.deliver_by_user]
            store_events(p, conn, grant, pack, played)
            for s in pending:
                if pack.actions[s.step].action == "deliver_file" and s.at <= until:
                    _deliver(p, conn, grant, pack, s)
            clock.set_and_replay(p, conn, grant, now, until)
            continue
        if decision is None:
            sample_store.end_walk(conn, grant.id)
            return
        action = pack.actions[decision.step]
        if action.action == "sign_off":
            if store.has_pending_run(conn, grant.id):
                return  # a sign-off waits for every run
        elif sample_store.catch_up_runs_before(conn, grant.id, decision.at):
            return  # the agent is still reading what came before it
        _make(p, conn, grant, pack, decision)


def _deliver(p: Platform, conn: Conn, grant: Grant, pack: SamplePack, s: Scripted) -> None:
    """A file the user brings in, at its step's time, as an upload, by the Sample accountant."""
    a = pack.actions[s.step]
    step = resolve(p, conn, grant, pack, a, a.at)
    if not isinstance(step, DeliverFile):
        sample_store.finish_scripted(conn, grant.id, s.step, "left")
        return
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
    sample_store.finish_scripted(conn, grant.id, s.step, "done", file_id=f.id)


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


def _sign_off(p: Platform, conn: Conn, grant: Grant, user_id: str, note: str):  # noqa: ANN202
    from app.api.report import signed_report_maker
    from app.api.views import open_check

    return write_sign_off(
        p, conn, grant, user_id, note, signed_report_maker(p, user_id), open_check(p)
    )
