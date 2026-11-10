"""Agent runs as Procrastinate jobs.

- One `agent_runs` row per run, and one Procrastinate job at a time per run. The job's
  arguments carry the run's ID, the try number and the priority.
- The job's lock is `grant:{grant_id}`, so runs for one grant go one at a time.
- A run started by a thread message gets a higher priority, so it goes ahead of the
  grant's queued runs and waits only for the run in progress.
- The job is deferred inside the same transaction that inserts the run row, so a run is
  never queued without its job or the other way round.
- A run is saved all or nothing: the agent returns everything it wrote, and one
  transaction checks each record again against the database and saves it all, or
  nothing. Then the checks rerun and status rows are written with the run's trigger.
- A run that fails is tried again `run_retries` times; after the last try it's marked
  failed, and the checks rerun with it in `failed_runs`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import procrastinate
from psycopg.types.json import Jsonb

from app.contracts.charges import Charge
from app.contracts.checks import OpenQuestion
from app.contracts.records import Author
from app.contracts.rules import check_new_record
from app.contracts.runs import AgentRun, RunStatus, Trigger, TriggerKind
from app.contracts.workspaces import Grant

from . import store
from .pings import ping_changed, ping_run
from .platform import Platform, get_platform
from .pool import transaction, workspace_now
from .ports import AgentInput, AgentResult
from .recheck import recheck_grant
from .store import Conn

log = logging.getLogger(__name__)

QUEUE = "agent"
TASK_NAME = "run_agent"
NORMAL_PRIORITY = 0
THREAD_PRIORITY = 10  # a question in a thread goes ahead of queued runs


# A run triggered by a charge covers every charge on its grant that arrived at the same
# moment, in batches of at most this many, each batch its own run.
CHARGE_BATCH = 25


def charge_batches(charges: Sequence[Charge]) -> list[list[Charge]]:
    """Charges grouped by arrival moment, each group in ledger line ID order and cut into
    batches of CHARGE_BATCH. A batch's run is triggered by its first charge."""
    groups: dict[datetime, list[Charge]] = {}
    for c in charges:
        groups.setdefault(c.arrived_at, []).append(c)
    batches: list[list[Charge]] = []
    for at in sorted(groups):
        group = sorted(groups[at], key=lambda c: c.ledger_line_id)
        batches += [group[i : i + CHARGE_BATCH] for i in range(0, len(group), CHARGE_BATCH)]
    return batches


def batch_for(trigger_charge_id: str, charges: Sequence[Charge]) -> list[Charge]:
    """The batch a charge-triggered run covers: the trigger's batch among the grant's
    charges that arrived at the same moment."""
    by_id = {c.id: c for c in charges}
    trigger = by_id.get(trigger_charge_id)
    if trigger is None:
        return []
    same = [c for c in charges if c.arrived_at == trigger.arrived_at]
    for batch in charge_batches(same):
        if any(c.id == trigger_charge_id for c in batch):
            return batch
    return [trigger]


def grant_lock(grant_id: str) -> str:
    return f"grant:{grant_id}"


def log_path(run: AgentRun, attempt: int = 0) -> str:
    """Where a try's debug log is kept in private storage, next to the grant's files."""
    return f"{run.workspace_id}/{run.grant_id}/runs/{run.id}-{attempt + 1}.json"


class RunConflict(Exception):
    """A record the run wrote no longer passes the write check against the database,
    because something changed while the agent worked. Nothing is saved; the run is tried again."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# Queueing.


def _defer(
    conn: Conn, run: AgentRun, *, attempt: int, priority: int, at: datetime | None = None
) -> None:
    conn.execute(
        """select procrastinate_defer_jobs_v1(
             array[row(%s, %s, %s, %s, null, %s, %s)::procrastinate_job_to_defer_v1])""",
        (
            QUEUE,
            TASK_NAME,
            priority,
            grant_lock(run.grant_id),
            Jsonb({"run_id": run.id, "attempt": attempt, "priority": priority}),
            at,
        ),
    )


def queue_run(conn: Conn, grant: Grant, trigger: Trigger, clock_now: datetime) -> AgentRun:
    """Queue an agent run on the grant, in the caller's transaction. Ping it after commit."""
    run = store.insert_run(conn, grant.workspace_id, grant.id, trigger, clock_now)
    priority = THREAD_PRIORITY if trigger.kind == TriggerKind.THREAD_MESSAGE else NORMAL_PRIORITY
    _defer(conn, run, attempt=0, priority=priority)
    return run


def agent_questions_open(questions: list[OpenQuestion]) -> bool:
    return any(q.answer_by == Author.AGENT for q in questions)


# Running.


def _load_input(p: Platform, conn: Conn, run: AgentRun) -> AgentInput:
    grant = store.get_grant(conn, run.grant_id)
    assert grant is not None
    thread = []
    if run.trigger.kind == TriggerKind.THREAD_MESSAGE and run.trigger.id:
        message = store.get_message(conn, run.trigger.id)
        if message is not None:
            thread = store.list_thread(
                conn, charge_id=message.charge_id, record_id=message.record_id
            )
    charges = store.list_charges(conn, grant.id, run.clock_now)
    covers = (
        [c.id for c in batch_for(run.trigger.id, charges)]
        if run.trigger.kind == TriggerKind.CHARGE and run.trigger.id
        else []
    )
    return AgentInput(
        run=run,
        grant=grant,
        charge_ids=covers,
        charges=charges,
        files=store.list_files(conn, grant.id, run.clock_now),
        records=store.list_records(conn, grant.id, run.clock_now),
        thread=thread,
        read_file=lambda f: p.storage.get(f.storage_path),
        checks=p.checks,
    )


def _check_result(run: AgentRun, result: AgentResult) -> None:
    for r in result.records:
        if (
            r.author != Author.AGENT
            or r.grant_id != run.grant_id
            or r.workspace_id != run.workspace_id
        ):
            raise ValueError(f"record {r.id} isn't the agent's record on this run's grant")
        if r.written_at != run.clock_now:
            raise ValueError(f"record {r.id} isn't written at the run's clock time")
    for m in result.messages:
        if m.run_id != run.id or m.grant_id != run.grant_id or m.workspace_id != run.workspace_id:
            raise ValueError(f"message {m.id} isn't this run's message on its grant")


def save_run(
    p: Platform, conn: Conn, run: AgentRun, result: AgentResult, attempt: int = 0
) -> list[OpenQuestion]:
    """Save everything the run wrote, all or nothing, then rerun the checks.

    Takes the grant's lock, so no accountant write lands between the check and the save.
    Raises RunConflict when a record no longer passes the write check.
    """
    _check_result(run, result)
    grant = store.get_grant(conn, run.grant_id, lock=True)
    assert grant is not None
    now = workspace_now(store.workspace_by_id(conn, grant.workspace_id))
    records = store.list_records(conn, grant.id, now)
    charges = store.list_charges(conn, grant.id, now)
    files = store.list_files(conn, grant.id, now)
    problems: list[str] = []
    for r in result.records:
        problems += [
            f"{r.id}: {x}"
            for x in check_new_record(
                r, records, charges, files, default_items=p.checks.default_items
            )
        ]
        records.append(r)
    if problems:
        raise RunConflict(problems)
    store.insert_records(conn, result.records)
    store.insert_messages(conn, result.messages)
    if result.log is not None:
        p.storage.put(log_path(run, attempt), result.log, "application/json")
    store.set_run(conn, run.id, RunStatus.DONE, finished=True, summary=result.summary)
    output = recheck_grant(conn, p.checks, grant, now, run.trigger)
    return output.questions


def execute_run(p: Platform, run_id: str, attempt: int, priority: int = NORMAL_PRIORITY) -> None:
    """One try of one run. The Procrastinate task calls this."""
    with transaction(p.pool) as conn:
        run = store.get_run(conn, run_id, lock=True)
        if run is None or run.status in (RunStatus.DONE, RunStatus.FAILED):
            return
        # The lock means no other run of this grant is in progress. A row still marked
        # running belongs to a worker that stopped mid-run and whose job moved on.
        for other in store.other_running_runs(conn, run.grant_id, run.id):
            store.set_run(
                conn,
                other,
                RunStatus.FAILED,
                finished=True,
                error="the worker stopped during the run",
            )
        store.set_run(conn, run.id, RunStatus.RUNNING, started=True)
        run = run.model_copy(update={"status": RunStatus.RUNNING})
    ping_run(p.pinger, run)

    try:
        with transaction(p.pool) as conn:
            agent_input = _load_input(p, conn, run)
        result = p.agent.run(agent_input)
        with transaction(p.pool) as conn:
            questions = save_run(p, conn, run, result, attempt)
            # A thread run answers only for its own charge or record. Any other question
            # left for the agent gets an ordinary run.
            left_open = bool(getattr(result, "other_open_questions", None)) or (
                run.trigger.kind == TriggerKind.THREAD_MESSAGE and agent_questions_open(questions)
            )
            if left_open and not store.has_pending_run(conn, run.grant_id):
                follow_up = store.insert_run(
                    conn, run.workspace_id, run.grant_id, run.trigger, run.clock_now
                )
                _defer(conn, follow_up, attempt=0, priority=NORMAL_PRIORITY)
            else:
                follow_up = None
        ping_run(p.pinger, run.model_copy(update={"status": RunStatus.DONE}))
        if follow_up is not None:
            ping_run(p.pinger, follow_up)
        ping_changed(p.pinger, run.workspace_id, run.grant_id, "records", "statuses", "thread")
    except Exception as error:  # noqa: BLE001 - any failure fails the try, and nothing was saved
        message = f"{type(error).__name__}: {error}"[:2000]
        log.warning("agent run %s try %s failed: %s", run.id, attempt + 1, type(error).__name__)
        # The agent's AgentRunFailed says whether trying again could help, and carries the
        # try's debug log, which is kept even though nothing else is saved.
        retryable = bool(getattr(error, "retryable", True))
        debug_log = getattr(error, "log", None)
        if isinstance(debug_log, bytes):
            try:
                p.storage.put(log_path(run, attempt), debug_log, "application/json")
            except Exception:  # noqa: BLE001 - a lost log mustn't hide the failure
                log.warning("debug log of run %s try %s not stored", run.id, attempt + 1)
        _after_failure(p, run, attempt, priority, message, retryable=retryable)


def _after_failure(
    p: Platform, run: AgentRun, attempt: int, priority: int, message: str, *, retryable: bool
) -> None:
    if retryable and attempt < p.run_retries:
        with transaction(p.pool) as conn:
            store.set_run(conn, run.id, RunStatus.QUEUED, error=message)
            at = datetime.now(UTC) + timedelta(seconds=p.run_retry_wait_seconds)
            _defer(conn, run, attempt=attempt + 1, priority=priority, at=at)
        ping_run(p.pinger, run.model_copy(update={"status": RunStatus.QUEUED}))
        return
    with transaction(p.pool) as conn:
        store.set_run(conn, run.id, RunStatus.FAILED, finished=True, error=message)
        grant = store.get_grant(conn, run.grant_id, lock=True)
        assert grant is not None
        now = workspace_now(store.workspace_by_id(conn, grant.workspace_id))
        recheck_grant(conn, p.checks, grant, now, run.trigger)
    ping_run(p.pinger, run.model_copy(update={"status": RunStatus.FAILED}))
    ping_changed(p.pinger, run.workspace_id, run.grant_id, "statuses")


# Procrastinate.

app = procrastinate.App(connector=procrastinate.PsycopgConnector())


@app.task(name=TASK_NAME, queue=QUEUE, pass_context=False)
def run_agent(run_id: str, attempt: int = 0, priority: int = NORMAL_PRIORITY) -> None:
    execute_run(get_platform(), run_id, attempt, priority)


@app.periodic(cron="* * * * *", periodic_id="retry_stalled")
@app.task(name="retry_stalled_runs", queue=QUEUE, pass_context=True)
async def retry_stalled_runs(context: procrastinate.JobContext, timestamp: int) -> None:
    """A job cut off by a restart stays "doing" and holds its grant's lock. Put it back
    in the queue once its worker has stopped sending heartbeats (Procrastinate's recipe)."""
    for job in await context.app.job_manager.get_stalled_jobs(task_name=TASK_NAME):
        await context.app.job_manager.retry_job(job)
