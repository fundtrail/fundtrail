"""The clock (decision 0023): the only place that says what time it is for a grant.

- `grant_now` answers "what time is it for this grant" for every caller. Nothing else
  in the app reads the stored clock or the system time for grant purposes, and only
  this module asks whether a clock is stored.
- Every rule asks the grant's clock for "now". A grant a user adds runs on the real time
  and its clock can't move. A sample grant's clock is stored (`grants.clock_now`), and
  moves forward only, to the next arrival or to a chosen time (issue 165).
- A jump is replayed in order. Each charge or file the clock passes gets its agent run as
  of its own arrival time, queued in arrival order, so the runs go one at a time in that
  order. Charges that arrive at the same moment share runs, in batches.
- Time alone can change a status, with no agent. The statuses are worked out again at
  each arrival and at each midnight the clock passes, so a change time caused is recorded
  on the day the rule was crossed. Each catch-up run's save works out its own moment and
  the midnights up to the next one, so a status never runs ahead of the agent's work. A
  grant on the real date gets the same once a day.
- The agent's review of a grant when its closeout window opens is a catch-up run too.
  It's queued once per end date in force: again when the end date moves, and on the next
  move, daily check or confirmation when the window was already open.
- A thread question asked while the agent catches up waits for the catch-up.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from app.contracts.checks import ChecksOutput
from app.contracts.evidence import Source
from app.contracts.rules import RecordState
from app.contracts.runs import AgentRun, Trigger, TriggerKind, charge_batches
from app.contracts.workspaces import Grant

from . import jobs, store, terms
from .pings import ping_changed, ping_run
from .platform import Platform
from .pool import transaction
from .recheck import recheck_grant
from .store import Conn

log = logging.getLogger(__name__)

_SOURCE_NAMES = {Source.GMAIL: "gmail", Source.DRIVE: "drive", Source.UPLOAD: "upload"}


class ClockError(Exception):
    """A move the clock refuses. The message says why, in plain words."""


@dataclass(frozen=True)
class Arrival:
    at: datetime
    source: str  # ledger, gmail, drive or upload (contracts.api.ArrivalSource)
    name: str  # the file name, or the ledger line ID
    grant_id: str


def _database_now(conn: Conn) -> datetime:
    """The database's time for this transaction: when it started, the same all through it."""
    row = conn.execute("select now() as now").fetchone()
    assert row is not None
    return row["now"]


def _stored_clock(conn: Conn, grant_id: str) -> datetime | None:
    """The grant's stored clock, if it has one: a sample grant's simulated "now"."""
    row = conn.execute("select clock_now from public.grants where id = %s", (grant_id,)).fetchone()
    assert row is not None
    return row["clock_now"]


def grant_now(conn: Conn, grant_id: str) -> datetime:
    """What time it is for this grant: its stored clock, which moves only when told, or
    else the database's time for this transaction (so a run's read point and its clock
    agree, call 40)."""
    return _stored_clock(conn, grant_id) or _database_now(conn)


def has_stored_clock(conn: Conn, grant_id: str) -> bool:
    """Whether the grant runs on a stored clock (a sample grant), not the real date: the one
    place that asks. It reads grants.clock_now, through _stored_clock."""
    return _stored_clock(conn, grant_id) is not None


def grant_clock(p: Platform) -> Callable[[str], datetime]:
    """`grant_now` as the ingest checker takes it (its `GrantNow`): each call reads the
    grant's clock in a transaction of its own."""

    def now(grant_id: str) -> datetime:
        with transaction(p.pool) as conn:
            return grant_now(conn, grant_id)

    return now


def read_now(conn: Conn, run: AgentRun) -> datetime:
    """The time a run's read works as of. On a stored clock, the time the run started at,
    so a move during the run doesn't shift what it reads (the move's arrivals get catch-up
    runs of their own). On real time, the read's own moment, so everything the run is
    given, records written since it started included, counts as read by it."""
    if _stored_clock(conn, run.grant_id) is not None:
        return run.clock_now
    return _database_now(conn)


def next_arrival(conn: Conn, grant_id: str) -> Arrival | None:
    """The first charge or file stored on the grant and still waiting for its clock. A
    grant on the real date has none."""
    now = _stored_clock(conn, grant_id)
    if now is None:
        return None
    found = [
        Arrival(c.arrived_at, "ledger", c.ledger_line_id, grant_id)
        for c in store.list_charges(conn, grant_id, store.END_OF_TIME)
        if c.arrived_at > now
    ]
    found += [
        Arrival(f.arrived_at, _SOURCE_NAMES[f.source], f.name, grant_id)
        for f in store.list_files(conn, grant_id, store.END_OF_TIME)
        if f.arrived_at > now
    ]
    return min(found, key=lambda a: (a.at, a.source, a.name), default=None)


def _midnights(after: datetime, until: datetime) -> list[datetime]:
    """Each midnight UTC in (after, until]."""
    day = after.date() + timedelta(days=1)
    out: list[datetime] = []
    while (at := datetime.combine(day, time(), tzinfo=UTC)) <= until:
        out.append(at)
        day += timedelta(days=1)
    return out


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=UTC)


def review_due(conn: Conn, grant: Grant, at: datetime) -> datetime | None:
    """When the grant's closeout window opened, if it has by `at` and no review has run for
    the end date in force: a review counts only if it works as of the window's opening or
    later, so a moved end date gets a review of its own."""
    state = RecordState(store.list_records(conn, grant.id, at))
    opens = terms.closeout_window_opens(terms.end_date(state, grant.id))
    if opens is None:
        return None
    window = _midnight(opens)
    if window > at or store.has_review_since(conn, grant.id, window):
        return None
    return window


def queue_review_if_due(conn: Conn, grant: Grant, now: datetime) -> AgentRun | None:
    """Queue the closeout review now if the window is open and it hasn't run for this end
    date: after the accountant confirms dates already inside the window, after the end date
    in force moves, or when a daily check was missed."""
    if review_due(conn, grant, now) is None:
        return None
    return jobs.queue_run(conn, grant, Trigger(kind=TriggerKind.CLOCK), now)


@dataclass(frozen=True)
class _CatchUp:
    at: datetime
    order: int  # at the same moment: the review, then files, then charge batches
    trigger: Trigger


def replay(
    p: Platform, conn: Conn, grant: Grant, after: datetime, until: datetime
) -> list[AgentRun]:
    """What happens on a grant when the clock moves from `after` to `until`.

    Each file and each batch of charges the clock passes, and the closeout review if its
    window is due, gets a catch-up run as of its own time, queued in time order. Time
    alone is worked out here only up to the first of them; from there, each catch-up run's
    save works out its own moment and the midnights up to the next one, so every status
    reflects the runs done by then, as stepping one arrival at a time would.
    """
    charges = [c for c in store.list_charges(conn, grant.id, until) if c.arrived_at > after]
    files = [f for f in store.list_files(conn, grant.id, until) if f.arrived_at > after]
    items = [_CatchUp(f.arrived_at, 1, Trigger(kind=TriggerKind.FILE, id=f.id)) for f in files]
    items += [
        _CatchUp(batch[0].arrived_at, 2, Trigger(kind=TriggerKind.CHARGE, id=batch[0].id))
        for batch in charge_batches(charges)
    ]
    window = review_due(conn, grant, until)
    if window is not None:
        items.append(_CatchUp(max(window, after), 0, Trigger(kind=TriggerKind.CLOCK)))
    items.sort(key=lambda i: (i.at, i.order, i.trigger.id or ""))

    # Stop at the first catch-up run on the grant, this move's or one an earlier move left
    # waiting: from there, the runs' saves step time on, so no status runs ahead of them.
    pending = store.next_catch_up_time(conn, grant.id, "")
    first = min(
        (t for t in (items[0].at if items else None, pending) if t is not None), default=None
    )
    points = [m for m in _midnights(after, until) if first is None or m < first]
    if first is None and until not in points:
        points.append(until)
    _step_through(p, conn, grant, points, first)
    return [jobs.queue_run(conn, grant, i.trigger, i.at, catch_up=True) for i in items]


def _scripted_due(p: Platform, conn: Conn, grant: Grant, before: datetime | None) -> list[Any]:
    """A sample grant's scripted decisions waiting to be made before `before` (all with
    None), from the skip in app.samples (ruling 47). Any other grant has none."""
    if grant.sample is None:
        return []
    from app.samples.skipping import due

    return list(due(p, conn, grant, before))


def _step_through(
    p: Platform, conn: Conn, grant: Grant, points: list[datetime], before: datetime | None
) -> None:
    """Work time out at each point, and make each scripted decision due before `before`
    at its own time among them: a decision first when they share a moment."""
    clock = Trigger(kind=TriggerKind.CLOCK)
    steps: list[tuple[datetime, int, Any]] = [(at, 1, None) for at in points]
    steps += [(d.at, 0, d) for d in _scripted_due(p, conn, grant, before)]
    for at, _, decision in sorted(steps, key=lambda s: (s[0], s[1])):
        if decision is None:
            recheck_grant(conn, p.checks, grant, at, clock)
        else:
            decision.make()


def make_due_scripted(p: Platform, conn: Conn, grant: Grant, run_id: str) -> None:
    """After an ordinary run saves or fails: a sample's scripted decision that waited for
    every run to finish (a sign-off) may be made now, before the next catch-up run."""
    _step_through(p, conn, grant, [], store.next_catch_up_time(conn, grant.id, run_id))


def set_stored_clock(conn: Conn, grant_id: str, at: datetime) -> None:
    """Set a grant's stored clock, here and nowhere else in the app: a scripted step on a
    sample grant is written at its own time and the clock set back after."""
    store.set_grant_clock(conn, grant_id, at)


def step_after_catch_up(p: Platform, conn: Conn, grant: Grant, run: AgentRun) -> ChecksOutput:
    """After a catch-up run saves or fails: work out the statuses at its own time, with
    what arrived then triggered by itself, then at each midnight up to the next catch-up
    run, or up to the grant's "now" when it's the last. Returns the output at its time."""
    at = run.clock_now
    charge_triggers = {
        c.id: Trigger(kind=TriggerKind.CHARGE, id=c.id)
        for c in store.list_charges(conn, grant.id, at)
        if c.arrived_at == at
    }
    file_triggers = {
        f.id: Trigger(kind=TriggerKind.FILE, id=f.id)
        for f in store.list_files(conn, grant.id, at)
        if f.arrived_at == at
    }
    output = recheck_grant(
        conn,
        p.checks,
        grant,
        at,
        run.trigger,
        charge_triggers=charge_triggers,
        file_triggers=file_triggers,
    )
    following = store.next_catch_up_time(conn, grant.id, run.id)
    end = following or grant_now(conn, grant.id)
    points = [m for m in _midnights(at, end) if following is None or m < following]
    if following is None and end > at and end not in points:
        points.append(end)
    _step_through(p, conn, grant, points, following)
    return output


def set_and_replay(
    p: Platform, conn: Conn, grant: Grant, old: datetime | None, to: datetime
) -> list[AgentRun]:
    """Set the grant's stored clock to `to` and replay what that passes, in the caller's
    transaction, which holds the grant's lock and has checked the move goes forward. With
    `old` None (a sample just opened or started over), what's stored at `to` itself is
    replayed: everything that arrived at the clock's first "now". The caller pings."""
    store.set_grant_clock(conn, grant.id, to)
    after = old if old is not None else to - timedelta(microseconds=1)
    return replay(p, conn, grant, after, to) if to > after else []


def move_grant_clock(p: Platform, grant_id: str, to: datetime | None) -> datetime:
    """Move a grant's stored clock forward: to `to`, or with None, to the next charge or
    file stored on it and waiting. Everything the move passes is replayed in order. Returns
    the grant's new "now"."""
    with transaction(p.pool) as conn:
        grant = store.get_grant(conn, grant_id, lock=True)
        if grant is None:
            raise ClockError("There's no such grant.")
        old = _stored_clock(conn, grant_id)
        if old is None:
            raise ClockError("This grant runs on the real date, so its clock can't move.")
        if to is None:
            arrival = next_arrival(conn, grant_id)
            if arrival is None:
                raise ClockError("Nothing is waiting to arrive.")
            to = arrival.at
        if to < old:
            raise ClockError("The clock only moves forward.")
        runs = set_and_replay(p, conn, grant, old, to)
    for run in runs:
        ping_run(p.pinger, run)
    ping_changed(p.pinger, grant.workspace_id, grant.id, "charges", "evidence", "statuses")
    return to


def daily_recheck(p: Platform) -> None:
    """Once a day, each grant at its own "now": work the statuses out again for time alone,
    and queue the closeout review if its window is open and it hasn't run for this end date
    (so a missed day doesn't lose it). A grant whose agent is catching up is left to its
    catch-up runs, whose saves step time on, so no status runs ahead of them. On a clock
    that hasn't moved, nothing has changed, so nothing is written.

    One grant's failure, or a grant removed since the list was read, doesn't stop the
    others: it's logged, and tomorrow's check tries it again.
    """
    with transaction(p.pool) as conn:
        grants = store.all_grants(conn)
    for grant in grants:
        try:
            with transaction(p.pool) as conn:
                if store.get_grant(conn, grant.id, lock=True) is None:
                    continue  # removed since the list was read, such as a workspace reset
                if jobs.grant_catching_up(conn, grant.id):
                    continue
                now = grant_now(conn, grant.id)
                recheck_grant(conn, p.checks, grant, now, Trigger(kind=TriggerKind.CLOCK))
                review = queue_review_if_due(conn, grant, now)
        except Exception:  # noqa: BLE001 - one grant's failure mustn't stop the others
            log.exception("daily recheck of grant %s failed; tried again tomorrow", grant.id)
            continue
        if review is not None:
            ping_run(p.pinger, review)
        ping_changed(p.pinger, grant.workspace_id, grant.id, "statuses")
