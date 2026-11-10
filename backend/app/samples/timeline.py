"""The timeline player's pure logic: no database, no clock of its own.

A sample grant's timeline is its pack's scheduled events, plus the dates the checks work
out (a snooze ending, the closeout window opening), which the caller passes in.

- **Played up to now.** After any move to T, every scheduled event at or before T has been
  played (or skipped, for a file the user already brought in). So what a move plays is
  exactly the events after the old "now" and at or before the new one, in time order, and
  no list of played events has to be kept.
- **Forward only.** A move to a time before "now" is refused. "Next" moves to the first item
  after "now"; with nothing left, it's refused.
- **A ledger file's later lines.** A `ledger` event stores the whole file when it plays; a
  line whose posting date is still ahead arrives at 00:00 UTC on it (decision 0023). The
  clock releases those lines, so they're items on the timeline (in Coming up, and stops for
  "next") but not events a move plays.
- **Items the user brings in.** A file marked `deliver: "user"` waits for the user from
  its `available_at` (or the sample's opening) until its fallback time, when the clock
  delivers it unless the same file (the same sha256) is already on the grant.
- **One at a time (first version, the product owner's ruling).** A larger sample read live
  blocks opening or starting over another one while it's still reading its history: its
  clock is before its opening date, or agent runs for events dated before the opening are
  still queued or running. Once its history is read, it blocks nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.contracts.api import ArrivalSource

from .pack import EventKind, PackError, SamplePack, ScheduledEvent


class ItemKind(StrEnum):
    """The contract's TimelineEventKind."""

    ARRIVAL = "arrival"  # a file, the ledger file or a ledger line
    USER_DELIVERY = "user_delivery"  # an item the user is expected to bring in
    CHECKS_DATE = "checks_date"  # a date the checks work out


@dataclass(frozen=True)
class ChecksDate:
    """A date the checks work out, from the checks' `upcoming_dates`."""

    at: datetime
    name: str
    note: str | None = None


@dataclass(frozen=True)
class TimelineItem:
    """One item on the timeline, in the contract's TimelineEvent terms."""

    id: str
    at: datetime
    kind: ItemKind
    name: str  # the file name, the ledger line ID, or what the date is
    source: ArrivalSource | None = None
    note: str | None = None
    # The scheduled event a move plays. None for a ledger file's later line, which the
    # clock releases, and for a checks date.
    event: ScheduledEvent | None = None
    line_id: str | None = None  # for a ledger line


class MoveRefused(Exception):
    """A move the timeline refuses. The message says why, in plain words."""


@dataclass(frozen=True)
class Move:
    after: datetime | None  # the old "now"; None when the sample is being created
    until: datetime  # the new "now"
    play: tuple[ScheduledEvent, ...]  # the scheduled events to play, in order
    passed: tuple[TimelineItem, ...]  # every item the move passes: what just happened
    stopped_on: TimelineItem | None  # the item at the new "now", if there is one


_ORDER = {ItemKind.ARRIVAL: 0, ItemKind.USER_DELIVERY: 0, ItemKind.CHECKS_DATE: 1}


def _ledger_lines_later(pack: SamplePack, event: ScheduledEvent) -> list[TimelineItem]:
    """The lines of a ledger file arriving after the file itself, each at 00:00 UTC on its
    posting date, read the way an upload reads them."""
    from app.ingest.ledger import LedgerFileError, read_ledger_file

    try:
        read = read_ledger_file(
            pack.ledger_bytes(),
            workspace_id="sample",
            grant_id="sample",
            existing_line_ids=(),
            now=event.at,
        )
    except LedgerFileError as error:
        raise PackError(f"{pack.files_folder}: {error}") from error
    if read.rejected:
        rows = ", ".join(str(r.row) for r in read.rejected)
        raise PackError(f"{pack.files_folder}: rows {rows} of the ledger can't be read.")
    return [
        TimelineItem(
            id=f"{event.id}-{c.ledger_line_id}",
            at=c.arrived_at,
            kind=ItemKind.ARRIVAL,
            name=c.ledger_line_id,
            source=ArrivalSource.LEDGER,
            line_id=c.ledger_line_id,
        )
        for c in read.charges
        if c.arrived_at > event.at
    ]


def pack_items(pack: SamplePack) -> tuple[TimelineItem, ...]:
    """Every item the pack puts on the timeline, in time order: its scheduled events, and a
    ledger file's later lines."""
    items: list[TimelineItem] = []
    for e in pack.events:
        kind = ItemKind.USER_DELIVERY if e.deliver_by_user else ItemKind.ARRIVAL
        items.append(
            TimelineItem(
                id=e.id,
                at=e.at,
                kind=kind,
                name=e.name,
                source=e.source,
                note=e.note,
                event=e,
                line_id=e.name if e.kind is EventKind.LEDGER_LINE else None,
            )
        )
        if e.kind is EventKind.LEDGER:
            items += _ledger_lines_later(pack, e)
    return _sorted(items)


def checks_items(dates: Iterable[ChecksDate]) -> list[TimelineItem]:
    """The checks' dates as timeline items. An ID names the date and what it is, so the same
    date keeps its ID from one view to the next."""
    return [
        TimelineItem(
            id=f"checks-{d.at.strftime('%Y%m%dT%H%M%S')}-{n}",
            at=d.at,
            kind=ItemKind.CHECKS_DATE,
            name=d.name,
            note=d.note,
        )
        for n, d in enumerate(sorted(dates, key=lambda d: (d.at, d.name)), start=1)
    ]


def _sorted(items: Iterable[TimelineItem]) -> tuple[TimelineItem, ...]:
    # A stable sort: at the same moment, arrivals before checks dates, then the pack's order.
    return tuple(sorted(items, key=lambda i: (i.at, _ORDER[i.kind])))


def merge(
    pack_side: Sequence[TimelineItem], checks: Iterable[TimelineItem]
) -> tuple[TimelineItem, ...]:
    return _sorted([*pack_side, *checks])


def _between(
    items: Sequence[TimelineItem], after: datetime | None, until: datetime
) -> tuple[TimelineItem, ...]:
    return tuple(i for i in items if (after is None or i.at > after) and i.at <= until)


def _move(items: Sequence[TimelineItem], after: datetime | None, until: datetime) -> Move:
    passed = _between(items, after, until)
    return Move(
        after=after,
        until=until,
        play=tuple(i.event for i in passed if i.event is not None),
        passed=passed,
        stopped_on=next((i for i in passed if i.at == until), None),
    )


def plan_start(items: Sequence[TimelineItem], starts_at: datetime) -> Move:
    """Creating or starting over a sample: the clock is set to its start, and every event
    at or before it plays."""
    return _move(items, None, starts_at)


def plan_move(items: Sequence[TimelineItem], now: datetime, to: datetime | None) -> Move:
    """A move from `now`: to `to`, or with None, to the next item after `now`."""
    if to is None:
        upcoming = next((i for i in items if i.at > now), None)
        if upcoming is None:
            raise MoveRefused("Nothing is left on the timeline.")
        to = upcoming.at
    if to < now:
        raise MoveRefused("The timeline only moves forward.")
    return _move(items, now, to)


def skip_delivery(pack: SamplePack, event: ScheduledEvent, shas_on_grant: Iterable[str]) -> bool:
    """Whether the clock leaves out a file the user was to bring in: the same file (the same
    sha256) is already on the grant, so nothing is delivered twice."""
    return event.deliver_by_user and pack.sha256(event.name) in set(shas_on_grant)


def available_from(pack: SamplePack, event: ScheduledEvent) -> datetime:
    """When the user can first bring in an item: its `available_at`, else the opening."""
    return event.available_at or min(pack.opens_at, event.at)


@dataclass(frozen=True)
class Delivery:
    item: TimelineItem
    delivered_at: datetime | None  # when the same file reached the grant, if it has


def deliveries(
    pack: SamplePack,
    items: Sequence[TimelineItem],
    now: datetime,
    arrived_by_sha: Mapping[str, datetime],
) -> list[Delivery]:
    """The items waiting for the user at `now`: available, and not yet past the clock's
    fallback (at the fallback the clock delivers them). `arrived_by_sha` gives, for each
    sha256 on the grant, when that file first arrived."""
    out: list[Delivery] = []
    for i in items:
        e = i.event
        if i.kind is not ItemKind.USER_DELIVERY or e is None:
            continue
        if available_from(pack, e) <= now < e.at:
            out.append(Delivery(i, arrived_by_sha.get(pack.sha256(e.name))))
    return out


def coming_up(
    pack: SamplePack,
    items: Sequence[TimelineItem],
    now: datetime,
    shas_on_grant: Iterable[str],
) -> tuple[TimelineItem, ...]:
    """Every item after `now`, in date order, except a user delivery already brought in."""
    on_grant = set(shas_on_grant)
    return tuple(
        i
        for i in items
        if i.at > now and not (i.event is not None and skip_delivery(pack, i.event, on_grant))
    )


def finished(items: Sequence[TimelineItem], now: datetime) -> bool:
    """Nothing is left to arrive. Dates the checks work out don't count."""
    return not any(i.at > now and i.kind is not ItemKind.CHECKS_DATE for i in items)


def reading_history(
    now: datetime, opens_at: datetime, pending_run_times: Iterable[datetime]
) -> bool:
    """Whether a larger sample read live is still reading its history (first version of the
    product owner's ruling): its clock is before its opening date, or an agent run for an
    event dated before the opening is still queued or running. `pending_run_times` are the
    clock times of the grant's queued and running runs."""
    return now < opens_at or any(t < opens_at for t in pending_run_times)
