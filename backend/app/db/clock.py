"""The clock (decision 0023): the only place that says what time it is for a grant.

- `grant_now` answers "what time is it for this grant" for every caller. Nothing else
  in the app reads the stored clock or the system time for grant purposes, and only
  this module asks whether a clock is stored.
- Every rule asks the grant's clock for "now". A workspace a user creates runs on the real
  time and its clock can't move; the demo workspace's clock is simulated and moves
  forward only, to the next arrival or to a chosen time.
- A jump is replayed in order. Each charge or file the clock passes gets its agent run as
  of its own arrival time, queued in arrival order, so the runs go one at a time in that
  order. Charges that arrive at the same moment share runs, in batches.
- Time alone can change a status, with no agent. The statuses are worked out again at
  each arrival and at each midnight the clock passes, so a change time caused is recorded
  on the day the rule was crossed. Each catch-up run's save works out its own moment and
  the midnights up to the next one, so a status never runs ahead of the agent's work. A
  real workspace gets the same once a day.
- The agent's review of a grant when its closeout window opens is a catch-up run too.
  It's queued once per end date in force: again when the end date moves, and on the next
  move, daily check or confirmation when the window was already open.
- A thread question asked while the agent catches up waits for the catch-up.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from app.contracts.checks import ChecksOutput
from app.contracts.evidence import Source
from app.contracts.rules import RecordState
from app.contracts.runs import AgentRun, Trigger, TriggerKind, charge_batches
from app.contracts.workspaces import Grant, Workspace

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


@dataclass(frozen=True)
class ClockState:
    now: datetime
    simulated: bool
    next_arrival: Arrival | None
    catching_up: bool


def _database_now(conn: Conn) -> datetime:
    """The database's time for this transaction: when it started, the same all through it."""
    row = conn.execute("select now() as now").fetchone()
    assert row is not None
    return row["now"]


def _stored_clock(conn: Conn, grant_id: str) -> datetime | None:
    """The grant's stored clock, if it has one. It's the workspace's until the per-grant
    clock lands with the sample-grant design; then only this function changes."""
    row = conn.execute(
        """select w.clock_now from public.grants g
           join public.workspaces w on w.id = g.workspace_id where g.id = %s""",
        (grant_id,),
    ).fetchone()
    assert row is not None
    return row["clock_now"]


def grant_now(conn: Conn, grant_id: str) -> datetime:
    """What time it is for this grant: its stored clock, which moves only when told, or
    else the database's time for this transaction (so a run's read point and its clock
    agree, call 40)."""
    return _stored_clock(conn, grant_id) or _database_now(conn)


def read_now(conn: Conn, run: AgentRun) -> datetime:
    """The time a run's read works as of. On a stored clock, the time the run started at,
    so a move during the run doesn't shift what it reads (the move's arrivals get catch-up
    runs of their own). On real time, the read's own moment, so everything the run is
    given, records written since it started included, counts as read by it."""
    if _stored_clock(conn, run.grant_id) is not None:
        return run.clock_now
    return _database_now(conn)


def next_arrival(conn: Conn, workspace: Workspace) -> Arrival | None:
    """The first charge or file waiting for the clock. A real workspace has none."""
    if workspace.clock_now is None:
        return None
    now = workspace.clock_now
    found: list[Arrival] = []
    for grant in store.list_grants(conn, workspace.id):
        for c in store.list_charges(conn, grant.id, store.END_OF_TIME):
            if c.arrived_at > now:
                found.append(Arrival(c.arrived_at, "ledger", c.ledger_line_id, grant.id))
        for f in store.list_files(conn, grant.id, store.END_OF_TIME):
            if f.arrived_at > now:
                found.append(Arrival(f.arrived_at, _SOURCE_NAMES[f.source], f.name, grant.id))
    return min(found, key=lambda a: (a.at, a.source, a.name), default=None)


def catching_up(conn: Conn, workspace: Workspace) -> bool:
    """Whether the agent is still working through arrivals the clock passed, on any grant."""
    return any(jobs.grant_catching_up(conn, g.id) for g in store.list_grants(conn, workspace.id))


def clock_state(conn: Conn, workspace: Workspace) -> ClockState:
    return ClockState(
        now=workspace.clock_now or _database_now(conn),
        simulated=workspace.clock_now is not None,
        next_arrival=next_arrival(conn, workspace),
        catching_up=catching_up(conn, workspace),
    )


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
    clock = Trigger(kind=TriggerKind.CLOCK)
    points = [m for m in _midnights(after, until) if first is None or m < first]
    if first is None and until not in points:
        points.append(until)
    for at in points:
        recheck_grant(conn, p.checks, grant, at, clock)
    return [jobs.queue_run(conn, grant, i.trigger, i.at, catch_up=True) for i in items]


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
    clock = Trigger(kind=TriggerKind.CLOCK)
    points = [m for m in _midnights(at, end) if following is None or m < following]
    if following is None and end > at and end not in points:
        points.append(end)
    for point in points:
        recheck_grant(conn, p.checks, grant, point, clock)
    return output


def move_clock(p: Platform, workspace_id: str, to: datetime | None) -> ClockState:
    """Move the demo workspace's clock forward: to `to`, or to the next arrival."""
    with transaction(p.pool) as conn:
        workspace = store.lock_workspace(conn, workspace_id)
        if workspace.clock_now is None:
            raise ClockError("This workspace runs on the real date, so its clock can't move.")
        old = workspace.clock_now
        if to is None:
            arrival = next_arrival(conn, workspace)
            if arrival is None:
                raise ClockError("Nothing is waiting to arrive.")
            to = arrival.at
        if to < old:
            raise ClockError("The clock only moves forward.")
        store.set_clock(conn, workspace.id, to)
        grants = store.list_grants(conn, workspace.id)
        runs: list[AgentRun] = []
        if to > old:
            for g in grants:
                store.get_grant(conn, g.id, lock=True)
                runs += replay(p, conn, g, old, to)
        state = clock_state(conn, workspace.model_copy(update={"clock_now": to}))
    for run in runs:
        ping_run(p.pinger, run)
    for g in grants:
        ping_changed(p.pinger, workspace.id, g.id, "charges", "evidence", "statuses")
    return state


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
