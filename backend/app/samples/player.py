"""The timeline player's database side (issue 165, first version).

A sample grant is an ordinary grant with a stored clock (`grants.clock_now`), what it was
opened from (`grants.sample`) and its pack's timeline. Nothing else about it is special.

- **Opening.** A new grant in the user's workspace, its clock at the timeline's first event,
  and every event at that moment played.
- **A move.** Forward only, to the next item or to a date. Each scheduled event the move
  passes is stored at its own time through the ordinary storing paths (a file as Gmail,
  Drive or an upload stores it; the ledger as an upload reads it), then the clock is set
  and everything stored in between is replayed in order (decision 0023): each file and
  batch of charges gets its agent run as of its own arrival time.
- **The user's items (ruling 44).** The clock stops on them and never delivers them.
- **The read-live limit (ruling 48, first version).** Only on a move, and only between the
  user's larger read-live samples: while one has agent runs queued or running from a move
  of its clock, another's clock can't move.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, time
from functools import cache

from app.checks import upcoming_dates
from app.checks.upcoming import (
    CLOSEOUT_WINDOW_OPENS,
    GRANT_ENDS,
    MISSING_FLAGGED,
    SNOOZE_ENDS,
    UpcomingDate,
)
from app.contracts.api import GrantSummary, SampleOption
from app.contracts.charges import Charge
from app.contracts.checks import ChecksInput
from app.contracts.evidence import EvidenceFile
from app.contracts.records import Author, Record
from app.contracts.runs import AgentRun, TriggerKind
from app.contracts.timeline import (
    PlayedEvent,
    TimelineEvent,
    TimelineEventKind,
    TimelineNow,
    TimelineView,
    UserDelivery,
)
from app.contracts.workspaces import Grant, GrantSample, SampleChoice
from app.db import clock, sample_store, store
from app.db.jobs import grant_catching_up
from app.db.mail_sink import arrive_files
from app.db.pings import ping_changed, ping_run
from app.db.platform import Platform
from app.db.pool import transaction
from app.db.store import Conn
from app.ingest.email_files import email_parts
from app.ingest.incoming import IncomingFile
from app.ingest.ledger import read_ledger_file

from .pack import (
    LARGER_SAMPLE,
    SMALL_SAMPLE,
    EventKind,
    PackError,
    SamplePack,
    load_pack,
    message_id_of,
)
from .timeline import (
    ChecksDate,
    ItemKind,
    OnGrant,
    TimelineItem,
    checks_items,
    coming_up,
    delivered_at,
    deliveries,
    finished,
    merge,
    pack_items,
    plan_move,
    plan_start,
    still_reading,
)

# Which pack each choice opens.
PACK_FOR_CHOICE = {
    SampleChoice.SMALL_LIVE: SMALL_SAMPLE,
    SampleChoice.LARGER_LIVE: LARGER_SAMPLE,
    SampleChoice.LARGER_PRERUN: LARGER_SAMPLE,
}
# Not built: how a prerun is saved and reused isn't settled (ruling 47).
PRERUN_UNAVAILABLE = "The already-read sample isn't ready yet."

# Short names for the checks' dates. The screens may word them their own way.
_CHECKS_NAMES = {
    SNOOZE_ENDS: "A snooze ends",
    CLOSEOUT_WINDOW_OPENS: "The closeout window opens",
    GRANT_ENDS: "The grant ends",
    MISSING_FLAGGED: "A missing item goes on the problem list",
}


class SampleError(Exception):
    """A sample request the player refuses. The message says why, in plain words."""


class NotASample(Exception):
    """The grant isn't a sample grant."""


class AnotherSampleWorking(Exception):
    """The read-live limit refuses a move: `grant` is the one still working."""

    def __init__(self, grant: Grant) -> None:
        super().__init__(grant.id)
        self.grant = grant


@cache
def pack_for(sample: str) -> SamplePack:
    return load_pack(sample)


@cache
def items_for(sample: str) -> tuple[TimelineItem, ...]:
    return pack_items(pack_for(sample))


def _sample_of(grant: Grant) -> GrantSample:
    if grant.sample is None:
        raise NotASample
    return grant.sample


# The choices.


def options() -> list[SampleOption]:
    """The Add a grant dropdown's sample choices, in order, with the packs' names."""
    out: list[SampleOption] = []
    for choice in SampleChoice:
        meta = pack_for(PACK_FOR_CHOICE[choice]).meta
        text = next(
            (o for o in meta.get("options", []) if o.get("choice") == choice.value),
            {"name": choice.value, "description": choice.value},
        )
        prerun = choice is SampleChoice.LARGER_PRERUN
        out.append(
            SampleOption(
                choice=choice,
                name=text["name"],
                description=text["description"],
                needs_confirm=choice is SampleChoice.LARGER_LIVE,
                available=not prerun,
                unavailable_reason=PRERUN_UNAVAILABLE if prerun else None,
            )
        )
    return out


# Playing events.


def _incoming(grant: Grant, pack: SamplePack, event_id: str) -> list[IncomingFile]:
    """The files a scheduled file event brings, as its channel would bring them."""
    e = pack.event(event_id)
    assert e is not None and e.kind is EventKind.FILE
    data = pack.file_bytes(e.name)
    ref = f"sample-{e.id}"  # stands in for the Gmail message ID or the Drive file ID
    if e.source.value == "gmail":
        parts = email_parts(
            data, message_id=ref, grant_id=grant.id, workspace_id=grant.workspace_id
        )
        files = parts.files
    else:
        media_type = mimetypes.guess_type(e.name)[0] or "application/octet-stream"
        files = [
            IncomingFile(
                key=ref,
                grant_id=grant.id,
                workspace_id=grant.workspace_id,
                source="drive" if e.source.value == "drive" else "upload",
                name=e.name,
                media_type=media_type,
                data=data,
                source_ref=ref if e.source.value == "drive" else None,
            )
        ]
    # A scheduled file arrives at its own time, with its dates as written.
    return [replace(f, arrived_at=e.at) for f in files]


def _ledger(p: Platform, conn: Conn, grant: Grant, content: bytes, at: datetime) -> None:
    """Read the ledger as an upload reads it, at the event's time: a line already on file,
    such as one the user uploaded early, is skipped (decision 0027: nothing is blocked)."""
    read = read_ledger_file(
        content,
        workspace_id=grant.workspace_id,
        grant_id=grant.id,
        existing_line_ids=store.ledger_line_ids(conn, grant.workspace_id),
        now=at,
    )
    if read.rejected:
        rows = ", ".join(f"row {r.row}: {r.reason}" for r in read.rejected)
        raise SampleError(f"The sample's ledger can't be read ({rows}).")
    store.insert_charges(conn, read.charges)


def _store_events(p: Platform, conn: Conn, grant: Grant, pack: SamplePack, played: Sequence[str]):
    """Store each played event at its own time, in order, as its channel would."""
    for event_id in played:
        e = pack.event(event_id)
        assert e is not None
        if e.kind is EventKind.FILE:
            arrive_files(p, conn, grant, _incoming(grant, pack, e.id))
        elif e.kind is EventKind.LEDGER:
            _ledger(p, conn, grant, pack.ledger_bytes(), e.at)
        else:
            _ledger(p, conn, grant, pack.ledger_row(e.name), e.at)


def _ping(p: Platform, grant: Grant, runs: Sequence[AgentRun]) -> None:
    for run in runs:
        ping_run(p.pinger, run)
    ping_changed(p.pinger, grant.workspace_id, grant.id, "charges", "evidence", "statuses")


def open_sample(p: Platform, workspace_id: str, choice: SampleChoice) -> Grant:
    """A new sample grant in the workspace, its clock at the timeline's first event."""
    if choice is SampleChoice.LARGER_PRERUN:
        raise SampleError(PRERUN_UNAVAILABLE)
    sample = PACK_FOR_CHOICE[choice]
    pack = pack_for(sample)
    items = items_for(sample)
    move = plan_start(items, pack.starts_at)
    with transaction(p.pool) as conn:
        # First version, pending a product answer: ledger line IDs are unique in a
        # workspace, so a second copy of a sample there couldn't take its ledger in. The
        # workspace's row lock keeps two opens from both passing the check.
        sample_store.lock_workspace(conn, workspace_id)
        if any(
            g.sample and g.sample.sample == sample for g in store.list_grants(conn, workspace_id)
        ):
            raise SampleError(
                "This workspace already has this sample. Open it in another workspace."
            )
        grant = store.create_grant(conn, workspace_id)
        store.get_grant(conn, grant.id, lock=True)
        info = GrantSample(sample=sample, choice=choice)
        sample_store.set_sample(conn, grant.id, info)
        _store_events(p, conn, grant, pack, [e.id for e in move.play])
        runs = clock.set_and_replay(p, conn, grant, None, move.until)
        sample_store.insert_move(conn, grant.id, None, move.until)
        grant = grant.model_copy(update={"clock_now": move.until, "sample": info})
    _ping(p, grant, runs)
    return grant


def check_read_live_limit(conn: Conn, user_id: str, grant: Grant) -> None:
    """The read-live limit (ruling 48, first version), for a move of `grant`'s clock."""
    if _sample_of(grant).choice is not SampleChoice.LARGER_LIVE:
        return
    for other in sample_store.users_sample_grants(conn, user_id):
        if other.id == grant.id or _sample_of(other).choice is not SampleChoice.LARGER_LIVE:
            continue
        if still_reading(sample_store.catch_up_runs_pending(conn, other.id)):
            raise AnotherSampleWorking(other)


def move(p: Platform, user_id: str, grant: Grant, to: datetime | None) -> None:
    """Move a sample grant's timeline forward: to `to`, or with None, to the next item.
    Raises MoveRefused (timeline) for a move backwards or with nothing left, and
    AnotherSampleWorking for the read-live limit."""
    info = _sample_of(grant)
    pack = pack_for(info.sample)
    with transaction(p.pool) as conn:
        # One move at a time per user, so two moves can't both pass the read-live limit
        # before either has queued its runs. Taken before the grant's lock.
        sample_store.lock_users_moves(conn, user_id)
        locked = store.get_grant(conn, grant.id, lock=True)
        assert locked is not None
        check_read_live_limit(conn, user_id, locked)
        now = clock.grant_now(conn, grant.id)
        items = merge(items_for(info.sample), checks_items(_checks_dates(p, conn, locked, now)))
        plan = plan_move(items, now, to)
        _store_events(p, conn, locked, pack, [e.id for e in plan.play])
        runs = clock.set_and_replay(p, conn, locked, now, plan.until)
        sample_store.insert_move(conn, grant.id, now, plan.until)
    _ping(p, grant, runs)


# The view.


def _checks_input(conn: Conn, grant: Grant, now: datetime) -> ChecksInput:
    return ChecksInput(
        now=now,
        charges=tuple(store.list_charges(conn, grant.id, now)),
        files=tuple(store.list_files(conn, grant.id, now)),
        records=tuple(store.list_records(conn, grant.id, now)),
        failed_runs=tuple(store.failed_runs(conn, grant.id)),
        skipped_files=tuple(store.list_skipped(conn, grant.id, now)),
    )


def _checks_dates(p: Platform, conn: Conn, grant: Grant, now: datetime) -> list[ChecksDate]:
    """The dates the checks work out after `now`, at 00:00 UTC on each."""
    found: list[UpcomingDate] = upcoming_dates(_checks_input(conn, grant, now), grant.id)
    return [
        ChecksDate(
            at=datetime.combine(d.on, time(), tzinfo=UTC),
            name=_CHECKS_NAMES.get(d.kind, d.kind),
            key="/".join(
                x or "" for x in (d.kind, d.charge_id, d.record_id, d.file_id, d.check, d.problem)
            ),
        )
        for d in found
    ]


def _on_grant(
    p: Platform, pack: SamplePack, items: Sequence[TimelineItem], files: Sequence[EvidenceFile]
) -> OnGrant:
    """What's on the grant, to tell when a user's item counts as delivered (ruling 44). An
    email's Message-ID is read only when a user's email item isn't matched by its bytes."""
    by_sha: dict[str, datetime] = {}
    for f in sorted(files, key=lambda f: f.arrived_at):
        by_sha.setdefault(f.sha256, f.arrived_at)
    on_grant = OnGrant(by_sha=by_sha)
    unmatched = [
        i
        for i in items
        if i.kind is ItemKind.USER_DELIVERY
        and i.event is not None
        and pack.message_id(i.event.name) is not None
        and delivered_at(pack, i.event, on_grant) is None
    ]
    if not unmatched:
        return on_grant
    by_message_id: dict[str, datetime] = {}
    for f in sorted(files, key=lambda f: f.arrived_at):
        if f.media_type == "message/rfc822" or f.name.lower().endswith(".eml"):
            found = _message_id(p, f)
            if found is not None:
                by_message_id.setdefault(found, f.arrived_at)
    return OnGrant(by_sha=by_sha, by_message_id=by_message_id)


# An email's Message-ID by its bytes' sha256. Stored files never change, so a file is read
# from storage once per process, not on every view.
_MESSAGE_IDS: dict[str, str | None] = {}
_MESSAGE_IDS_MAX = 10_000


def _message_id(p: Platform, f: EvidenceFile) -> str | None:
    if f.sha256 not in _MESSAGE_IDS:
        if len(_MESSAGE_IDS) >= _MESSAGE_IDS_MAX:
            _MESSAGE_IDS.clear()
        _MESSAGE_IDS[f.sha256] = message_id_of(p.storage.get(f.storage_path))
    return _MESSAGE_IDS[f.sha256]


def _event(
    item: TimelineItem,
    pack: SamplePack,
    files: Sequence[EvidenceFile],
    charges: Sequence[Charge],
) -> TimelineEvent:
    file_id = charge_id = None
    if item.line_id is not None:
        charge_id = next((c.id for c in charges if c.ledger_line_id == item.line_id), None)
    elif item.event is not None and item.event.kind is EventKind.FILE:
        sha = pack.sha256(item.event.name)
        file_id = next(
            (f.id for f in sorted(files, key=lambda f: f.arrived_at) if f.sha256 == sha), None
        )
    return TimelineEvent(
        id=item.id,
        at=item.at,
        kind=TimelineEventKind(item.kind.value),
        source=item.source,
        name=item.name,
        note=item.note,
        charge_id=charge_id,
        file_id=file_id,
    )


def _agent_records(
    event: TimelineEvent,
    runs: Sequence[AgentRun],
    records: Sequence[Record],
    charges: Sequence[Charge],
) -> tuple[Record, ...]:
    """What the agent wrote so far from the runs an event started: a file's runs, or the
    runs of the batch of charges a ledger line arrived with."""
    if event.file_id is not None:
        mine = [
            r for r in runs if r.trigger.kind is TriggerKind.FILE and r.trigger.id == event.file_id
        ]
    elif event.charge_id is not None:
        arrived = {c.id: c.arrived_at for c in charges}
        at = arrived.get(event.charge_id)
        mine = [
            r
            for r in runs
            if r.trigger.kind is TriggerKind.CHARGE and arrived.get(r.trigger.id or "") == at
        ]
    else:
        return ()
    done = {(r.read_through_seq, r.clock_now) for r in mine if r.read_through_seq is not None}
    return tuple(
        r
        for r in records
        if r.author is Author.AGENT and (r.read_through_seq, r.written_at) in done
    )


def view(p: Platform, conn: Conn, grant: Grant, summary: GrantSummary) -> TimelineView:
    """The timeline panel: Just happened, Now and Coming up (issue 165). `summary` is the
    grant's summary at its now, for the problem list's count."""
    info = _sample_of(grant)
    pack = pack_for(info.sample)
    now = clock.grant_now(conn, grant.id)
    items = merge(items_for(info.sample), checks_items(_checks_dates(p, conn, grant, now)))
    files = store.list_files(conn, grant.id, now)
    charges = store.list_charges(conn, grant.id, now)
    on_grant = _on_grant(p, pack, items, files)
    last = sample_store.last_move(conn, grant.id)
    after, until = (last.moved_from, last.moved_to) if last else (None, now)

    def in_move(at: datetime) -> bool:
        return (after is None or at > after) and at <= until

    runs = store.list_runs(conn, grant.id)
    records = store.list_records(conn, grant.id, now)
    just: list[PlayedEvent] = []
    for i in items:
        if i.kind is ItemKind.USER_DELIVERY and i.event is not None:
            # A user's item shows here for the move that brought it, by any channel.
            brought = delivered_at(pack, i.event, on_grant)
            if brought is None or not in_move(brought):
                continue
        elif not in_move(i.at):
            continue
        event = _event(i, pack, files, charges)
        just.append(
            PlayedEvent(
                event=event,
                agent_records=_agent_records(event, runs, records, charges),
                charge_ids=(event.charge_id,) if event.charge_id else (),
            )
        )
    stopped = next((i for i in items if i.at == until), None) if until == now else None
    return TimelineView(
        just_happened=tuple(just),
        now=TimelineNow(
            now=now,
            stopped_on=_event(stopped, pack, files, charges) if stopped else None,
            deliveries=tuple(
                UserDelivery(event=_event(i, pack, files, charges), delivered=False)
                for i in deliveries(pack, items, now, on_grant)
            ),
            waiting_on_problem_list=summary.on_problem_list,
        ),
        coming_up=tuple(
            _event(i, pack, files, charges) for i in coming_up(pack, items, now, on_grant)
        ),
        finished=finished(items, now),
        catching_up=grant_catching_up(conn, grant.id),
    )


__all__ = [
    "AnotherSampleWorking",
    "NotASample",
    "PackError",
    "SampleError",
    "check_read_live_limit",
    "move",
    "open_sample",
    "options",
    "view",
]
