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
from procrastinate.jobs import Job
from procrastinate.retry import BaseRetryStrategy, RetryDecision
from psycopg.types.json import Jsonb

from app.contracts.checks import OpenQuestion
from app.contracts.records import Author
from app.contracts.rules import check_new_record, run_read_point
from app.contracts.runs import AgentRun, RunStatus, Trigger, TriggerKind, batch_for
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


# A refused save starts the run over from a fresh read this many times, then it fails.
REDOS = 2
# At most this many follow-up runs after one thread run. Safe because any ordinary run
# answers every question open for the agent on its grant before it can finish
# (contracts.md section 9), so the first follow-up covers the rest.
MAX_FOLLOW_UPS = 10


def grant_lock(grant_id: str) -> str:
    return f"grant:{grant_id}"


def log_path(run: AgentRun, attempt: int = 0) -> str:
    """Where a try's debug log is kept in private storage, next to the grant's files."""
    return f"{run.workspace_id}/{run.grant_id}/runs/{run.id}-{attempt + 1}.json"


class RetryRun(Exception):
    """Raised out of a job to have Procrastinate try the same job again. A retried job keeps
    its ID, so among jobs of the same priority it keeps its place in the grant's queue. A
    higher-priority job, such as a thread question, can run while the retry waits."""


class _RunRetry(BaseRetryStrategy):
    def get_retry_decision(self, *, exception: BaseException, job: Job) -> RetryDecision | None:
        if not isinstance(exception, RetryRun):
            return None
        wait = get_platform().run_retry_wait_seconds
        if wait <= 0:
            return RetryDecision()
        return RetryDecision(retry_at=datetime.now(UTC) + timedelta(seconds=wait))


class RunConflict(Exception):
    """A record the run wrote no longer passes the write check against the database,
    because something changed while the agent worked. Nothing is saved; the run is tried again."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# Queueing.


def _defer(
    conn: Conn,
    run: AgentRun,
    *,
    attempt: int,
    priority: int,
    at: datetime | None = None,
    catch_up: bool = False,
) -> None:
    conn.execute(
        """select procrastinate_defer_jobs_v1(
             array[row(%s, %s, %s, %s, null, %s, %s)::procrastinate_job_to_defer_v1])""",
        (
            QUEUE,
            TASK_NAME,
            priority,
            grant_lock(run.grant_id),
            Jsonb(
                {"run_id": run.id, "attempt": attempt, "priority": priority, "catch_up": catch_up}
            ),
            at,
        ),
    )


def grant_catching_up(conn: Conn, grant_id: str) -> bool:
    """Whether the agent is still working through runs a clock move queued on this grant
    (decision 0023). The move marks each run's job as a catch-up, and the mark lasts through
    retries until the run is done or has failed for good."""
    row = conn.execute(
        """select 1 from procrastinate_jobs
           where lock = %s and status in ('todo', 'doing') and (args ->> 'catch_up')::boolean
           limit 1""",
        (grant_lock(grant_id),),
    ).fetchone()
    return row is not None


def queue_run(
    conn: Conn, grant: Grant, trigger: Trigger, clock_now: datetime, *, catch_up: bool = False
) -> AgentRun:
    """Queue an agent run on the grant, in the caller's transaction. Ping it after commit.

    A run a thread message starts names the thread's charge or record. `catch_up` marks a
    run a clock move queued for something the clock passed; it works as of `clock_now`, its
    arrival time. A thread question goes ahead of queued runs, except while the agent
    catches up: then it waits, so "the agent never answers with arrivals it hasn't read"
    (decision 0023)."""
    subject: dict[str, str | None] = {}
    if trigger.kind == TriggerKind.THREAD_MESSAGE and trigger.id:
        message = store.get_message(conn, trigger.id)
        assert message is not None, "a thread run's message is stored first"
        subject = {"thread_charge_id": message.charge_id, "thread_record_id": message.record_id}
    run = store.insert_run(conn, grant.workspace_id, grant.id, trigger, clock_now, **subject)
    priority = NORMAL_PRIORITY
    if trigger.kind == TriggerKind.THREAD_MESSAGE and not grant_catching_up(conn, grant.id):
        priority = THREAD_PRIORITY
    _defer(conn, run, attempt=0, priority=priority, catch_up=catch_up)
    return run


def agent_questions_open(questions: Sequence[OpenQuestion]) -> bool:
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
    # Everything stored on the grant, whatever its date; only arrivals the clock hasn't
    # released by the run's time are hidden (the run-order ruling, 2).
    charges = store.list_charges(conn, grant.id, run.clock_now)
    covers = (
        [c.id for c in batch_for(run.trigger.id, charges)]
        if run.trigger.kind == TriggerKind.CHARGE and run.trigger.id
        else []
    )
    files = store.list_files(conn, grant.id, run.clock_now)
    records = store.list_records(conn, grant.id)
    # Call 40: the last stored point the run reads, over exactly what it's given, taken at
    # this read (a redo's fresh read takes it again), never at save.
    read_point = run_read_point(records, charges, files)
    store.set_read_point(conn, run.id, read_point)
    run = run.model_copy(update={"read_through_seq": read_point})
    return AgentInput(
        run=run,
        grant=grant,
        charge_ids=covers,
        charges=charges,
        files=files,
        records=records,
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
        if r.read_through_seq != run.read_through_seq:
            raise ValueError(f"record {r.id} doesn't carry the run's read point")
    for m in result.messages:
        if m.run_id != run.id or m.grant_id != run.grant_id or m.workspace_id != run.workspace_id:
            raise ValueError(f"message {m.id} isn't this run's message on its grant")


def save_run(
    p: Platform,
    conn: Conn,
    run: AgentRun,
    result: AgentResult,
    attempt: int = 0,
    *,
    catch_up: bool = False,
) -> Sequence[OpenQuestion]:
    """Save everything the run wrote, all or nothing, then rerun the checks.

    The run's records are checked in the order they'll be stored, against everything stored
    on the grant by then (the run-order ruling, 3). The grant's row lock is held from the
    check through the insert, and every write to the grant takes it, so nothing lands
    between them. Raises RunConflict when the check refuses a record; a record that only
    waits is saved, waiting.
    """
    _check_result(run, result)
    grant = store.get_grant(conn, run.grant_id, lock=True)
    assert grant is not None
    now = workspace_now(store.workspace_by_id(conn, grant.workspace_id))
    records = store.list_records(conn, grant.id)
    charges = store.list_charges(conn, grant.id, now)
    files = store.list_files(conn, grant.id, now)
    problems: list[str] = []
    for r in result.records:
        problems += [
            f"{r.id}: {x}"
            for x in check_new_record(
                r,
                records,
                charges,
                files,
                default_items=p.checks.default_items,
                trigger=run.trigger,
            )
        ]
        records.append(r)
    on_grant = {c.id for c in charges} | {r.id for r in records}
    for m in result.messages:
        if (m.charge_id or m.record_id) not in on_grant:
            problems.append(f"message {m.id} is about something not on the run's grant")
    if problems:
        raise RunConflict(problems)
    store.insert_records(conn, result.records)
    store.insert_messages(conn, result.messages)
    stored_log = None
    if result.log is not None:
        stored_log = log_path(run, attempt)
        p.storage.put(stored_log, result.log, "application/json")
    store.set_run(
        conn, run.id, RunStatus.DONE, finished=True, summary=result.summary, log_path=stored_log
    )
    if catch_up:
        from .clock import step_after_catch_up

        return step_after_catch_up(p, conn, grant, run).questions
    output = recheck_grant(conn, p.checks, grant, now, run.trigger)
    return output.questions


def follow_up_triggers(open_questions: Sequence[OpenQuestion]) -> list[Trigger]:
    """The triggers of the ordinary runs for the questions a thread run left open: one run per
    charge whose question is open, with trigger kind `open_question` naming that charge, so
    its history line names the real cause (the main coordinator's ruling)."""
    charges = list(dict.fromkeys(q.charge_id for q in open_questions))
    return [Trigger(kind=TriggerKind.OPEN_QUESTION, id=c) for c in charges]


def _follow_ups(conn: Conn, run: AgentRun, triggers: Sequence[Trigger]) -> list[AgentRun]:
    runs: list[AgentRun] = []
    for trigger in triggers:
        follow_up = store.insert_run(conn, run.workspace_id, run.grant_id, trigger, run.clock_now)
        _defer(conn, follow_up, attempt=0, priority=NORMAL_PRIORITY)
        runs.append(follow_up)
    return runs


def _start(p: Platform, run_id: str, catch_up: bool) -> AgentRun | None:
    """Mark the run running and fix its clock time (the run-order ruling, 1): a run works as
    of the workspace's "now" when it first starts, not when it was queued. A catch-up run
    replays an arrival and keeps that arrival's time (decision 0023)."""
    with transaction(p.pool) as conn:
        run = store.get_run(conn, run_id, lock=True)
        if run is None or run.status in (RunStatus.DONE, RunStatus.FAILED):
            return None
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
        clock_now = run.clock_now
        if run.started_at is None and not catch_up:
            clock_now = workspace_now(store.workspace_by_id(conn, run.workspace_id))
        store.set_run(conn, run.id, RunStatus.RUNNING, started=True, clock_now=clock_now)
        return run.model_copy(update={"status": RunStatus.RUNNING, "clock_now": clock_now})


def _attempt(p: Platform, run: AgentRun, attempt: int, catch_up: bool) -> None:
    """One try: read, run the agent, save. A save the write check refuses starts over from a
    fresh read, up to REDOS times (the run-order ruling, 4); that isn't a failure retry."""
    for redo in range(REDOS + 1):
        with transaction(p.pool) as conn:
            agent_input = _load_input(p, conn, run)
        run = agent_input.run  # with the read point of this read
        result = p.agent.run(agent_input)
        try:
            with transaction(p.pool) as conn:
                questions = save_run(p, conn, run, result, attempt, catch_up=catch_up)
                follow_ups = _follow_ups(conn, run, _open_questions(run, result, questions))
        except RunConflict as conflict:
            if result.log is not None:
                # A refused try's debug log is kept too, beside the try's own.
                path = log_path(run, attempt).removesuffix(".json") + f"-refused-{redo + 1}.json"
                try:
                    p.storage.put(path, result.log, "application/json")
                except Exception:  # noqa: BLE001 - a lost log mustn't stop the redo
                    log.warning("debug log of run %s's refused save not stored", run.id)
            if redo < REDOS:
                log.info("run %s redoes after a refused save: %s", run.id, conflict)
                continue
            raise RunFailed(f"RunConflict: {conflict}", retryable=False) from conflict
        ping_run(p.pinger, run.model_copy(update={"status": RunStatus.DONE}))
        for follow_up in follow_ups:
            ping_run(p.pinger, follow_up)
        ping_changed(p.pinger, run.workspace_id, run.grant_id, "records", "statuses", "thread")
        return


def _open_questions(
    run: AgentRun, result: AgentResult, questions: Sequence[OpenQuestion]
) -> list[Trigger]:
    """Follow-ups only after a thread run: it replies and suggests and isn't responsible for
    code's open questions, so any it leaves get an ordinary run right away."""
    if run.trigger.kind != TriggerKind.THREAD_MESSAGE:
        return []
    open_questions = [*getattr(result, "other_open_questions", ())]
    open_questions += [q for q in questions if q.answer_by == Author.AGENT]
    return follow_up_triggers(open_questions)[:MAX_FOLLOW_UPS]


class RunFailed(Exception):
    def __init__(self, message: str, *, retryable: bool, log: bytes | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.log = log


def execute_run(p: Platform, run_id: str, attempt: int, catch_up: bool = False) -> None:
    """One try of one run. The Procrastinate task calls this.

    Whatever goes wrong ends in one of two ways: a retry of the same job, or the run marked
    failed with the usual problem raised by the checks. That includes an error before the
    try starts and an error while recording a failure.
    """
    try:
        run = _start(p, run_id, catch_up)
        if run is None:
            return
        ping_run(p.pinger, run)
        try:
            _attempt(p, run, attempt, catch_up)
        except Exception as error:  # noqa: BLE001 - any failure fails the try; nothing was saved
            _after_failure(p, run, attempt, error, catch_up)
    except RetryRun:
        raise
    except Exception as error:  # noqa: BLE001 - the run must not stay queued or running
        log.warning("agent run %s ended by an error: %s", run_id, type(error).__name__)
        _fail_for_good(p, run_id, f"{type(error).__name__}: {error}"[:2000], None, catch_up)


def _after_failure(
    p: Platform, run: AgentRun, attempt: int, error: Exception, catch_up: bool = False
) -> None:
    message = f"{type(error).__name__}: {error}"[:2000]
    log.warning("agent run %s try %s failed: %s", run.id, attempt + 1, type(error).__name__)
    # The agent's AgentRunFailed says whether trying again could help, and carries the
    # try's debug log, which is kept even though nothing else is saved.
    retryable = bool(getattr(error, "retryable", True))
    debug_log = getattr(error, "log", None)
    stored_log = None
    if isinstance(debug_log, bytes):
        try:
            p.storage.put(log_path(run, attempt), debug_log, "application/json")
            stored_log = log_path(run, attempt)
        except Exception:  # noqa: BLE001 - a lost log mustn't hide the failure
            log.warning("debug log of run %s try %s not stored", run.id, attempt + 1)
    if retryable and attempt < p.run_retries:
        with transaction(p.pool) as conn:
            store.set_run(conn, run.id, RunStatus.QUEUED, error=message, log_path=stored_log)
        ping_run(p.pinger, run.model_copy(update={"status": RunStatus.QUEUED}))
        raise RetryRun(message)
    _fail_for_good(p, run.id, message, stored_log, catch_up)


def _fail_for_good(
    p: Platform, run_id: str, message: str, stored_log: str | None, catch_up: bool = False
) -> None:
    """Mark the run failed, then rerun the checks with it in failed_runs, so they raise the
    usual problem where its trigger points. A catch-up run's checks step on from its own
    time, as its save would have.

    Two transactions: the run ends `failed` even when the checks themselves raise, which is
    logged; the next recheck on the grant raises the problem then."""
    with transaction(p.pool) as conn:
        run = store.get_run(conn, run_id, lock=True)
        if run is None or run.status in (RunStatus.DONE, RunStatus.FAILED):
            return
        store.set_run(
            conn, run.id, RunStatus.FAILED, finished=True, error=message, log_path=stored_log
        )
    ping_run(p.pinger, run.model_copy(update={"status": RunStatus.FAILED}))
    try:
        with transaction(p.pool) as conn:
            grant = store.get_grant(conn, run.grant_id, lock=True)
            assert grant is not None
            if catch_up:
                from .clock import step_after_catch_up

                step_after_catch_up(p, conn, grant, run)
            else:
                now = workspace_now(store.workspace_by_id(conn, grant.workspace_id))
                recheck_grant(conn, p.checks, grant, now, run.trigger)
    except Exception as error:  # noqa: BLE001 - the run is failed already; say so and go on
        log.warning("checks after run %s failed for good raised %s", run.id, type(error).__name__)
        return
    ping_changed(p.pinger, run.workspace_id, run.grant_id, "statuses")


# Procrastinate.

app = procrastinate.App(connector=procrastinate.PsycopgConnector())


@app.task(name=TASK_NAME, queue=QUEUE, pass_context=True, retry=_RunRetry())
def run_agent(
    context: procrastinate.JobContext,
    run_id: str,
    attempt: int = 0,
    priority: int = NORMAL_PRIORITY,
    catch_up: bool = False,
) -> None:
    """One try of one run. The try number is the job's own count of earlier attempts.
    `attempt` and `priority` are in the job's arguments for reading the queue; the job's own
    attempts count is what's used. `catch_up` marks a run a clock move queued."""
    execute_run(get_platform(), run_id, context.job.attempts, catch_up)


@app.periodic(cron="* * * * *", periodic_id="retry_stalled")
@app.task(name="retry_stalled_runs", queue=QUEUE, pass_context=True)
async def retry_stalled_runs(context: procrastinate.JobContext, timestamp: int) -> None:
    """A job cut off by a restart stays "doing" and holds its grant's lock. Put it back
    in the queue once its worker has stopped sending heartbeats (Procrastinate's recipe)."""
    for job in await context.app.job_manager.get_stalled_jobs(task_name=TASK_NAME):
        await context.app.job_manager.retry_job(job)


@app.periodic(cron="5 0 * * *", periodic_id="daily_recheck")
@app.task(name="daily_recheck", queue=QUEUE, pass_context=False)
def daily_recheck_task(timestamp: int) -> None:
    """Shortly after midnight UTC: time alone can change a status in a real workspace."""
    from .clock import daily_recheck

    daily_recheck(get_platform())
