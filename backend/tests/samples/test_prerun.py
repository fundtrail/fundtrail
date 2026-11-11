"""The prerun (decision 0027, ruling 47, first version), with the agent faked by the
sample's own agent_records.json. The command itself makes paid calls and never runs here."""

from __future__ import annotations

import json
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from app.contracts.records import Author, Record
from app.contracts.workspaces import SampleChoice
from app.db import sample_store, store
from app.db.pool import transaction
from app.db.ports import AgentInput, AgentResult, ModuleChecks
from app.samples import player, prerun
from app.samples.pack import DATA_DIR
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
        return AgentResult(records=result.records, log=json.dumps(LOG).encode())

    agent.behave = with_log


def _reading_agent(api: Api) -> None:
    """The agent, faked by agent_records.json: a run writes the records of its time that
    aren't on its grant yet, mapped onto whichever grant it runs on."""
    pack = player.pack_for(SMALL)
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
        return AgentResult(records=records)

    agent.behave = behave


def _make(api: Api, *, read: bool = True) -> prerun.Prerun:
    """A prerun of the small sample, the agent reading from agent_records.json (or nothing)."""
    if read:
        _reading_agent(api)
    _logged(api)
    return prerun.make(
        api.platform,
        SMALL,
        api.user_id,
        drain=lambda: run_worker_until_idle(str(api.platform.pool.conninfo)),
    )


def test_the_version_changes_with_the_sample(tmp_path: Path) -> None:
    assert prerun.version(SMALL) == prerun.version(SMALL)
    copy = tmp_path / "samples" / SMALL
    shutil.copytree(DATA_DIR / "samples" / SMALL, copy)
    assert prerun.version(SMALL, tmp_path) == prerun.version(SMALL)
    (copy / "timeline.json").write_text((copy / "timeline.json").read_text() + "\n")
    assert prerun.version(SMALL, tmp_path) != prerun.version(SMALL)


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


def test_the_spend_cap_stops_runs_before_going_over(setup: Api) -> None:
    """Each faked run spends $0.009 at the list prices; with a $0.03 cap and $0.009 kept
    back, the third run doesn't start, and the prerun can't be released."""
    api = setup
    _reading_agent(api)
    _logged(api)
    capped = prerun.CappedAgent(api.platform.agent, cap=0.03, reserve=0.009)
    api.platform.agent = capped
    made = prerun.make(
        api.platform,
        SMALL,
        api.user_id,
        drain=lambda: run_worker_until_idle(str(api.platform.pool.conninfo)),
        capped=capped,
    )
    assert capped.stopped and made.usage["stopped_at_cap"] is True
    assert made.usage["cost_dollars"] <= 0.03
    assert capped.spent <= 0.03
    with transaction(api.platform.pool) as conn:
        runs = store.list_runs(conn, made.grant_id)
    assert any("spend cap" in (r.error or "") for r in runs)
    with pytest.raises(prerun.NotReleasable, match="spend cap"):
        prerun.release(api.platform, made.id)
    report = prerun._report(made)  # pyright: ignore[reportPrivateUsage]
    assert "stopped at the spend cap" in report and "not released" in report


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


def _released(api: Api) -> prerun.Prerun:
    saved = prerun.release(api.platform, _make(api).id)
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


def test_a_prerun_grant_loads_the_saved_result_while_on_the_run_through(setup: Api) -> None:
    api = setup
    saved = _released(api)
    grant_id = _open(api, "larger_prerun")
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert timeline["on_run_through"] is True
    assert [p["loaded"] for p in timeline["just_happened"]] == [True]
    assert _pending(api, grant_id) == 0  # nothing runs: the agent's work was done ahead

    end = max(i.at for i in player.items_for(SMALL)) + timedelta(days=1)
    moved = _post(
        api, f"/grants/{grant_id}/timeline", {"to": _iso(end), "skip_human_steps": True}
    ).json()
    assert moved["on_run_through"] is True
    assert all(p["loaded"] for p in moved["just_happened"])
    assert _pending(api, grant_id) == 0
    assert _counts(api, grant_id) == _counts(api, saved.grant_id)

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


def test_the_command_needs_a_spend_cap() -> None:
    with pytest.raises(SystemExit) as stopped:
        prerun.main(["make", "salt-marsh-carbon", "--owner", "someone"])
    assert stopped.value.code == 2  # argparse: --cap is required
