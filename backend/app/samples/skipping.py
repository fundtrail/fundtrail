"""Skipping the human steps (ruling 47, first version).

With `skip_human_steps`, as a move's clock passes each step of the sample's accountant
script, the workspace's Sample accountant makes it through the ordinary write paths, as its
author, at the step's own time:

- **A file the user brings in** (`deliver_file`) needs no agent: it's stored at the step's
  time during the move, before the move's replay, so its run is queued in order with the
  rest. The panel tags it "delivered for you" (ruling 52).
- **A decision** waits until the agent's runs before it are done: the move records it as
  pending, and it's made when no catch-up run before its time is left, either during the
  move itself or after the catch-up run that came last before it. The clock module asks
  `due` at those points, so each decision lands between the right runs.
- **Its target** is found as `script.resolve` finds it, with the grant's clock set to the
  step's time while it's written, so what the write sees and its `written_at` are what
  resolve looked at. A step whose target isn't there, or whose write is refused (a
  sign-off while runs remain, say), is left for the user.

A scripted step is never a stop: "Go to a date" plays straight through (ruling 60).
"""

from __future__ import annotations

import logging
import mimetypes
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
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


def deliver_and_queue(
    p: Platform,
    conn: Conn,
    grant: Grant,
    pack: SamplePack,
    move_id: int,
    after: datetime,
    until: datetime,
) -> None:
    """A skipping move's steps in (after, until]: files the user brings in are stored now,
    at their times; decisions wait, pending, for the agent's runs before them."""
    for n, a in enumerate(pack.actions):
        if not after < a.at <= until:
            continue
        if a.action != "deliver_file":
            sample_store.insert_scripted(conn, grant.id, Scripted(n, move_id, a.at, "pending"))
            continue
        step = resolve(p, conn, grant, pack, a, a.at)
        if not isinstance(step, DeliverFile):
            sample_store.insert_scripted(conn, grant.id, Scripted(n, move_id, a.at, "left"))
            continue
        media_type = mimetypes.guess_type(step.name)[0] or "application/octet-stream"
        incoming = IncomingFile(
            key=f"sample-step-{n}",
            grant_id=grant.id,
            workspace_id=grant.workspace_id,
            source="upload",
            name=step.name,
            media_type=media_type,
            data=pack.file_bytes(step.name),
        )
        [f] = arrive_files(p, conn, grant, [replace(incoming, arrived_at=a.at)])
        done = Scripted(n, move_id, a.at, "done", file_id=f.id)
        sample_store.insert_scripted(conn, grant.id, done)


@dataclass(frozen=True)
class Due:
    """A pending decision, ready to make: `make` writes it in the caller's transaction."""

    at: datetime
    make: Callable[[], None]


def due(p: Platform, conn: Conn, grant: Grant, before: datetime | None) -> list[Due]:
    """The grant's pending decisions before `before` (all of them with None), in order."""
    if grant.sample is None:
        return []
    from .player import pack_for

    pack = pack_for(grant.sample.sample)
    return [
        Due(s.at, lambda s=s: _make(p, conn, grant, pack, s))
        for s in sample_store.pending_scripted(conn, grant.id, before)
    ]


def _make(p: Platform, conn: Conn, grant: Grant, pack: SamplePack, s: Scripted) -> None:
    """Make one decision at its time, as the Sample accountant, or leave it for the user."""
    action = pack.actions[s.step]
    if action.action == "sign_off" and store.has_pending_run(conn, grant.id):
        return  # a sign-off waits for the agent; tried again when the next run is done
    accountant = store.sample_accountant_id(conn, grant.workspace_id)
    now = clock.grant_now(conn, grant.id)
    record_id: str | None = None
    try:
        with conn.transaction():  # a savepoint: a refused or failed step writes nothing
            clock.set_stored_clock(conn, grant.id, s.at)
            step = resolve(p, conn, grant, pack, action, s.at)
            if isinstance(step, WriteRecord):
                record, _, _ = write_record(
                    p, conn, grant, accountant, step.data, step.replaces_id, catch_up=True
                )
                record_id = record.id
            elif isinstance(step, SignOff):
                record_id = _sign_off(p, conn, grant, accountant, step.note).id
            clock.set_stored_clock(conn, grant.id, now)
    except WriteRejected as refused:
        log.info("scripted step %s on grant %s left for the user: %s", s.step, grant.id, refused)
    except Exception:  # noqa: BLE001 - a step that fails is the user's to make
        log.exception("scripted step %s on grant %s failed; left for the user", s.step, grant.id)
    state = "done" if record_id is not None else "left"
    sample_store.finish_scripted(conn, grant.id, s.step, state, record_id)


def _sign_off(p: Platform, conn: Conn, grant: Grant, user_id: str, note: str):  # noqa: ANN202
    from app.api.report import signed_report_maker
    from app.api.views import open_check

    return write_sign_off(
        p, conn, grant, user_id, note, signed_report_maker(p, user_id), open_check(p)
    )


def made_in(conn: Conn, move_id: int) -> Sequence[Scripted]:
    return sample_store.move_scripted(conn, move_id)
