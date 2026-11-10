"""The job worker: one run at a time per grant, thread questions first, a run saved all
or nothing, retries, and the checks rerun after each save or final failure."""

from __future__ import annotations

import threading
import time
import uuid

from app.contracts.charges import Charge
from app.contracts.records import Author, Record
from app.contracts.runs import RunStatus, Trigger, TriggerKind
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant
from app.db import actions, store
from app.db.jobs import NORMAL_PRIORITY, THREAD_PRIORITY, log_path, queue_run
from app.db.platform import Platform
from app.db.pool import transaction
from app.db.ports import AgentInput, AgentResult
from tests.db.platform_fixtures import (  # noqa: F401 - fixtures
    FakeAgent,
    FakeChecks,
    FakePinger,
    FakeStorage,
    new_auth_user,
    platform,
    platform_database_url,
    run_worker_until_idle,
)

INVOICE = b"INVOICE INV-1001\nSediment core liners, 50 count\nTotal: $1,240.00\n"


def _grant(p: Platform) -> Grant:
    user_id = new_auth_user(p)
    with transaction(p.pool) as conn:
        store.upsert_user(conn, _user(user_id))
        workspace = store.create_workspace(conn, user_id, "Lab")
    return actions.add_grant(p, workspace.id, actions.Upload("invoice.txt", "text/plain", INVOICE))


def _user(user_id: str):
    from app.contracts.workspaces import User

    return User(id=user_id, email="pat@university.example")


def _runs(p: Platform, grant: Grant):
    with transaction(p.pool) as conn:
        return store.list_runs(conn, grant.id)


def _bill(agent_input: AgentInput, *, total: int = 124000) -> Record:
    f = agent_input.files[0]
    start = INVOICE.index(b"Total:")
    passage = INVOICE[start:].decode().strip()
    citation = {
        "file_id": f.id,
        "passage": passage,
        "location": {
            "type": "char_location",
            "start_char_index": start,
            "end_char_index": start + len(passage),
        },
        "match": "exact",
    }
    return Record.model_validate(
        {
            "id": str(uuid.uuid4()),
            "workspace_id": agent_input.run.workspace_id,
            "grant_id": agent_input.run.grant_id,
            "author": "agent",
            "written_at": agent_input.run.clock_now,
            "data": {
                "kind": "bill",
                "total": {"value": total, "text": "$1,240.00", "citation": citation},
            },
        }
    )


def test_a_run_saves_its_records_and_reruns_the_checks(platform: Platform) -> None:  # noqa: F811
    agent = platform.agent
    assert isinstance(agent, FakeAgent)

    def behave(i: AgentInput) -> AgentResult:
        assert [f.name for f in i.files] == ["invoice.txt"]
        assert i.read_file(i.files[0]) == INVOICE
        return AgentResult(records=[_bill(i)], summary="Read the invoice.", log=b"{}")

    agent.behave = behave
    grant = _grant(platform)
    [run] = _runs(platform, grant)
    run_worker_until_idle(str(platform.pool.conninfo))

    [run] = _runs(platform, grant)
    assert run.status == RunStatus.DONE and run.summary == "Read the invoice."
    assert run.started_at and run.finished_at and run.error is None
    with transaction(platform.pool) as conn:
        records = store.list_records(conn, grant.id, run.clock_now)
    assert [r.kind for r in records] == ["bill"] and records[0].author == Author.AGENT
    storage = platform.storage
    assert isinstance(storage, FakeStorage)
    assert storage.objects[log_path(run)] == (b"{}", "application/json")
    pinger = platform.pinger
    assert isinstance(pinger, FakePinger)
    statuses = [p[2]["status"] for p in pinger.pings if p[1] == "run"]
    assert statuses == ["queued", "running", "done"]


def test_a_run_whose_write_no_longer_passes_saves_nothing_and_fails_after_its_retries(
    platform: Platform,  # noqa: F811
) -> None:
    agent = platform.agent
    assert isinstance(agent, FakeAgent)

    def behave(i: AgentInput) -> AgentResult:
        good = _bill(i)
        bad = good.model_copy(update={"id": str(uuid.uuid4()), "replaces_id": "no-such-record"})
        return AgentResult(records=[good, bad])

    agent.behave = behave
    grant = _grant(platform)
    run_worker_until_idle(str(platform.pool.conninfo))

    assert len(agent.inputs) == platform.run_retries + 1
    [run] = _runs(platform, grant)
    assert run.status == RunStatus.FAILED and run.error and "RunConflict" in run.error
    with transaction(platform.pool) as conn:
        assert store.list_records(conn, grant.id, run.clock_now) == []
        statuses = store.current_statuses(conn, grant.id)
        row = conn.execute(
            "select trigger_kind, trigger_id from public.statuses where file_id is not null"
        ).fetchone()
    # The checks raised a problem on the file that triggered the run.
    [(key, status)] = statuses.items()
    assert key[0] == "file" and status.flagged
    assert row == {"trigger_kind": "file", "trigger_id": run.trigger.id}


def test_a_failed_try_is_retried_and_can_then_succeed(platform: Platform) -> None:  # noqa: F811
    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    tries: list[int] = []

    def behave(i: AgentInput) -> AgentResult:
        tries.append(1)
        if len(tries) == 1:
            raise RuntimeError("overloaded")
        return AgentResult(summary="ok")

    agent.behave = behave
    grant = _grant(platform)
    run_worker_until_idle(str(platform.pool.conninfo))
    [run] = _runs(platform, grant)
    assert len(tries) == 2 and run.status == RunStatus.DONE and run.error is None


def test_a_thread_question_goes_ahead_of_queued_runs(platform: Platform) -> None:  # noqa: F811
    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    grant = _grant(platform)  # queues the award letter's run
    with transaction(platform.pool) as conn:
        charge = Charge(
            id=str(uuid.uuid4()),
            workspace_id=grant.workspace_id,
            grant_id=grant.id,
            ledger_line_id=f"L-{uuid.uuid4().hex[:6]}",
            transaction_date="2025-11-12",  # pyright: ignore[reportArgumentType]
            posting_date="2025-11-14",  # pyright: ignore[reportArgumentType]
            arrived_at="2025-11-14T00:00:00Z",  # pyright: ignore[reportArgumentType]
            amount_cents=124000,
            description="Sediment core liners",
            account="55016 Lab Instruments and Supplies",
        )
        store.insert_charges(conn, [charge])
        now = store.list_runs(conn, grant.id)[0].clock_now
        queue_run(conn, grant, Trigger(kind=TriggerKind.CHARGE, id=charge.id), now)
        user_id = new_auth_user(platform)
        store.upsert_user(conn, _user(user_id))
        message = ThreadMessage(
            id=str(uuid.uuid4()),
            workspace_id=grant.workspace_id,
            grant_id=grant.id,
            charge_id=charge.id,
            author=Author.USER,
            author_user_id=user_id,
            text="Is this the right invoice?",
            written_at=now,
        )
        store.insert_messages(conn, [message])
        queue_run(conn, grant, Trigger(kind=TriggerKind.THREAD_MESSAGE, id=message.id), now)
        jobs = conn.execute("select priority from procrastinate_jobs order by id").fetchall()
    assert [j["priority"] for j in jobs] == [NORMAL_PRIORITY, NORMAL_PRIORITY, THREAD_PRIORITY]

    run_worker_until_idle(str(platform.pool.conninfo))
    kinds = [i.run.trigger.kind for i in agent.inputs]
    assert kinds == [TriggerKind.THREAD_MESSAGE, TriggerKind.FILE, TriggerKind.CHARGE]
    assert [m.text for m in agent.inputs[0].thread] == ["Is this the right invoice?"]


def test_runs_for_one_grant_go_one_at_a_time(platform: Platform) -> None:  # noqa: F811
    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    running: dict[str, int] = {}
    most: dict[str, int] = {}
    lock = threading.Lock()

    def behave(i: AgentInput) -> AgentResult:
        g = i.run.grant_id
        with lock:
            running[g] = running.get(g, 0) + 1
            most[g] = max(most.get(g, 0), running[g])
        time.sleep(0.2)
        with lock:
            running[g] -= 1
        return AgentResult()

    agent.behave = behave
    grants = [_grant(platform), _grant(platform)]
    for grant in grants:
        with transaction(platform.pool) as conn:
            now = store.list_runs(conn, grant.id)[0].clock_now
            queue_run(conn, grant, Trigger(kind=TriggerKind.CLOCK), now)
    run_worker_until_idle(str(platform.pool.conninfo), concurrency=4)
    assert len(agent.inputs) == 4
    assert most == {g.id: 1 for g in grants}
    assert all(r.status == RunStatus.DONE for g in grants for r in _runs(platform, g))


def test_charges_that_arrive_together_share_a_run_in_batches(platform: Platform) -> None:  # noqa: F811
    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    grant = _grant(platform)
    header = b"line_id,transaction_date,posting_date,amount,description,account\n"
    rows = b"".join(
        f"B-{i:03},2025-11-12,2025-11-14,10.00,Item {i},55016 Lab\n".encode() for i in range(30)
    )
    result = actions.add_ledger(platform, grant, header + rows)
    assert result.added == 30
    runs = [r for r in _runs(platform, grant) if r.trigger.kind == TriggerKind.CHARGE]
    assert len(runs) == 2
    run_worker_until_idle(str(platform.pool.conninfo))
    covered = [i.charge_ids for i in agent.inputs if i.run.trigger.kind == TriggerKind.CHARGE]
    assert sorted(len(c) for c in covered) == [5, 25]
    assert len({c for batch in covered for c in batch}) == 30
