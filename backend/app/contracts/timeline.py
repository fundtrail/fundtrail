"""A sample grant's timeline (issue 165): what has happened, what's now, what's coming up.

A sample grant has its own simulated "now" (Grant.clock_now). The timeline plays
its events forward: files and ledger lines arriving, items the user is expected to
bring in, and dates the checks work out. Every timeline route is 404 on a grant
that isn't a sample.

- GET  /grants/{grant_id}/timeline: TimelineView.
- POST /grants/{grant_id}/timeline: TimelineMove; returns TimelineView. The
  read-live limit can refuse it with a 409 whose `detail` is api.SampleRefusal (see
  TimelineMove).
- POST /grants/{grant_id}/timeline/start-over: TimelineStartOver; resets that one
  grant; returns TimelineView. The read-live limit never refuses it.
- POST /grants/{grant_id}/timeline/deliveries/{event_id}: "Deliver for me"; brings
  the item in as if the user had; returns TimelineView.
- GET  /grants/{grant_id}/timeline/deliveries/{event_id}/file: "Get the file"; a
  short-lived link (api.FileLink), like an evidence file's.
"""

from enum import StrEnum

from .api import ArrivalSource
from .base import Id, Model, Text, UtcDatetime
from .records import Record


class TimelineEventKind(StrEnum):
    ARRIVAL = "arrival"  # a file, the ledger file or a ledger line arrives
    USER_DELIVERY = "user_delivery"  # an item the user is expected to bring in
    CHECKS_DATE = "checks_date"  # a date the checks work out: a snooze ending, the closeout window


class TimelineEvent(Model):
    id: Id
    at: UtcDatetime
    kind: TimelineEventKind
    source: ArrivalSource | None = None  # for an arrival or a delivery: where it comes from
    name: Text  # the file name, the ledger line ID, or what the date is
    note: str | None = None
    charge_id: Id | None = None  # once played: the charge a ledger line became
    file_id: Id | None = None  # once played or on file: the evidence file


class PlayedEvent(Model):
    """An event the last move played, with what the agent wrote from it so far."""

    event: TimelineEvent
    agent_records: tuple[Record, ...] = ()
    charge_ids: tuple[Id, ...] = ()
    # Ruling 47, a first version: the decisions the workspace's sample accountant made
    # in that move, from the sample's accountant script, when the move skipped the
    # human steps. The panel lists them so the user sees who decided what.
    scripted_decisions: tuple[Record, ...] = ()
    # Ruling 47: the result was loaded from the prerun, not worked live. Only on the
    # prerun choice, while the grant is on the run-through; the panel marks it so
    # nothing loaded passes for live work (decision 0007).
    loaded: bool = False


class UserDelivery(Model):
    """An item the user is expected to bring in."""

    event: TimelineEvent
    delivered: bool
    delivered_at: UtcDatetime | None = None


class TimelineNow(Model):
    now: UtcDatetime
    stopped_on: TimelineEvent | None = None  # the event the last move stopped on
    # Undelivered items whose date has come and that are still available.
    deliveries: tuple[UserDelivery, ...] = ()
    waiting_on_problem_list: int  # rows waiting on the grant's problem list


class TimelineView(Model):
    """GET /grants/{grant_id}/timeline, and what every timeline move returns."""

    just_happened: tuple[PlayedEvent, ...] = ()  # the events the last move played
    now: TimelineNow
    coming_up: tuple[TimelineEvent, ...] = ()  # in date order
    finished: bool  # nothing is left to play
    catching_up: bool  # the agent is still working through what was played
    # Ruling 47: for the prerun choice only, whether the grant is still on the
    # run-through, so saved results still apply: every accountant decision on it is
    # the sample accountant's scripted one, and none whose time has passed is
    # missing. A user's decision or a missed scripted one takes it off for good.
    # None on a sample the agent reads live.
    on_run_through: bool | None = None


class TimelineMove(Model):
    """POST /grants/{grant_id}/timeline. None in `to` moves to the next event.

    Forward only: a time before the grant's now is a 409.

    The read-live limit (ruling 48, a first version): while one of the user's larger
    read-live samples has agent runs queued or running from a move of its clock,
    moving the clock of another is refused with a 409 whose `detail` is an
    api.SampleRefusal with reason `another_sample_working`, naming the one still
    working.
    """

    to: UtcDatetime | None = None
    # Ruling 47, a first version: on "Next event" and "Go to a date" alike. As the
    # clock passes each scripted accountant action's time, the workspace's sample
    # accountant performs it through the ordinary write paths, as its author. A
    # scripted action whose target isn't there is left for the user.
    skip_human_steps: bool = False


class TimelineStartOver(Model):
    """POST /grants/{grant_id}/timeline/start-over: resets that one grant.

    With `confirmed` false it's refused: a 409 whose `detail` is an api.SampleRefusal
    with reason `needs_confirm`. The read-live limit never refuses it: that limit is
    on moving the clock (TimelineMove).
    """

    confirmed: bool
