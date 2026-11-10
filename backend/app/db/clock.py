"""The workspace clock (decision 0023).

- Every rule asks the workspace for "now". A workspace a user creates runs on the real
  time and its clock can't move; the demo workspace's clock is simulated and moves
  forward only, to the next arrival or to a chosen time.
- A jump is replayed in order. Each charge or file the clock passes gets its agent run as
  of its own arrival time, queued in arrival order, so the runs go one at a time in that
  order. Charges that arrive at the same moment share runs, in batches.
- Time alone can change a status, with no agent. The statuses are worked out again at
  each arrival and at each midnight the clock passes, so a change time caused is recorded
  on the day the rule was crossed. A real workspace gets the same once a day.
- The agent's review of a grant when its closeout window opens is queued the same way,
  once per grant.
- A thread question asked while the agent catches up waits for the catch-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from app.contracts.evidence import Source
from app.contracts.rules import RecordState
from app.contracts.runs import AgentRun, Trigger, TriggerKind
from app.contracts.workspaces import Grant, Workspace

from . import store, terms
from .jobs import charge_batches, grant_catching_up, queue_run
from .pings import ping_changed, ping_run
from .platform import Platform
from .pool import transaction, workspace_now
from .recheck import recheck_grant
from .store import Conn

_SOURCE_NAMES = {Source.GMAIL: "email", Source.DRIVE: "drive", Source.UPLOAD: "upload"}


class ClockError(Exception):
    """A move the clock refuses. The message says why, in plain words."""


@dataclass(frozen=True)
class Arrival:
    at: datetime
    source: str  # ledger, email, drive or upload
    name: str  # the file name, or the ledger line ID
    grant_id: str


@dataclass(frozen=True)
class ClockState:
    now: datetime
    simulated: bool
    next_arrival: Arrival | None
    catching_up: bool


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
    return any(grant_catching_up(conn, g.id) for g in store.list_grants(conn, workspace.id))


def clock_state(conn: Conn, workspace: Workspace) -> ClockState:
    return ClockState(
        now=workspace_now(workspace),
        simulated=workspace.clock_now is not None,
        next_arrival=next_arrival(conn, workspace),
        catching_up=catching_up(conn, workspace),
    )


def _midnights(after: datetime, until: datetime) -> list[datetime]:
    day = after.date() + timedelta(days=1)
    out: list[datetime] = []
    while (at := datetime.combine(day, time(), tzinfo=UTC)) <= until:
        out.append(at)
        day += timedelta(days=1)
    return out


def _closeout_review(
    conn: Conn, grant: Grant, after: datetime, until: datetime, *, catch_up: bool = False
) -> AgentRun | None:
    """Queue the grant's closeout review if its window opened in (after, until]."""
    if store.has_clock_run(conn, grant.id):
        return None
    state = RecordState(store.list_records(conn, grant.id, until))
    opens = terms.closeout_window_opens(terms.end_date(state, grant.id))
    if opens is None:
        return None
    at = datetime.combine(opens, time(), tzinfo=UTC)
    if not after < at <= until:
        return None
    return queue_run(conn, grant, Trigger(kind=TriggerKind.CLOCK), at, catch_up=catch_up)


def replay(
    p: Platform, conn: Conn, grant: Grant, after: datetime, until: datetime
) -> list[AgentRun]:
    """Everything that happens on a grant when time moves from `after` to `until`: arrivals
    get their runs in order, and the statuses are worked out again at each arrival and each
    midnight, with the arriving item or the clock as the trigger."""
    charges = [c for c in store.list_charges(conn, grant.id, until) if c.arrived_at > after]
    files = [f for f in store.list_files(conn, grant.id, until) if f.arrived_at > after]
    points = sorted(
        {c.arrived_at for c in charges}
        | {f.arrived_at for f in files}
        | set(_midnights(after, until))
        | {until}
    )
    runs: list[AgentRun] = []
    clock = Trigger(kind=TriggerKind.CLOCK)
    batches = charge_batches(charges)
    for at in points:
        arriving_charges = [c for c in charges if c.arrived_at == at]
        arriving_files = [f for f in files if f.arrived_at == at]
        charge_triggers = {
            c.id: Trigger(kind=TriggerKind.CHARGE, id=c.id) for c in arriving_charges
        }
        file_triggers = {f.id: Trigger(kind=TriggerKind.FILE, id=f.id) for f in arriving_files}
        first = next(iter([*charge_triggers.values(), *file_triggers.values()]), clock)
        recheck_grant(
            conn,
            p.checks,
            grant,
            at,
            first,
            charge_triggers=charge_triggers,
            file_triggers=file_triggers,
        )
        for f in sorted(arriving_files, key=lambda f: (f.arrived_at, f.id)):
            runs.append(queue_run(conn, grant, file_triggers[f.id], at, catch_up=True))
        for batch in batches:
            if batch[0].arrived_at == at:
                runs.append(queue_run(conn, grant, charge_triggers[batch[0].id], at, catch_up=True))
        review = _closeout_review(conn, grant, after, at, catch_up=True)
        if review is not None:
            runs.append(review)
        after = max(after, at)
    return runs


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
        runs = [r for g in grants for r in replay(p, conn, g, old, to)] if to > old else []
        state = clock_state(conn, workspace.model_copy(update={"clock_now": to}))
    for run in runs:
        ping_run(p.pinger, run)
    for g in grants:
        ping_changed(p.pinger, workspace.id, g.id, "charges", "evidence", "statuses")
    return state


def daily_recheck(p: Platform) -> None:
    """Once a day in each real-time workspace: work the statuses out again for time alone,
    and queue any closeout review whose window opened since yesterday."""
    now = datetime.now(UTC)
    with transaction(p.pool) as conn:
        workspace_ids = store.real_time_workspace_ids(conn)
    for workspace_id in workspace_ids:
        with transaction(p.pool) as conn:
            grants = store.list_grants(conn, workspace_id)
            runs: list[AgentRun] = []
            for grant in grants:
                store.get_grant(conn, grant.id, lock=True)
                recheck_grant(conn, p.checks, grant, now, Trigger(kind=TriggerKind.CLOCK))
                review = _closeout_review(conn, grant, now - timedelta(days=1), now)
                if review is not None:
                    runs.append(review)
        for run in runs:
            ping_run(p.pinger, run)
        for grant in grants:
            ping_changed(p.pinger, workspace_id, grant.id, "statuses")
