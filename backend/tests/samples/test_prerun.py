"""The prerun (decision 0027, ruling 47, first version), with the agent faked by the
sample's own agent_records.json. The command itself makes paid calls and never runs here."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, LiteralString

import pytest

from app.agent.model import ModelRequest
from app.contracts.records import Author, Record
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import SampleChoice
from app.db import sample_store, store
from app.db.pool import transaction
from app.db.ports import AgentInput, AgentResult, ModuleChecks
from app.samples import player, prerun
from app.samples.pack import DATA_DIR, LARGER_SAMPLE, UserAction
from app.samples.script import WriteRecord, resolve
from tests.api.conftest import Api
from tests.db.platform_fixtures import FakeAgent, run_worker_until_idle

from .plays import Mapping, _mapped, _pointed_first
from .test_player import _get, _open, _post, _workspace
from .test_skipping import SMALL, _iso

LOG = {
    "events": [{"event": "response"}, {"event": "tool"}, {"event": "response"}],
    "usage": {
        "input_tokens": 1000,
        "output_tokens": 200,
        "cache_read_input_tokens": 5000,
        "cache_creation_input_tokens": 0,
    },
}


@pytest.fixture
def setup(api: Api, monkeypatch: pytest.MonkeyPatch) -> Api:
    """Real checks, the user's row, and the prerun choice opening the small sample (so a
    test plays a short timeline)."""
    api.platform.checks = ModuleChecks()
    _get(api, "/samples")  # the API stores the signed-in user
    monkeypatch.setitem(player.PACK_FOR_CHOICE, SampleChoice.LARGER_PRERUN, SMALL)
    monkeypatch.setitem(player.PACK_FOR_CHOICE, SampleChoice.LARGER_EXPECTED, SMALL)
    with transaction(api.platform.pool) as conn:  # the database is shared across tests
        conn.execute("update public.sample_preruns set released = false")
    return api


def _logged(api: Api) -> None:
    """Each run also leaves a debug log with two model calls."""
    agent = api.platform.agent
    assert isinstance(agent, FakeAgent)
    behave = agent.behave

    def with_log(i: AgentInput) -> AgentResult:
        result = behave(i)
        return replace(result, log=json.dumps(LOG).encode())

    agent.behave = with_log


def _reading_agent(api: Api, sample: str = SMALL, *, posts: bool = False) -> None:
    """The agent, faked by agent_records.json: a run writes the records of its time that
    aren't on its grant yet, mapped onto whichever grant it runs on. With `posts`, it also
    posts in the thread of the first record it writes."""
    pack = player.pack_for(sample)
    raw = json.loads((pack.folder / "agent_records.json").read_text())["records"]
    mappings: dict[str, Mapping] = {}
    agent = api.platform.agent
    assert isinstance(agent, FakeAgent)

    def behave(i: AgentInput) -> AgentResult:
        mapping = mappings.setdefault(i.grant.id, Mapping(pack, i.grant))
        with transaction(api.platform.pool) as conn:
            on_grant = {r.id for r in store.list_records(conn, i.grant.id)}
            due = [
                r
                for r in raw
                if r["written_at"] == _iso(i.run.clock_now)
                and mapping.records.get(r["id"]) not in on_grant
            ]
            records = [
                Record.model_validate(_mapped(r, lambda v: mapping(conn, v))).model_copy(
                    update={"read_through_seq": i.run.read_through_seq}
                )
                for r in _pointed_first(due)
            ]
        messages = []
        if posts and records:
            messages = [
                ThreadMessage(
                    id=str(uuid.uuid4()),
                    workspace_id=i.grant.workspace_id,
                    grant_id=i.grant.id,
                    record_id=records[0].id,
                    author=Author.AGENT,
                    run_id=i.run.id,
                    text="Read from the award letter.",
                    written_at=i.run.clock_now,
                )
            ]
        return AgentResult(records=records, messages=messages)

    agent.behave = behave


def _drain(api: Api) -> Any:
    return lambda queue: prerun.drain_jobs(str(api.platform.pool.conninfo), queue)


def _make(
    api: Api, *, read: bool = True, sample: str = SMALL, posts: bool = False
) -> prerun.Prerun:
    """A prerun of the sample, the agent reading from agent_records.json (or nothing)."""
    if read:
        _reading_agent(api, sample, posts=posts)
    _logged(api)
    return prerun.make(api.platform, sample, api.user_id, drain=_drain(api))


# The version.


def test_the_version_changes_with_the_sample(tmp_path: Path) -> None:
    assert prerun.version(SMALL) == prerun.version(SMALL)
    copy = tmp_path / "samples" / SMALL
    shutil.copytree(DATA_DIR / "samples" / SMALL, copy)
    assert prerun.version(SMALL, tmp_path) == prerun.version(SMALL)
    (copy / "timeline.json").write_text((copy / "timeline.json").read_text() + "\n")
    assert prerun.version(SMALL, tmp_path) != prerun.version(SMALL)


@pytest.mark.parametrize("changed", ["prompts.py", "tools.py", "model.py", "rulebooks"])
def test_the_version_changes_with_the_agent(tmp_path: Path, changed: str) -> None:
    """The prompts, the tool definitions, the effort and turn limits, the rulebooks."""
    agent = tmp_path / "agent"
    shutil.copytree(prerun.AGENT_DIR, agent, ignore=shutil.ignore_patterns("__pycache__"))
    assert prerun.version(SMALL, agent_dir=agent) == prerun.version(SMALL)
    target = agent / changed
    if target.is_dir():
        target = next(p for p in sorted(target.rglob("*")) if p.is_file())
    target.write_bytes(target.read_bytes() + b"\n# changed\n")
    assert prerun.version(SMALL, agent_dir=agent) != prerun.version(SMALL)


def test_the_version_changes_with_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agent import model

    before = prerun.version(SMALL)
    monkeypatch.setattr(model, "MODEL", "another-model")
    assert prerun.version(SMALL) != before


# Making one.


def _seeding(api: Api, made: prerun.Prerun) -> str:
    with transaction(api.platform.pool) as conn:
        grant = store.get_grant(conn, made.grant_id)
    assert grant is not None
    return grant.workspace_id


def test_a_prerun_is_made_checked_and_released(setup: Api) -> None:
    api = setup
    made = _make(api)
    key = json.loads((player.pack_for(SMALL).folder / "answer_key.json").read_text())
    assert made.checked == len(key["buckets"]) and made.wrong == []
    assert not made.released
    assert made.version == prerun.version(SMALL)
    # Two model calls per run's log, and their cost at the list prices.
    runs = made.usage["runs"]
    assert runs > 0 and made.usage["calls"] == 2 * runs
    assert made.usage["input_tokens"] == 1000 * runs
    expected = runs * (1000 * 4.00 + 200 * 20.00 + 5000 * 0.20) / 1_000_000
    assert made.usage["cost_dollars"] == round(expected, 2)
    with transaction(api.platform.pool) as conn:
        assert prerun.current(conn, SMALL) is None
    released = prerun.release(api.platform, made.id)
    assert released.released
    with transaction(api.platform.pool) as conn:
        found = prerun.current(conn, SMALL)
    assert found is not None and found.id == made.id
    report = prerun._report(released)  # pyright: ignore[reportPrivateUsage]
    assert "cost: $" in report and "estimate" in report and "model calls" in report


def test_no_person_can_reach_the_seeding_workspace(setup: Api) -> None:
    api = setup
    made = _make(api)
    workspace_id = _seeding(api, made)
    with transaction(api.platform.pool) as conn:
        assert workspace_id not in {w.id for w in store.list_workspaces(conn, api.user_id)}
        members = conn.execute(
            "select role from public.workspace_members where workspace_id = %s", (workspace_id,)
        ).fetchall()
    assert [m["role"] for m in members] == ["sample"]
    assert (
        api.client.get(f"/grants/{made.grant_id}/timeline", headers=api.headers).status_code == 404
    )
    assert (
        api.client.get(f"/workspaces/{workspace_id}/grants", headers=api.headers).status_code == 404
    )


def _app_worker_once(api: Api) -> None:
    """One pass of a worker on the app's queue, as the app's own worker would run."""
    import asyncio

    from app.db.jobs import QUEUE
    from app.db.worker import open_worker_app

    async def go() -> None:
        async with open_worker_app(str(api.platform.pool.conninfo)) as app:
            await app.run_worker_async(
                queues=[QUEUE], wait=False, listen_notify=False, install_signal_handlers=False
            )

    asyncio.run(go())


def test_the_seeding_runs_go_on_a_queue_only_the_command_takes(setup: Api) -> None:
    """The app's worker never runs them; the command's worker runs only them."""
    api = setup
    _reading_agent(api)
    seen: dict[str, Any] = {}

    def drain(queue: str) -> None:
        with transaction(api.platform.pool) as conn:
            seen["queues"] = {
                r["queue_name"]
                for r in conn.execute(
                    "select queue_name from procrastinate_jobs where status = 'todo'"
                ).fetchall()
            }
        _app_worker_once(api)
        with transaction(api.platform.pool) as conn:
            seen["left"] = conn.execute(
                "select count(*) as n from procrastinate_jobs where queue_name = %s"
                " and status = 'todo'",
                (queue,),
            ).fetchone()["n"]  # type: ignore[index]
        seen["queue"] = queue
        prerun.drain_jobs(str(api.platform.pool.conninfo), queue)

    made = prerun.make(api.platform, SMALL, api.user_id, drain=drain)
    assert seen["queues"] == {seen["queue"]} and seen["queue"] != "agent"
    assert seen["left"] > 0  # the app's worker left them alone
    assert made.wrong == []


def test_a_command_that_stops_stops_its_play(setup: Api) -> None:
    """Interrupted while the agent reads: the walk stops for good and its jobs go, so
    nothing goes on; cleanup then removes the workspace."""
    api = setup

    def interrupted(_queue: str) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        prerun.make(api.platform, SMALL, api.user_id, drain=interrupted)
    with transaction(api.platform.pool) as conn:
        row = conn.execute(
            """select s.workspace_id, s.queue from public.sample_seeding s
               where not exists (select 1 from public.sample_preruns r
                 join public.grants g on g.id = r.grant_id where g.workspace_id = s.workspace_id)
               order by s.workspace_id"""
        ).fetchall()
    assert row
    workspace_id, queue = row[-1]["workspace_id"], row[-1]["queue"]
    with transaction(api.platform.pool) as conn:
        [grant] = store.list_grants(conn, workspace_id)
        assert sample_store.walk_target(conn, grant.id) is None
        assert sample_store.last_move(conn, grant.id).walk_stopped  # type: ignore[union-attr]
        left = conn.execute(
            "select count(*) as n from procrastinate_jobs where queue_name = %s", (queue,)
        ).fetchone()
    assert left is not None and left["n"] == 0
    with transaction(api.platform.pool) as conn:
        stored = [f.storage_path for f in store.list_files(conn, grant.id, store.END_OF_TIME)]
    assert stored and all(path in api.platform.storage.objects for path in stored)  # type: ignore[attr-defined]
    assert workspace_id in prerun.cleanup(api.platform)
    with transaction(api.platform.pool) as conn:
        assert store.get_grant(conn, grant.id) is None
    assert not any(path in api.platform.storage.objects for path in stored)  # type: ignore[attr-defined]


# The spend cap.


def _call_with(budget: prerun.Budget, inner: Any) -> Any:
    model = prerun.CappedModel(inner, budget)
    return model(
        ModelRequest(
            system=[], tools=[], messages=[{"role": "user", "content": "x"}], max_tokens=1000
        )
    )


def _usage(input_tokens: int, output_tokens: int) -> Any:
    return SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
    )


def test_no_model_call_starts_that_could_pass_the_cap() -> None:
    """Each call costs $0.014 and could cost up to about $0.02: with a $0.05 cap, three
    calls are made ($0.042) and the fourth is refused before it's made."""
    budget = prerun.Budget(cap=0.05)
    made: list[int] = []

    def inner(_request: Any) -> Any:
        made.append(1)
        return _usage(1000, 500)

    for _ in range(3):
        _call_with(budget, inner)
    assert not budget.stopped
    with pytest.raises(prerun.SpendCapReached, match="spend cap"):
        _call_with(budget, inner)
    assert len(made) == 3 and budget.stopped
    assert budget.spent == pytest.approx(0.042) and budget.spent <= budget.cap
    assert budget.totals()["calls"] == 3 and budget.totals()["output_tokens"] == 1500


def test_a_call_that_raises_counts_its_worst_case() -> None:
    """It may have been billed: its whole worst case counts as spent."""
    budget = prerun.Budget(cap=1.0)

    def broken(_request: Any) -> Any:
        raise ConnectionError("the connection dropped")

    with pytest.raises(ConnectionError):
        _call_with(budget, broken)
    assert budget.failed_calls == 1 and budget.spent == pytest.approx(0.02, abs=0.001)
    assert budget.held == 0


def test_a_call_dearer_than_its_worst_case_stops_the_budget() -> None:
    """The estimate can't be trusted once it's been wrong: no further call starts."""
    budget = prerun.Budget(cap=10.0)
    _call_with(budget, lambda _r: _usage(1000, 5000))  # $0.104, past its ~$0.02 worst case
    with pytest.raises(prerun.SpendCapReached, match="worst case"):
        _call_with(budget, lambda _r: _usage(10, 10))
    assert budget.stopped and budget.calls == 1


def test_the_cap_stops_a_run_partway_and_the_prerun_isnt_released(setup: Api) -> None:
    """One run's calls cost more than the whole cap: the run stops at the call that could
    pass it, fails, and the prerun can't be released. Every call is counted."""
    api = setup
    budget = prerun.Budget(cap=0.05)
    agent = api.platform.agent
    assert isinstance(agent, FakeAgent)

    def behave(_i: AgentInput) -> AgentResult:
        for _ in range(5):  # a run of five calls: $0.07
            _call_with(budget, lambda _r: _usage(1000, 500))
        return AgentResult()

    agent.behave = behave
    made = prerun.make(api.platform, SMALL, api.user_id, drain=_drain(api), budget=budget)
    assert budget.spent <= 0.05 and made.usage["stopped_at_cap"] is True
    assert made.usage["all_calls"]["calls"] == budget.calls
    with transaction(api.platform.pool) as conn:
        runs = store.list_runs(conn, made.grant_id)
    assert any("spend cap" in (r.error or "") for r in runs)
    with pytest.raises(prerun.NotReleasable, match="spend cap"):
        prerun.release(api.platform, made.id)
    report = prerun._report(made)  # pyright: ignore[reportPrivateUsage]
    assert "stopped at the spend cap" in report and "every model call" in report


# The release gate.


def test_a_prerun_that_doesnt_match_isnt_released(setup: Api) -> None:
    made = _make(setup, read=False)  # the agent reads nothing: no bucket holds
    assert made.wrong
    with pytest.raises(prerun.NotReleasable, match="expected results"):
        prerun.release(setup.platform, made.id)


def test_a_prerun_whose_walk_left_a_step_isnt_released(
    setup: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.samples import skipping

    def fails(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("the write broke")

    monkeypatch.setattr(skipping, "write_record", fails)
    made = _make(setup)
    assert any("was left" in w for w in made.wrong)
    with pytest.raises(prerun.NotReleasable):
        prerun.release(setup.platform, made.id)


def test_a_prerun_with_a_failed_run_isnt_released(setup: Api) -> None:
    api = setup
    _reading_agent(api)
    agent = api.platform.agent
    assert isinstance(agent, FakeAgent)
    reads = agent.behave
    failed: list[str] = []

    class Refused(Exception):
        retryable = False
        log = None

    def behave(i: AgentInput) -> AgentResult:
        if not failed and i.run.trigger.kind.value == "charge":
            failed.append(i.run.id)
            raise Refused("the model refused")
        return reads(i)

    agent.behave = behave
    made = prerun.make(api.platform, SMALL, api.user_id, drain=_drain(api))
    assert any("failed: Refused" in w for w in made.wrong)
    with pytest.raises(prerun.NotReleasable):
        prerun.release(api.platform, made.id)


def test_the_prerun_choice_opens_only_once_released(setup: Api) -> None:
    api = setup
    options = {o["choice"]: o for o in _get(api, "/samples")}
    assert options["larger_prerun"]["available"] is False
    workspace_id = _workspace(api)
    refused = _post(api, f"/workspaces/{workspace_id}/samples", {"choice": "larger_prerun"})
    assert refused.status_code == 422
    prerun.release(api.platform, _make(api).id)
    options = {o["choice"]: o for o in _get(api, "/samples")}
    assert options["larger_prerun"]["available"] is True


# Loading.


def _released(api: Api, **make: Any) -> prerun.Prerun:
    saved = prerun.release(api.platform, _make(api, **make).id)
    agent = api.platform.agent
    assert isinstance(agent, FakeAgent)
    agent.behave = lambda _i: AgentResult()  # from here, a live run writes nothing
    return saved


def _counts(api: Api, grant_id: str) -> tuple[int, int, int]:
    with transaction(api.platform.pool) as conn:
        return (
            len(store.list_files(conn, grant_id, store.END_OF_TIME)),
            len(store.list_charges(conn, grant_id, store.END_OF_TIME)),
            len(store.list_records(conn, grant_id)),
        )


def _pending(api: Api, grant_id: str) -> int:
    with transaction(api.platform.pool) as conn:
        return sample_store.catch_up_runs_pending(conn, grant_id)


def _to_the_end(api: Api, grant_id: str, sample: str = SMALL) -> Any:
    end = max(i.at for i in player.items_for(sample)) + timedelta(days=1)
    moved = _post(api, f"/grants/{grant_id}/timeline", {"to": _iso(end), "skip_human_steps": True})
    assert moved.status_code == 200, moved.text
    return moved.json()


def _rows(api: Api, grant_id: str) -> dict[str, list[dict[str, Any]]]:
    """Every row a load copies onto the grant, as stored."""
    tables: dict[str, LiteralString] = {
        "records": "select * from public.records where grant_id = %s",
        "files": "select * from public.evidence_files where grant_id = %s",
        "charges": "select * from public.charges where grant_id = %s",
        "held": "select * from public.held_mail where grant_id = %s",
        "runs": "select * from public.agent_runs where grant_id = %s",
        "messages": "select * from public.thread_messages where grant_id = %s",
        "scripted": "select * from public.sample_scripted where grant_id = %s",
    }
    with transaction(api.platform.pool) as conn:
        return {k: conn.execute(q, (grant_id,)).fetchall() for k, q in tables.items()}


def _ids(rows: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {str(r["id"]) for k, v in rows.items() if k != "scripted" for r in v}


def _no_seeding_ids(api: Api, saved: prerun.Prerun, grant_id: str) -> None:
    """No copied row mentions the seeding workspace, grant, or any of its rows, anywhere."""
    seeding = _ids(_rows(api, saved.grant_id)) | {saved.grant_id, _seeding(api, saved)}
    text = json.dumps(_rows(api, grant_id), default=str)
    leaked = sorted(i for i in seeding if i in text)
    assert leaked == []


def test_a_prerun_grant_loads_the_saved_result_while_on_the_run_through(setup: Api) -> None:
    api = setup
    saved = _released(api, posts=True)
    grant_id = _open(api, "larger_prerun")
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert timeline["on_run_through"] is True
    assert [p["loaded"] for p in timeline["just_happened"]] == [True]
    assert _pending(api, grant_id) == 0  # nothing runs: the agent's work was done ahead

    moved = _to_the_end(api, grant_id)
    assert moved["on_run_through"] is True
    assert all(p["loaded"] for p in moved["just_happened"])
    assert _pending(api, grant_id) == 0
    assert _counts(api, grant_id) == _counts(api, saved.grant_id)
    # The agent's thread messages too, under the copied runs.
    copied, source = _rows(api, grant_id), _rows(api, saved.grant_id)
    assert len(copied["messages"]) == len(source["messages"]) > 0
    run_ids = {r["id"] for r in copied["runs"]}
    assert all(m["run_id"] in run_ids for m in copied["messages"])
    _no_seeding_ids(api, saved, grant_id)

    # Decisions are this workspace's Sample accountant's, listed under the move.
    with transaction(api.platform.pool) as conn:
        grant = store.get_grant(conn, grant_id)
        assert grant is not None
        accountant = store.sample_accountant_id(conn, grant.workspace_id)
        users = {
            r.author_user_id for r in store.list_records(conn, grant_id) if r.author == Author.USER
        }
    assert users == {accountant}
    shown = [d for p in moved["just_happened"] for d in p["scripted_decisions"]]
    assert shown  # the confirmation of the letter's terms
    # The copy gives the expected results, as the prerun did.
    checked, wrong = prerun.key_check(api.platform, grant_id, SMALL)
    assert checked and wrong == []


def test_two_users_loading_one_prerun_share_no_row(setup: Api) -> None:
    api = setup
    _released(api)
    first, second = _open(api, "larger_prerun"), _open(api, "larger_prerun")
    _to_the_end(api, first)
    _to_the_end(api, second)
    assert _ids(_rows(api, first)) and not _ids(_rows(api, first)) & _ids(_rows(api, second))


def test_the_sign_off_is_never_loaded(setup: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """The user always signs off themselves (ruling 77): the prerun signed off, a grant
    loading it past that point doesn't get the sign-off, its report or its snapshot."""
    api = setup
    pack = player.pack_for(SMALL)
    sign = UserAction(
        at=max(e.at for e in pack.events) + timedelta(hours=1),
        action="sign_off",
        note="Signed by the script.",
    )
    monkeypatch.setattr(player, "pack_for", lambda _s: replace(pack, actions=(*pack.actions, sign)))
    saved = _released(api)
    with transaction(api.platform.pool) as conn:
        kinds = [r.kind.value for r in store.list_records(conn, saved.grant_id)]
    assert "sign_off" in kinds
    grant_id = _open(api, "larger_prerun")
    moved = _to_the_end(api, grant_id)
    assert moved["on_run_through"] is True
    with transaction(api.platform.pool) as conn:
        loaded = [r.kind.value for r in store.list_records(conn, grant_id)]
    assert "sign_off" not in loaded and len(loaded) == len(kinds) - 1
    _no_seeding_ids(api, saved, grant_id)


def test_the_larger_sample_loads_whole(setup: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """Made from the larger sample's agent_records.json and loaded to the end: the same
    files, charges and records (but the sign-off), no seeding ID, and the key holds."""
    api = setup
    monkeypatch.setitem(player.PACK_FOR_CHOICE, SampleChoice.LARGER_PRERUN, LARGER_SAMPLE)
    saved = _released(api, sample=LARGER_SAMPLE)
    assert saved.wrong == []
    grant_id = _open(api, "larger_prerun")
    moved = _to_the_end(api, grant_id, LARGER_SAMPLE)
    assert moved["on_run_through"] is True and _pending(api, grant_id) == 0
    files, charges, records = _counts(api, saved.grant_id)
    assert _counts(api, grant_id) == (files, charges, records - 1)  # no sign-off
    copied, source = _rows(api, grant_id), _rows(api, saved.grant_id)
    assert len(copied["runs"]) == len(source["runs"])
    assert len(copied["held"]) == len(source["held"])
    _no_seeding_ids(api, saved, grant_id)
    checked, wrong = prerun.key_check(api.platform, grant_id, LARGER_SAMPLE)
    assert checked and wrong == []


# Off the run-through.


def test_a_users_decision_takes_it_off_the_run_through(setup: Api) -> None:
    api = setup
    _released(api)
    grant_id = _open(api, "larger_prerun")
    added = _post(
        api,
        f"/grants/{grant_id}/records",
        {
            "data": {
                "kind": "person",
                "name": {"value": "Pat", "text": "Pat"},
                "email": {"value": "pat@university.example", "text": "pat@university.example"},
                "role": {"value": "Known sender", "text": "Known sender"},
            }
        },
    )
    assert added.status_code == 201, added.text
    moved = _post(api, f"/grants/{grant_id}/timeline", {}).json()
    assert moved["on_run_through"] is False
    assert not any(p["loaded"] for p in moved["just_happened"])
    assert _pending(api, grant_id) > 0  # the agent works live from here


def _upload(api: Api, grant_id: str) -> Any:
    return api.client.post(
        f"/grants/{grant_id}/evidence",
        files={"file": ("note.txt", b"A synthetic note.", "text/plain")},
        headers=api.headers,
    )


def _ledger(api: Api, grant_id: str) -> Any:
    return api.client.post(
        f"/grants/{grant_id}/ledger",
        files={"file": ("ledger.csv", player.pack_for(SMALL).ledger_bytes(), "text/csv")},
        headers=api.headers,
    )


def _ask(api: Api, grant_id: str) -> Any:
    with transaction(api.platform.pool) as conn:
        record = store.list_records(conn, grant_id)[0]
    return _post(api, f"/records/{record.id}/thread", {"text": "Where does this come from?"})


@pytest.mark.parametrize("act", [_upload, _ledger, _ask])
def test_anything_a_user_does_takes_it_off_the_run_through(setup: Api, act: Any) -> None:
    """An upload the script doesn't make, a ledger upload or a thread question: the grant
    goes live, and the next move loads nothing on top of it."""
    api = setup
    saved = _released(api)
    grant_id = _open(api, "larger_prerun")
    done = act(api, grant_id)
    assert done.status_code in (200, 201), done.text
    assert _get(api, f"/grants/{grant_id}/timeline")["on_run_through"] is False
    moved = _to_the_end(api, grant_id)
    assert moved["on_run_through"] is False
    assert not any(p["loaded"] for p in moved["just_happened"])
    run_worker_until_idle(str(api.platform.pool.conninfo))
    files = {f.sha256 for f in _rows_files(api, grant_id)}
    assert len(files) == len(_rows_files(api, grant_id)) or act is _upload
    assert saved.grant_id != grant_id


def _rows_files(api: Api, grant_id: str) -> list[Any]:
    with transaction(api.platform.pool) as conn:
        return store.list_files(conn, grant_id, store.END_OF_TIME)


def test_passing_a_scripted_step_without_skipping_takes_it_off(setup: Api) -> None:
    api = setup
    _released(api)
    grant_id = _open(api, "larger_prerun")
    confirm = next(a for a in player.pack_for(SMALL).actions if a.action == "confirm_terms")
    moved = _post(
        api, f"/grants/{grant_id}/timeline", {"to": _iso(confirm.at + timedelta(minutes=1))}
    ).json()
    assert moved["on_run_through"] is False


def test_a_move_before_any_scripted_step_stays_on(setup: Api) -> None:
    api = setup
    _released(api)
    grant_id = _open(api, "larger_prerun")
    confirm = next(a for a in player.pack_for(SMALL).actions if a.action == "confirm_terms")
    moved = _post(
        api, f"/grants/{grant_id}/timeline", {"to": _iso(confirm.at - timedelta(minutes=1))}
    ).json()
    assert moved["on_run_through"] is True


def test_a_withdrawn_prerun_stops_loading(setup: Api) -> None:
    """A grant on the run-through of a prerun that's no longer released (or not at the
    current version) goes live: the view says so, and the next move loads nothing."""
    api = setup
    saved = _released(api)
    grant_id = _open(api, "larger_prerun")
    with transaction(api.platform.pool) as conn:
        conn.execute("update public.sample_preruns set released = false where id = %s", (saved.id,))
    assert _get(api, f"/grants/{grant_id}/timeline")["on_run_through"] is False
    moved = _to_the_end(api, grant_id)
    assert not any(p["loaded"] for p in moved["just_happened"])


def test_starting_over_puts_it_back_on_the_run_through(setup: Api) -> None:
    api = setup
    _released(api)
    grant_id = _open(api, "larger_prerun")
    confirm = next(a for a in player.pack_for(SMALL).actions if a.action == "confirm_terms")
    _post(api, f"/grants/{grant_id}/timeline", {"to": _iso(confirm.at + timedelta(minutes=1))})
    response = _post(api, f"/grants/{grant_id}/timeline/start-over", {"confirmed": True})
    assert response.status_code == 200, response.text
    timeline = response.json()
    assert timeline["on_run_through"] is True
    assert [p["loaded"] for p in timeline["just_happened"]] == [True]


# The command.


def test_the_command_needs_a_spend_cap() -> None:
    with pytest.raises(SystemExit) as stopped:
        prerun.main(["make", "salt-marsh-carbon", "--owner", "someone"])
    assert stopped.value.code == 2  # argparse: --cap is required


def _env(monkeypatch: pytest.MonkeyPatch, database: str, supabase: str) -> None:
    monkeypatch.setenv("DATABASE_URL", database)
    monkeypatch.setenv("SUPABASE_URL", supabase)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "not-a-real-key")


def test_the_command_refuses_a_database_that_isnt_on_this_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env(monkeypatch, "postgresql://u:p@db.hosted.example:5432/postgres", "http://127.0.0.1:54321")
    with pytest.raises(SystemExit, match="DATABASE_URL points at db.hosted.example"):
        prerun.main(["make", "salt-marsh-carbon", "--owner", "someone", "--cap", "1"])
    _env(monkeypatch, "postgresql://u:p@127.0.0.1:54322/postgres", "https://project.hosted.example")
    with pytest.raises(SystemExit, match="--allow-remote"):
        prerun.main(["release", "some-prerun"])


def test_the_command_needs_its_targets_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:54322/postgres")
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
    with pytest.raises(SystemExit, match="SUPABASE_SERVICE_ROLE_KEY isn't set"):
        prerun.main(["cleanup"])


# A user's own step that matches the script (ruling 80).


def _scripted_write(api: Api, grant_id: str, action: str) -> Any:
    """The write the script's step would make on the grant now."""
    pack = player.pack_for(SMALL)
    step = next(a for a in pack.actions if a.action == action)
    with transaction(api.platform.pool) as conn:
        grant = store.get_grant(conn, grant_id)
        assert grant is not None
        found = resolve(api.platform, conn, grant, pack, step, prerun_clock(conn, grant_id))
    assert isinstance(found, WriteRecord)
    return found


def prerun_clock(conn: Any, grant_id: str) -> Any:
    from app.db import clock

    return clock.grant_now(conn, grant_id)


def _confirmations(api: Api, grant_id: str) -> list[Record]:
    with transaction(api.platform.pool) as conn:
        return [r for r in store.list_records(conn, grant_id) if r.kind.value == "confirmation"]


def test_confirming_as_read_keeps_it_on_and_the_next_highlight_loads_at_once(
    setup: Api,
) -> None:
    """Highlight 1, path 1: the user confirms the letter's terms as the script would. The
    grant stays on the run-through; the confirmation is the user's own; Next highlight
    then loads at once, and what rests on the confirmation points at the user's record."""
    api = setup
    saved = _released(api)
    grant_id = _open(api, "larger_prerun")
    write = _scripted_write(api, grant_id, "confirm_terms")
    # The same terms, listed in another order.
    data = {**write.data, "record_ids": list(reversed(write.data["record_ids"]))}
    mine = _post(api, f"/grants/{grant_id}/records", {"data": data})
    assert mine.status_code == 201, mine.text
    assert _get(api, f"/grants/{grant_id}/timeline")["on_run_through"] is True
    assert _pending(api, grant_id) == 0  # nothing runs live for it

    moved = _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True})
    assert moved.status_code == 200, moved.text
    timeline = moved.json()
    assert timeline["on_run_through"] is True and _pending(api, grant_id) == 0
    assert timeline["just_happened"] and all(p["loaded"] for p in timeline["just_happened"])
    # One confirmation, the user's: none of the script's is copied over it, and no
    # decision is shown as the sample accountant's that the user made.
    [confirmation] = _confirmations(api, grant_id)
    assert confirmation.id == mine.json()["id"] and confirmation.author_user_id == api.user_id
    shown = [d["id"] for p in timeline["just_happened"] for d in p["scripted_decisions"]]
    assert confirmation.id not in shown
    _to_the_end(api, grant_id)
    assert _counts(api, grant_id) == _counts(api, saved.grant_id)
    _no_seeding_ids(api, saved, grant_id)
    checked, wrong = prerun.key_check(api.platform, grant_id, SMALL)
    assert checked and wrong == []


def test_changing_a_term_before_confirming_goes_live(setup: Api) -> None:
    """Highlight 1, path 2: the user changes one of the terms the letter was read for: a
    decision the script doesn't make. The grant goes live, and the panel says so."""
    api = setup
    _released(api)
    grant_id = _open(api, "larger_prerun")
    with transaction(api.platform.pool) as conn:
        term = next(
            r
            for r in store.list_records(conn, grant_id)
            if r.author == Author.AGENT and r.kind.value == "period_of_performance"
        )
    data = term.data.model_dump(mode="json")
    end = date.fromisoformat(data["end"]["value"]) + timedelta(days=1)
    data["end"]["value"] = end.isoformat()  # one day later than the letter says
    changed = _post(api, f"/grants/{grant_id}/records", {"data": data, "replaces_id": term.id})
    assert changed.status_code == 201, changed.text
    assert _get(api, f"/grants/{grant_id}/timeline")["on_run_through"] is False
    moved = _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True}).json()
    assert moved["on_run_through"] is False
    assert not any(p["loaded"] for p in moved["just_happened"])


def test_moving_on_without_confirming_skipping_off_goes_live(setup: Api) -> None:
    """Highlight 1, path 3: the user moves past the confirmation's time without making it
    and without skipping. The grant goes live for good."""
    api = setup
    _released(api)
    grant_id = _open(api, "larger_prerun")
    confirm = next(a for a in player.pack_for(SMALL).actions if a.action == "confirm_terms")
    moved = _post(
        api, f"/grants/{grant_id}/timeline", {"to": _iso(confirm.at + timedelta(minutes=1))}
    ).json()
    assert moved["on_run_through"] is False
    later = _to_the_end(api, grant_id)
    assert later["on_run_through"] is False
    assert not any(p["loaded"] for p in later["just_happened"])


def test_delivering_the_scripted_file_keeps_it_on(setup: Api) -> None:
    """Deliver for me of the file the script delivers, before its time: the user's file
    stands for the prerun's, nothing runs live for it, and loading points the prerun's
    reading of it at the user's file."""
    api = setup
    saved = _released(api)
    grant_id = _open(api, "larger_prerun")
    write = _scripted_write(api, grant_id, "confirm_terms")
    assert _post(api, f"/grants/{grant_id}/records", {"data": write.data}).status_code == 201
    receipt = next(e for e in player.pack_for(SMALL).events if e.deliver_by_user)
    delivered = _post(api, f"/grants/{grant_id}/timeline/deliveries/{receipt.id}", {})
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["on_run_through"] is True and _pending(api, grant_id) == 0
    _to_the_end(api, grant_id)
    assert _counts(api, grant_id) == _counts(api, saved.grant_id)
    with transaction(api.platform.pool) as conn:
        files = store.list_files(conn, grant_id, store.END_OF_TIME)
        runs = store.list_runs(conn, grant_id)
    sha = player.pack_for(SMALL).sha256(receipt.name)
    [mine] = [f for f in files if f.sha256 == sha]
    assert any(r.trigger.id == mine.id for r in runs)  # the prerun's reading, pointed at it
    _no_seeding_ids(api, saved, grant_id)


def _marked(monkeypatch: pytest.MonkeyPatch) -> str:
    """The small sample with its receipt delivery marked as the receipt highlight's own
    step (built here, not in data/). Returns the receipt's event name."""
    pack = player.pack_for(SMALL)
    receipt = next(e for e in pack.events if e.deliver_by_user)
    actions = tuple(
        replace(a, highlight=receipt.highlight) if a.action == "deliver_file" else a
        for a in pack.actions
    )
    monkeypatch.setattr(player, "pack_for", lambda _s: replace(pack, actions=actions))
    return receipt.name


def _to_highlight_2(api: Api, grant_id: str) -> Any:
    """From highlight 1, confirmed as read, Next highlight to the receipt."""
    write = _scripted_write(api, grant_id, "confirm_terms")
    assert _post(api, f"/grants/{grant_id}/records", {"data": write.data}).status_code == 201
    moved = _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True})
    assert moved.status_code == 200, moved.text
    return moved.json()


def test_next_highlight_on_the_run_through_holds_its_own_step(
    setup: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The receipt's delivery waits for the user; the user delivers it, and the grant
    stays on. A later skipping move loads the rest."""
    api = setup
    name = _marked(monkeypatch)
    saved = _released(api)
    grant_id = _open(api, "larger_prerun")
    timeline = _to_highlight_2(api, grant_id)
    assert timeline["on_run_through"] is True
    assert [d["event"]["name"] for d in timeline["now"]["deliveries"]] == [name]
    receipt = next(e for e in player.pack_for(SMALL).events if e.name == name)
    delivered = _post(api, f"/grants/{grant_id}/timeline/deliveries/{receipt.id}", {})
    assert delivered.json()["on_run_through"] is True
    _to_the_end(api, grant_id)
    assert _counts(api, grant_id) == _counts(api, saved.grant_id)
    _no_seeding_ids(api, saved, grant_id)


def test_skipping_on_past_a_held_step_has_the_accountant_make_it(
    setup: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = setup
    name = _marked(monkeypatch)
    saved = _released(api)
    grant_id = _open(api, "larger_prerun")
    _to_highlight_2(api, grant_id)
    later = _to_the_end(api, grant_id)  # skipping on
    assert later["on_run_through"] is True
    assert _counts(api, grant_id) == _counts(api, saved.grant_id)
    shown = [p for p in later["just_happened"] if p["event"]["name"] == name]
    assert shown and shown[0]["delivered_by_sample_accountant"] is True


def test_moving_past_a_held_step_skipping_off_goes_live(
    setup: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = setup
    _marked(monkeypatch)
    _released(api)
    grant_id = _open(api, "larger_prerun")
    _to_highlight_2(api, grant_id)
    moved = _post(api, f"/grants/{grant_id}/timeline", {}).json()  # Next event, skipping off
    assert moved["on_run_through"] is False


# Next highlight to a highlight whose own step is due after its event (ruling 77, amended).


def _late_receipt(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any]:
    """The small sample with the receipt's delivery marked as the receipt highlight's own
    step and due half an hour after the receipt's event (built here, not in data/). Returns
    the receipt event and its delivery step."""
    pack = player.pack_for(SMALL)
    receipt = next(e for e in pack.events if e.deliver_by_user)
    actions = tuple(
        replace(a, highlight=receipt.highlight, at=receipt.at + timedelta(minutes=30))
        if a.action == "deliver_file"
        else a
        for a in pack.actions
    )
    late = replace(pack, actions=tuple(sorted(actions, key=lambda a: a.at)))
    monkeypatch.setattr(player, "pack_for", lambda _s: late)
    return receipt, next(a for a in late.actions if a.action == "deliver_file")


def _delivery_state(api: Api, grant_id: str) -> str | None:
    with transaction(api.platform.pool) as conn:
        rows = sample_store.grant_scripted(conn, grant_id)
    pack = player.pack_for(SMALL)
    return next((s.state for s in rows if pack.actions[s.step].action == "deliver_file"), None)


def test_on_the_run_through_a_late_own_step_is_held_and_matched(
    setup: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a prerun grant: Next highlight loads up to the own step's time and holds it; the
    next press is refused until the user makes it (ruling 86); the user delivers it, the
    grant stays on, and a later skip loads the rest."""
    api = setup
    receipt, step = _late_receipt(monkeypatch)
    # The moved delivery puts the receipt's evidence after the key's time, so the key
    # doesn't hold; this test is about loading, so the prerun is released here directly.
    saved = _make(api)
    with transaction(api.platform.pool) as conn:
        conn.execute("update public.sample_preruns set released = true where id = %s", (saved.id,))
    agent = api.platform.agent
    assert isinstance(agent, FakeAgent)
    agent.behave = lambda _i: AgentResult()
    grant_id = _open(api, "larger_prerun")
    timeline = _to_highlight_2(api, grant_id)
    assert timeline["on_run_through"] is True
    assert timeline["now"]["now"] == _iso(step.at)
    assert _delivery_state(api, grant_id) == "held"
    # Ruling 86: Next highlight waits for the user's step, on the run-through too.
    again = _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True})
    assert again.status_code == 409 and "Bring in" in again.json()["detail"]
    assert _delivery_state(api, grant_id) == "held"
    delivered = _post(api, f"/grants/{grant_id}/timeline/deliveries/{receipt.id}", {})
    assert delivered.json()["on_run_through"] is True
    assert _delivery_state(api, grant_id) == "user"
    _to_the_end(api, grant_id)
    assert _counts(api, grant_id) == _counts(api, saved.grant_id)
    _no_seeding_ids(api, saved, grant_id)


# What the review's mutations showed untested.


def test_a_stale_prerun_stops_loading(setup: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """The app changed since the prerun was made (another version): the grant goes live."""
    api = setup
    _released(api)
    grant_id = _open(api, "larger_prerun")
    assert _get(api, f"/grants/{grant_id}/timeline")["on_run_through"] is True
    made_at = prerun.version
    monkeypatch.setattr(prerun, "version", lambda *a, **k: "another" + made_at(*a, **k))
    assert _get(api, f"/grants/{grant_id}/timeline")["on_run_through"] is False
    moved = _to_the_end(api, grant_id)
    assert not any(p["loaded"] for p in moved["just_happened"])


def test_the_walk_check_never_takes_a_seeding_walk_on(setup: Api) -> None:
    api = setup
    _reading_agent(api)
    seen: dict[str, Any] = {}

    def drain(queue: str) -> None:
        with transaction(api.platform.pool) as conn:
            seen["walking"] = [
                r["grant_id"]
                for r in conn.execute("select grant_id from public.sample_walks").fetchall()
            ]
            seen["checked"] = sample_store.walking_grants(conn)
        prerun.drain_jobs(str(api.platform.pool.conninfo), queue)

    made = prerun.make(api.platform, SMALL, api.user_id, drain=drain)
    assert made.grant_id in seen["walking"]  # its walk waits on the agent
    assert made.grant_id not in seen["checked"]


def _attachment_on(api: Api, grant_id: str) -> None:
    """An attachment on the prerun's grant: a file whose parent is one of its files."""
    from app.contracts.evidence import storage_path

    with transaction(api.platform.pool) as conn:
        # The latest file, so the attachment is stored after everything, as it was read.
        parent = max(
            store.list_files(conn, grant_id, store.END_OF_TIME), key=lambda f: f.arrived_at
        )
        child_id = str(uuid.uuid4())
        path = storage_path(parent.workspace_id, grant_id, child_id, "attachment.pdf")
        data = b"%PDF-1.4 a synthetic attachment"
        api.platform.storage.put(path, data, "application/pdf")
        store.insert_file(
            conn,
            parent.model_copy(
                update={
                    "id": child_id,
                    "name": "attachment.pdf",
                    "media_type": "application/pdf",
                    "storage_path": path,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "parent_id": parent.id,
                    "stored_seq": None,
                }
            ),
        )


def test_loading_maps_read_points_and_parents(setup: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each copied record's read point covers the same rows, by the prerun's stored order,
    as the prerun's did; each copied file's parent is the copy of its parent."""
    api = setup
    monkeypatch.setitem(player.PACK_FOR_CHOICE, SampleChoice.LARGER_PRERUN, LARGER_SAMPLE)
    saved = _released(api, sample=LARGER_SAMPLE)
    _attachment_on(api, saved.grant_id)
    grant_id = _open(api, "larger_prerun")
    _to_the_end(api, grant_id, LARGER_SAMPLE)

    def seqs(rows: dict[str, list[dict[str, Any]]]) -> list[int]:
        return sorted(
            int(r["stored_seq"]) for k in ("files", "charges", "records") for r in rows[k]
        )

    source, copied = _rows(api, saved.grant_id), _rows(api, grant_id)
    signed = {r["id"] for r in source["records"] if r["kind"] == "sign_off"}
    source_seqs = sorted(
        int(r["stored_seq"])
        for k in ("files", "charges", "records")
        for r in source[k]
        if r["id"] not in signed
    )
    copied_seqs = seqs(copied)
    by_point = {
        int(r["read_through_seq"])
        for r in source["records"]
        if r["read_through_seq"] is not None and r["id"] not in signed
    }
    expected = {p: sum(1 for s in source_seqs if s <= p) for p in by_point}
    for r in copied["records"]:
        if r["read_through_seq"] is None:
            continue
        covered = sum(1 for s in copied_seqs if s <= int(r["read_through_seq"]))
        assert covered in expected.values()
    files = {r["id"]: r for r in copied["files"]}
    children = [f for f in files.values() if f["parent_id"]]
    assert children and all(f["parent_id"] in files for f in children)


# Ruling 86 on a loaded grant.


def _at_the_opening_step(api: Api) -> tuple[str, Any]:
    """A prerun grant whose first Next highlight press stopped at the award letter's own
    step, confirming its terms, which comes due before the next highlight."""
    confirm = next(a for a in player.pack_for(SMALL).actions if a.action == "confirm_terms")
    assert confirm.highlight is not None
    _released(api)
    grant_id = _open(api, "larger_prerun")
    first = _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True})
    assert first.status_code == 200, first.text
    timeline = first.json()
    assert timeline["on_run_through"] is True and timeline["now"]["now"] == _iso(confirm.at)
    assert all(p["loaded"] for p in timeline["just_happened"])
    assert _confirmations(api, grant_id) == []  # held: not loaded as made
    return grant_id, confirm


def test_on_the_run_through_next_highlight_waits_for_the_held_step(setup: Api) -> None:
    """Next highlight is refused with the step's reason, so the clock never moves past
    what's loaded; once the user confirms as read, the grant stays on and the next press
    loads at once."""
    api = setup
    grant_id, confirm = _at_the_opening_step(api)
    reason = f"Confirm the terms read from {confirm.file} first: that's this highlight's step."
    assert _get(api, f"/grants/{grant_id}/timeline")["next_highlight_unavailable_reason"] == reason
    refused = _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True})
    assert refused.status_code == 409 and refused.json()["detail"] == reason
    assert _get(api, f"/grants/{grant_id}/timeline")["now"]["now"] == _iso(confirm.at)
    write = _scripted_write(api, grant_id, "confirm_terms")
    assert _post(api, f"/grants/{grant_id}/records", {"data": write.data}).status_code == 201
    second = _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True})
    assert second.status_code == 200, second.text
    assert second.json()["on_run_through"] is True and _pending(api, grant_id) == 0


def test_on_the_run_through_a_skipping_next_event_makes_the_held_step(setup: Api) -> None:
    """Next event with skipping on loads the sample accountant's step the press held, and
    the grant stays on; Next highlight is available again."""
    api = setup
    grant_id, _confirm = _at_the_opening_step(api)
    moved = _post(api, f"/grants/{grant_id}/timeline", {"skip_human_steps": True})
    assert moved.status_code == 200, moved.text
    timeline = moved.json()
    assert timeline["on_run_through"] is True
    [confirmation] = _confirmations(api, grant_id)
    assert confirmation.author_user_id != api.user_id  # the sample accountant's
    assert timeline["next_highlight_unavailable_reason"] is None
    again = _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True})
    assert again.status_code == 200, again.text
    assert again.json()["on_run_through"] is True


# The expected prerun: the demo's fallback, a choice of its own beside the prerun.


def _as_expected(api: Api, made: prerun.Prerun) -> prerun.Prerun:
    """Mark a prerun expected, as the script that writes expected preruns does, and
    release it."""
    with transaction(api.platform.pool) as conn:
        conn.execute(
            """update public.sample_preruns
                 set usage = usage || '{"expected": true}'::jsonb where id = %s""",
            (made.id,),
        )
    return prerun.release(api.platform, made.id)


def _own_prerun(api: Api, grant_id: str) -> str:
    with transaction(api.platform.pool) as conn:
        row = conn.execute(
            "select prerun_id from public.sample_runthrough where grant_id = %s", (grant_id,)
        ).fetchone()
    assert row is not None
    return row["prerun_id"]


def _choices(api: Api) -> dict[str, Any]:
    return {o["choice"]: o for o in _get(api, "/samples")}


def test_each_prerun_choice_opens_only_its_kind(setup: Api) -> None:
    api = setup
    expected = _as_expected(api, _make(api))
    played = prerun.release(api.platform, _make(api).id)
    newer_expected = _as_expected(api, _make(api))  # newest of all: still only its own choice
    assert prerun.is_expected(expected) and not prerun.is_expected(played)
    assert _own_prerun(api, _open(api, "larger_prerun")) == played.id
    assert _own_prerun(api, _open(api, "larger_expected")) == newer_expected.id


def test_each_prerun_choice_is_unavailable_without_its_kind(setup: Api) -> None:
    api = setup
    choices = _choices(api)
    assert choices["larger_prerun"]["available"] is False
    assert choices["larger_expected"]["available"] is False
    assert choices["larger_expected"]["unavailable_reason"]
    _as_expected(api, _make(api))
    choices = _choices(api)
    assert choices["larger_expected"]["available"] is True
    assert choices["larger_prerun"]["available"] is False  # an expected one never stands in
    workspace_id = _workspace(api)
    refused = _post(api, f"/workspaces/{workspace_id}/samples", {"choice": "larger_prerun"})
    assert refused.status_code == 422
    with transaction(api.platform.pool) as conn:
        conn.execute("update public.sample_preruns set released = false")
    prerun.release(api.platform, _make(api).id)  # a played one only
    choices = _choices(api)
    assert choices["larger_prerun"]["available"] is True
    assert choices["larger_expected"]["available"] is False
    refused = _post(api, f"/workspaces/{workspace_id}/samples", {"choice": "larger_expected"})
    assert refused.status_code == 422


def test_the_expected_choice_says_what_it_is(setup: Api) -> None:
    api = setup
    choice = _choices(api)["larger_expected"]
    assert choice["name"] == "Larger sample, expected prerun"
    assert "expect the agent to write" in choice["description"]
    assert "aren't the agent's output" in choice["description"]
    assert choice["needs_confirm"] is False


def test_a_grant_opened_from_the_expected_prerun_says_so(setup: Api) -> None:
    """Keyed off the grant's own prerun: the expected choice's grant says so as it loads
    to the end; one opened from the played prerun doesn't; a live one has no prerun."""
    api = setup
    expected = _as_expected(api, _make(api))
    prerun.release(api.platform, _make(api).id)
    grant_id = _open(api, "larger_expected")
    timeline = _to_the_end(api, grant_id)
    assert timeline["expected_prerun"] is True and timeline["on_run_through"] is True
    assert all(p["loaded"] for p in timeline["just_happened"])
    assert _counts(api, grant_id) == _counts(api, expected.grant_id)
    played_grant = _open(api, "larger_prerun")
    assert _get(api, f"/grants/{played_grant}/timeline")["expected_prerun"] is False
    live = _open(api, "small_live")
    assert _get(api, f"/grants/{live}/timeline")["expected_prerun"] is None
