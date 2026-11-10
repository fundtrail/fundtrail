"""The timeline player's pure logic: no database, no clock of its own.

A sample grant's timeline is its pack's scheduled events, plus the dates the checks work
out (a snooze ending, the closeout window opening), which the caller passes in.

- **Played up to now.** After any move to T, every scheduled event at or before T has been
  played. So what a move plays is exactly the events after the old "now" and at or before
  the new one, in time order, and no list of played events has to be kept.
- **Forward only.** A move to a time before "now" is refused. "Next" moves to the first item
  after "now"; with nothing left, it's refused.
- **A ledger file's later lines.** A `ledger` event stores the whole file when it plays; a
  line whose posting date is still ahead arrives at 00:00 UTC on it (decision 0023). The
  clock releases those lines, so they're items on the timeline (in Coming up, and stops for
  "next") but not events a move plays.
- **Items the user brings in (ruling 44).** A file marked `deliver: "user"` has a date, its
  `at`. The clock stops on it once, like any event, but never delivers it: from its date it
  waits for the user, whatever moves come after, until it's delivered. It counts as
  delivered once a file with the same sha256 arrives by any channel (an upload, Drive, or an
  email's attachment), or, for an email file, once an email with the same Message-ID does.
- **The read-live limit (ruling 48, first version).** It's on a move of the clock only:
  while one of the user's larger read-live samples still has agent runs queued or running
  from a move of its clock, moving another one's clock is refused, naming it. Opening and
  starting over are never refused for it. `still_reading` is the one place that says when.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.contracts.api import ArrivalSource

from .pack import EventKind, PackError, SamplePack, ScheduledEvent, event_id


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
    # What the date belongs to, such as a snooze or a charge, so two dates of the same kind
    # on the same day stay apart. Part of the ID; not shown.
    key: str = ""


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
            id=event_id(EventKind.LEDGER_LINE, c.ledger_line_id),
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


def _checks_id(d: ChecksDate) -> str:
    utc = d.at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(f"{d.name}/{d.key}".encode()).hexdigest()[:8]
    return f"checks-{utc}-{digest}"


def checks_items(dates: Iterable[ChecksDate]) -> list[TimelineItem]:
    """The checks' dates as timeline items. An ID names the date, in UTC, and what it is,
    never its place in the list, so the same date keeps its ID from one view to the next.
    The same date given twice is one item."""
    items: dict[str, TimelineItem] = {}
    for d in sorted(dates, key=lambda d: (d.at, d.name)):
        item_id = _checks_id(d)
        if item_id not in items:
            items[item_id] = TimelineItem(
                id=item_id, at=d.at, kind=ItemKind.CHECKS_DATE, name=d.name, note=d.note
            )
    return list(items.values())


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
        # A user's item is a stop, but the clock never delivers it.
        play=tuple(i.event for i in passed if i.event is not None and not i.event.deliver_by_user),
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


@dataclass(frozen=True)
class OnGrant:
    """What has arrived on the grant, to tell when a user's item counts as delivered."""

    # For each sha256 on the grant, when a file with it first arrived. An email's
    # attachments are files of their own, so they're here too.
    by_sha: Mapping[str, datetime] = field(default_factory=dict[str, datetime])
    # For each arrived email's Message-ID (without its angle brackets), when it first arrived.
    by_message_id: Mapping[str, datetime] = field(default_factory=dict[str, datetime])


def delivered_at(pack: SamplePack, event: ScheduledEvent, on_grant: OnGrant) -> datetime | None:
    """When the user's item was delivered, if it has been: the first arrival of a file with
    the same sha256, or, for an email file, of an email with the same Message-ID."""
    found = [on_grant.by_sha.get(pack.sha256(event.name))]
    message_id = pack.message_id(event.name)
    if message_id is not None:
        found.append(on_grant.by_message_id.get(message_id))
    return min((t for t in found if t is not None), default=None)


def deliveries(
    pack: SamplePack, items: Sequence[TimelineItem], now: datetime, on_grant: OnGrant
) -> list[TimelineItem]:
    """The items waiting for the user at `now`: their date has come, and they haven't been
    delivered. They stay until they are."""
    return [
        i
        for i in items
        if i.kind is ItemKind.USER_DELIVERY
        and i.event is not None
        and i.at <= now
        and delivered_at(pack, i.event, on_grant) is None
    ]


def coming_up(
    pack: SamplePack, items: Sequence[TimelineItem], now: datetime, on_grant: OnGrant
) -> tuple[TimelineItem, ...]:
    """Every item after `now`, in date order, except a user's item already delivered."""
    return tuple(
        i
        for i in items
        if i.at > now
        and not (
            i.kind is ItemKind.USER_DELIVERY
            and i.event is not None
            and delivered_at(pack, i.event, on_grant) is not None
        )
    )


def finished(items: Sequence[TimelineItem], now: datetime) -> bool:
    """Nothing is left for the clock: no arrival and no user's item still to come. Dates the
    checks work out don't count, and neither does an item still waiting for the user."""
    return not any(i.at > now and i.kind is not ItemKind.CHECKS_DATE for i in items)


def still_reading(catch_up_runs_pending: int) -> bool:
    """The read-live limit (ruling 48, first version): whether a larger read-live sample
    holds a move of another one's clock, because agent runs from a move of its own clock
    (its catch-up runs) are still queued or running. Only a move is held: never opening
    or starting over."""
    return catch_up_runs_pending > 0
