"""The job worker: one run at a time per grant, thread questions first, a run saved all
or nothing, retries, and the checks rerun after each save or final failure."""

from __future__ import annotations

import threading
import time
import uuid

import pytest

from app.contracts.charges import Charge
from app.contracts.records import Author, Record
from app.contracts.runs import RunStatus, Trigger, TriggerKind
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant
from app.db import actions, store
from app.db.jobs import NORMAL_PRIORITY, REDOS, THREAD_PRIORITY, log_path, queue_run
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
            "read_through_seq": agent_input.run.read_through_seq,
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
    assert run.log_path == log_path(run)
    pinger = platform.pinger
    assert isinstance(pinger, FakePinger)
    statuses = [p[2]["status"] for p in pinger.pings if p[1] == "run"]
    assert statuses == ["queued", "running", "done"]


def test_a_save_that_keeps_being_refused_redoes_then_fails_with_nothing_saved(
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

    assert len(agent.inputs) == REDOS + 1  # redone from a fresh read, not retried
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


class _RunFailed(Exception):
    """Shaped like the agent's AgentRunFailed."""

    def __init__(self, error: str, retryable: bool, log: bytes):
        super().__init__(error)
        self.retryable = retryable
        self.log = log


def test_a_failure_that_cant_be_retried_fails_at_once_and_keeps_its_log(
    platform: Platform,  # noqa: F811
) -> None:
    agent = platform.agent
    assert isinstance(agent, FakeAgent)

    def behave(i: AgentInput) -> AgentResult:
        raise _RunFailed("refused", retryable=False, log=b'{"turns": 3}')

    agent.behave = behave
    grant = _grant(platform)
    run_worker_until_idle(str(platform.pool.conninfo))
    assert len(agent.inputs) == 1
    [run] = _runs(platform, grant)
    assert run.status == RunStatus.FAILED and run.error and "refused" in run.error
    storage = platform.storage
    assert isinstance(storage, FakeStorage)
    assert storage.objects[log_path(run)] == (b'{"turns": 3}', "application/json")


def test_questions_a_thread_run_left_open_get_an_ordinary_run_right_away(
    platform: Platform,  # noqa: F811
) -> None:
    from app.contracts.checks import OpenQuestion
    from app.contracts.records import Question

    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    seen: list[AgentInput] = []

    def behave(i: AgentInput) -> AgentResult:
        seen.append(i)
        if i.run.trigger.kind == TriggerKind.THREAD_MESSAGE:
            question = OpenQuestion(
                charge_id=charge.id, question=Question.ALLOWABLE, answer_by=Author.AGENT
            )
            # Every record the agent writes in a run a thread message started names it.
            bill = _bill(i).model_copy(update={"thread_message_id": i.run.trigger.id})
            return AgentResult(records=[bill], other_open_questions=[question])
        return AgentResult()

    agent.behave = behave
    grant = _grant(platform)
    with transaction(platform.pool) as conn:
        conn.execute(
            "update public.agent_runs set status = 'done' where grant_id = %s", (grant.id,)
        )
        conn.execute("delete from procrastinate_jobs")
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
    with transaction(platform.pool) as conn:
        store.insert_charges(conn, [charge])
        user_id = new_auth_user(platform)
        store.upsert_user(conn, _user(user_id))
        now = store.list_runs(conn, grant.id)[0].clock_now
        message = ThreadMessage(
            id=str(uuid.uuid4()),
            workspace_id=grant.workspace_id,
            grant_id=grant.id,
            charge_id=charge.id,
            author=Author.USER,
            author_user_id=user_id,
            text="Is this allowed?",
            written_at=now,
        )
        store.insert_messages(conn, [message])
        queue_run(conn, grant, Trigger(kind=TriggerKind.THREAD_MESSAGE, id=message.id), now)
    run_worker_until_idle(str(platform.pool.conninfo))
    _, follow_up = seen
    assert follow_up.run.trigger.kind == TriggerKind.OPEN_QUESTION
    assert follow_up.run.trigger.id == charge.id
    assert follow_up.run.thread_charge_id is None
    # The thread run's record was saved, and waits for the accountant.
    from app.contracts.rules import RecordState

    with transaction(platform.pool) as conn:
        records = store.list_records(conn, grant.id)
    [bill] = records
    assert bill.thread_message_id == message.id
    assert RecordState(records).is_waiting(bill.id)


def test_a_thread_runs_record_that_doesnt_name_its_message_is_refused(
    platform: Platform,  # noqa: F811
) -> None:
    """The write check takes the run's trigger, so a thread run can't skip the rule."""
    agent = platform.agent
    assert isinstance(agent, FakeAgent)

    def behave(i: AgentInput) -> AgentResult:
        return AgentResult(records=[_bill(i)])

    agent.behave = behave
    grant = _grant(platform)
    with transaction(platform.pool) as conn:
        conn.execute(
            "update public.agent_runs set status = 'done' where grant_id = %s", (grant.id,)
        )
        conn.execute("delete from procrastinate_jobs")
        user_id = new_auth_user(platform)
        store.upsert_user(conn, _user(user_id))
        now = store.list_runs(conn, grant.id)[0].clock_now
        charge = _charge(platform, grant)
        message = ThreadMessage(
            id=str(uuid.uuid4()),
            workspace_id=grant.workspace_id,
            grant_id=grant.id,
            charge_id=charge.id,
            author=Author.USER,
            author_user_id=user_id,
            text="Can you find the invoice?",
            written_at=now,
        )
        store.insert_messages(conn, [message])
        queue_run(conn, grant, Trigger(kind=TriggerKind.THREAD_MESSAGE, id=message.id), now)
    run_worker_until_idle(str(platform.pool.conninfo))
    thread_run = next(r for r in _runs(platform, grant) if r.thread_charge_id == charge.id)
    assert thread_run.status == RunStatus.FAILED and "RunConflict" in (thread_run.error or "")
    assert len(agent.inputs) == REDOS + 1  # the thread run and its redos


def test_open_question_follow_ups_name_each_charge_once() -> None:
    from app.contracts.checks import OpenQuestion
    from app.contracts.records import Question
    from app.db.jobs import follow_up_triggers

    questions = [
        OpenQuestion(charge_id=c, question=Question.ALLOWABLE, answer_by=Author.AGENT)
        for c in ("c-1", "c-2", "c-1")
    ]
    triggers = follow_up_triggers(questions)
    assert [(t.kind.value, t.id) for t in triggers] == [
        ("open_question", "c-1"),
        ("open_question", "c-2"),
    ]
    assert follow_up_triggers([]) == []


# The run-order ruling (PR 59, provisional call 35): one order, the order stored.


def _charge(p: Platform, grant: Grant, line: str = "L-1001") -> Charge:
    charge = Charge(
        id=str(uuid.uuid4()),
        workspace_id=grant.workspace_id,
        grant_id=grant.id,
        ledger_line_id=f"{line}-{uuid.uuid4().hex[:4]}",
        transaction_date="2025-11-12",  # pyright: ignore[reportArgumentType]
        posting_date="2025-11-14",  # pyright: ignore[reportArgumentType]
        arrived_at="2025-11-14T00:00:00Z",  # pyright: ignore[reportArgumentType]
        amount_cents=124000,
        description="Sediment core liners",
        account="55016 Lab Instruments and Supplies",
    )
    with transaction(p.pool) as conn:
        store.insert_charges(conn, [charge])
    return charge


def _user_id(p: Platform, grant: Grant) -> str:
    with transaction(p.pool) as conn:
        return store.workspace_by_id(conn, grant.workspace_id).owner_id


def test_the_agents_second_link_waits_when_the_accountant_linked_during_the_run(
    platform: Platform,  # noqa: F811
) -> None:
    """The sample grant's invoice: the accountant links it to L-1001 while the agent's run
    for L-1001 works; the agent's own link, stored after, is a second link and waits."""
    from app.contracts.rules import RecordState

    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    calls: list[TriggerKind] = []

    def behave(i: AgentInput) -> AgentResult:
        calls.append(i.run.trigger.kind)
        if i.run.trigger.kind == TriggerKind.FILE:
            return AgentResult(records=[_bill(i)])
        [bill] = [r for r in i.records if r.kind == "bill"]
        actions.add_record(
            platform,
            grant,
            _user_id(platform, grant),
            {"kind": "link", "record_id": bill.id, "charge_id": charge.id},
            None,
        )
        part = bill.data.total.citation  # pyright: ignore[reportAttributeAccessIssue]
        assert part is not None
        link = Record.model_validate(
            {
                "id": str(uuid.uuid4()),
                "workspace_id": i.run.workspace_id,
                "grant_id": i.run.grant_id,
                "author": "agent",
                "written_at": i.run.clock_now,
                "read_through_seq": i.run.read_through_seq,
                "data": {
                    "kind": "link",
                    "record_id": bill.id,
                    "charge_id": charge.id,
                    "part": part.model_dump(mode="json"),
                },
            }
        )
        return AgentResult(records=[link])

    agent.behave = behave
    grant = _grant(platform)
    run_worker_until_idle(str(platform.pool.conninfo))
    charge = _charge(platform, grant)
    with transaction(platform.pool) as conn:
        now = store.list_runs(conn, grant.id)[0].clock_now
        queue_run(conn, grant, Trigger(kind=TriggerKind.CHARGE, id=charge.id), now)
    run_worker_until_idle(str(platform.pool.conninfo))

    assert calls == [TriggerKind.FILE, TriggerKind.CHARGE]  # no redo
    with transaction(platform.pool) as conn:
        records = store.list_records(conn, grant.id)
    assert [(r.kind, r.author) for r in records] == [
        ("bill", Author.AGENT),
        ("link", Author.USER),
        ("link", Author.AGENT),
    ]
    state = RecordState(records)
    assert state.is_current(records[1].id)
    assert state.is_waiting(records[2].id) and not state.is_effective(records[2].id)


def test_a_refused_save_saves_nothing_and_redoes_from_a_fresh_read(
    platform: Platform,  # noqa: F811
) -> None:
    agent = platform.agent
    assert isinstance(agent, FakeAgent)

    def behave(i: AgentInput) -> AgentResult:
        good = _bill(i)
        if len(agent.inputs) == 1:
            bad = good.model_copy(update={"replaces_id": "no-such-record"})
            return AgentResult(records=[bad])
        return AgentResult(records=[good])

    agent.behave = behave
    grant = _grant(platform)
    run_worker_until_idle(str(platform.pool.conninfo))
    assert len(agent.inputs) == 2
    [run] = _runs(platform, grant)
    assert run.status == RunStatus.DONE and run.error is None
    with transaction(platform.pool) as conn:
        assert [r.kind for r in store.list_records(conn, grant.id)] == ["bill"]


def test_an_unrelated_accountant_record_during_a_run_causes_no_redo(
    platform: Platform,  # noqa: F811
) -> None:
    agent = platform.agent
    assert isinstance(agent, FakeAgent)

    def behave(i: AgentInput) -> AgentResult:
        actions.add_record(
            platform,
            grant,
            _user_id(platform, grant),
            {"kind": "person", "name": {"value": "Lee Example"}, "role": {"value": "Lab manager"}},
            None,
        )
        return AgentResult(records=[_bill(i)])

    agent.behave = behave
    grant = _grant(platform)
    run_worker_until_idle(str(platform.pool.conninfo))
    assert len(agent.inputs) == 1
    [run] = _runs(platform, grant)
    assert run.status == RunStatus.DONE
    with transaction(platform.pool) as conn:
        assert [r.kind for r in store.list_records(conn, grant.id)] == ["person", "bill"]


def test_a_question_left_open_during_a_run_gets_its_run(platform: Platform) -> None:  # noqa: F811
    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    checks = platform.checks
    assert isinstance(checks, FakeChecks)

    def behave(i: AgentInput) -> AgentResult:
        if len(agent.inputs) == 1:
            checks.agent_questions = True
            _charge(platform, grant)
            actions.add_record(
                platform,
                grant,
                _user_id(platform, grant),
                {"kind": "other_term", "label": "Note", "statement": {"value": "Look again."}},
                None,
            )
        return AgentResult()

    agent.behave = behave
    grant = _grant(platform)
    run_worker_until_idle(str(platform.pool.conninfo))
    assert [i.run.trigger.kind for i in agent.inputs] == [TriggerKind.FILE, TriggerKind.RECORD]
    # The second run read everything stored when it started, the record included.
    assert any(r.kind == "other_term" for r in agent.inputs[1].records)


def test_a_runs_clock_time_is_fixed_when_it_starts(platform: Platform) -> None:  # noqa: F811
    from datetime import UTC, datetime

    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    grant = _grant(platform)
    later = datetime(2030, 1, 1, tzinfo=UTC)
    with transaction(platform.pool) as conn:
        conn.execute(
            "update public.workspaces set clock_now = %s where id = %s", (later, grant.workspace_id)
        )
    run_worker_until_idle(str(platform.pool.conninfo))
    [run] = _runs(platform, grant)
    assert agent.inputs[0].run.clock_now == later and run.clock_now == later


def test_an_error_before_the_try_ends_the_run_failed_with_its_problem(
    platform: Platform,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_: object) -> list[str]:
        raise ConnectionError("lost the database")

    grant = _grant(platform)
    monkeypatch.setattr(store, "other_running_runs", broken)
    run_worker_until_idle(str(platform.pool.conninfo))
    [run] = _runs(platform, grant)
    assert run.status == RunStatus.FAILED and run.error and "ConnectionError" in run.error
    with transaction(platform.pool) as conn:
        assert not store.has_pending_run(conn, grant.id)
        [(key, status)] = store.current_statuses(conn, grant.id).items()
    assert key[0] == "file" and status.flagged


def test_an_error_while_recording_a_failure_still_ends_the_run_failed(
    platform: Platform,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = platform.agent
    assert isinstance(agent, FakeAgent)

    def behave(i: AgentInput) -> AgentResult:
        raise RuntimeError("overloaded")

    agent.behave = behave
    real_set_run = store.set_run

    def set_run(conn: object, run_id: str, status: RunStatus, **kwargs: object) -> None:
        if status == RunStatus.QUEUED:
            raise ConnectionError("lost the database")
        real_set_run(conn, run_id, status, **kwargs)  # pyright: ignore[reportArgumentType]

    grant = _grant(platform)
    monkeypatch.setattr(store, "set_run", set_run)
    run_worker_until_idle(str(platform.pool.conninfo))
    [run] = _runs(platform, grant)
    assert run.status == RunStatus.FAILED and run.error and "ConnectionError" in run.error


def test_a_record_sharing_a_queued_run_is_read_by_it_even_as_the_run_starts(
    platform: Platform,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reviewer's hold: the record's write is held just after it decided to share the
    queued run, while the run starts. The run's start waits for the write, then reads it."""
    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    checks = platform.checks
    assert isinstance(checks, FakeChecks)
    grant = _grant(platform)  # queues the award letter's run, not started
    _charge(platform, grant)
    checks.agent_questions = True
    real = store.has_queued_run
    worker: list[threading.Thread] = []

    def held(conn: object, grant_id: str) -> bool:
        shared = real(conn, grant_id)  # pyright: ignore[reportArgumentType]
        thread = threading.Thread(target=run_worker_until_idle, args=(str(platform.pool.conninfo),))
        thread.start()
        worker.append(thread)
        time.sleep(0.5)  # the run tries to start while the record isn't committed
        return shared

    monkeypatch.setattr(store, "has_queued_run", held)
    actions.add_record(
        platform,
        grant,
        _user_id(platform, grant),
        {"kind": "other_term", "label": "Note", "statement": {"value": "Look again."}},
        None,
    )
    monkeypatch.setattr(store, "has_queued_run", real)
    worker[0].join(timeout=30)
    [first] = agent.inputs[:1]
    assert any(r.kind == "other_term" for r in first.records)


def test_a_run_ends_failed_even_when_the_checks_raise(
    platform: Platform,  # noqa: F811
) -> None:
    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    checks = platform.checks
    assert isinstance(checks, FakeChecks)

    def behave(i: AgentInput) -> AgentResult:
        raise _RunFailed("refused", retryable=False, log=b"{}")

    agent.behave = behave
    grant = _grant(platform)

    def broken(*_: object) -> None:
        raise RuntimeError("a bug in the checks")

    checks.run_checks = broken  # pyright: ignore[reportAttributeAccessIssue]
    run_worker_until_idle(str(platform.pool.conninfo))
    [run] = _runs(platform, grant)
    assert run.status == RunStatus.FAILED and run.error and "refused" in run.error


# Call 40: a run's read point decides what's new evidence for its answers.


def _answer(i: AgentInput, charge: Charge, answer: str, replaces: str | None = None) -> Record:
    return Record.model_validate(
        {
            "id": str(uuid.uuid4()),
            "workspace_id": i.run.workspace_id,
            "grant_id": i.run.grant_id,
            "author": "agent",
            "written_at": i.run.clock_now,
            "read_through_seq": i.run.read_through_seq,
            "replaces_id": replaces,
            "data": {
                "kind": "judgment",
                "charge_id": charge.id,
                "question": "allowable",
                "text": "Is this cost necessary and reasonable, and is it for this project?",
                "answer": answer,
                "reasoning": "The evidence on file.",
            },
        }
    )


def _frozen_grant(p: Platform) -> tuple[Grant, Charge]:
    """A demo workspace with its clock frozen, a charge, and no runs waiting."""
    from datetime import UTC, datetime

    grant = _grant(p)
    frozen = datetime(2025, 11, 20, tzinfo=UTC)
    with transaction(p.pool) as conn:
        conn.execute(
            "update public.workspaces set clock_now = %s where id = %s",
            (frozen, grant.workspace_id),
        )
        conn.execute(
            "update public.agent_runs set status = 'done' where grant_id = %s", (grant.id,)
        )
        conn.execute("delete from procrastinate_jobs")
    charge = _charge(p, grant)
    with transaction(p.pool) as conn:
        queue_run(conn, grant, Trigger(kind=TriggerKind.CHARGE, id=charge.id), frozen)
    return grant, charge


def _judgments(p: Platform, grant: Grant) -> tuple[list[Record], object]:
    from datetime import UTC, datetime

    from app.contracts.rules import RecordState

    far = datetime(2100, 1, 1, tzinfo=UTC)
    with transaction(p.pool) as conn:
        records = store.list_records(conn, grant.id)
        files = store.list_files(conn, grant.id, far)
    return [r for r in records if r.kind == "judgment"], RecordState(records, files)


def test_a_receipt_uploaded_before_the_next_run_starts_lets_its_supports_count(
    platform: Platform,  # noqa: F811
) -> None:
    """The demo move: the agent is unsure; at the same frozen "now", a receipt is uploaded
    before the next run starts; that run reads it, and its supports counts at once."""
    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    first: list[Record] = []

    def behave(i: AgentInput) -> AgentResult:
        if i.run.trigger.kind == TriggerKind.CHARGE:
            first.append(_answer(i, charge, "unsure"))
            return AgentResult(records=[first[0]])
        return AgentResult(records=[_answer(i, charge, "supports", replaces=first[0].id)])

    agent.behave = behave
    grant, charge = _frozen_grant(platform)
    run_worker_until_idle(str(platform.pool.conninfo))
    actions.add_evidence(platform, grant, actions.Upload("receipt.txt", "text/plain", b"Paid."))
    run_worker_until_idle(str(platform.pool.conninfo))
    judgments, state = _judgments(platform, grant)
    unsure, supports = judgments
    assert supports.read_through_seq is not None
    assert state.is_current(supports.id) and not state.is_waiting(supports.id)  # pyright: ignore[reportAttributeAccessIssue]
    assert not state.is_current(unsure.id)  # pyright: ignore[reportAttributeAccessIssue]


def test_a_receipt_uploaded_mid_run_doesnt_let_its_supports_count(
    platform: Platform,  # noqa: F811
) -> None:
    """The receipt is stored after the run read, so it isn't new evidence the run saw:
    the supports over its own unsure waits for the accountant."""
    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    first: list[Record] = []

    def behave(i: AgentInput) -> AgentResult:
        if not first:
            first.append(_answer(i, charge, "unsure"))
            return AgentResult(records=[first[0]])
        if i.run.trigger.kind != TriggerKind.CHARGE:
            return AgentResult()  # the receipt's own run
        upload = actions.Upload("receipt.txt", "text/plain", b"Paid.")
        actions.add_evidence(platform, grant, upload)  # stored after this run read
        return AgentResult(records=[_answer(i, charge, "supports", replaces=first[0].id)])

    agent.behave = behave
    grant, charge = _frozen_grant(platform)
    run_worker_until_idle(str(platform.pool.conninfo))
    with transaction(platform.pool) as conn:
        queue_run(conn, grant, Trigger(kind=TriggerKind.CHARGE, id=charge.id), first[0].written_at)
    run_worker_until_idle(str(platform.pool.conninfo))
    judgments, state = _judgments(platform, grant)
    unsure, supports = judgments[:2]
    assert state.is_waiting(supports.id)  # pyright: ignore[reportAttributeAccessIssue]
    assert state.is_current(unsure.id)  # pyright: ignore[reportAttributeAccessIssue]


def test_the_read_point_counts_only_what_the_run_was_given(
    platform: Platform,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reviewer's hold: between reading the files and reading the records, a receipt is
    uploaded and an accountant record written. The run reads one snapshot, so neither is
    given to it, and its read point stays below both."""
    from datetime import UTC, datetime

    agent = platform.agent
    assert isinstance(agent, FakeAgent)
    grant = _grant(platform)
    real = store.list_files
    held: list[int] = []

    def hold(conn: object, grant_id: str, now: object) -> object:
        files = real(conn, grant_id, now)  # pyright: ignore[reportArgumentType]
        if not held:
            held.append(1)
            upload = actions.Upload("receipt.txt", "text/plain", b"Paid.")
            actions.add_evidence(platform, grant, upload)
            actions.add_record(
                platform,
                grant,
                _user_id(platform, grant),
                {"kind": "other_term", "label": "Note", "statement": {"value": "Look."}},
                None,
            )
        return files

    monkeypatch.setattr(store, "list_files", hold)
    run_worker_until_idle(str(platform.pool.conninfo))
    first = agent.inputs[0]
    assert [f.name for f in first.files] == ["invoice.txt"]
    assert not any(r.kind == "other_term" for r in first.records)
    with transaction(platform.pool) as conn:
        receipt = next(
            f
            for f in real(conn, grant.id, datetime.max.replace(tzinfo=UTC))
            if f.name == "receipt.txt"
        )
    assert first.run.read_through_seq is not None and receipt.stored_seq is not None
    assert first.run.read_through_seq < receipt.stored_seq
