"""Skipping the human steps (rulings 47, 52, 55, 56 and 60, first version).

The agent is faked by the sample's own `agent_records.json`: each run writes the records
written at its time, as the live agent would, through the ordinary save.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.contracts.records import Author, Record
from app.contracts.workspaces import Grant
from app.db import store
from app.db.pool import transaction
from app.db.ports import AgentInput, AgentResult, ModuleChecks
from app.samples import player
from app.samples.pack import SamplePack, UserAction
from tests.api.conftest import Api
from tests.db.platform_fixtures import FakeAgent, run_worker_until_idle

from .plays import Mapping, _mapped, _pointed_first, bucket_at
from .test_player import _get, _open, _post

SMALL = "nitrate-sensors"


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _grant(api: Api, grant_id: str) -> Grant:
    with transaction(api.platform.pool) as conn:
        grant = store.get_grant(conn, grant_id)
    assert grant is not None
    return grant


def _records_agent(api: Api, pack: SamplePack, grant_id: str) -> None:
    """The agent, faked by agent_records.json: a run writes the records of its time it
    hasn't written yet, mapped onto this grant."""
    raw = json.loads((pack.folder / "agent_records.json").read_text())["records"]
    mapping = Mapping(pack, _grant(api, grant_id))  # one mapping: a placeholder keeps its ID
    agent = api.platform.agent
    assert isinstance(agent, FakeAgent)

    def behave(i: AgentInput) -> AgentResult:
        with transaction(api.platform.pool) as conn:
            on_grant = {r.id for r in store.list_records(conn, grant_id)}
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


@pytest.fixture
def real_checks(api: Api) -> None:
    api.platform.checks = ModuleChecks()


def _skip(api: Api, grant_id: str, to: datetime | None) -> Any:
    response = _post(
        api,
        f"/grants/{grant_id}/timeline",
        {"to": _iso(to) if to else None, "skip_human_steps": True},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _scripted(api: Api, grant_id: str) -> list[dict[str, Any]]:
    with transaction(api.platform.pool) as conn:
        return conn.execute(
            "select step, state, record_id, file_id from public.sample_scripted"
            " where grant_id = %s order by step",
            (grant_id,),
        ).fetchall()


def _accountant(api: Api, grant_id: str) -> str:
    with transaction(api.platform.pool) as conn:
        grant = store.get_grant(conn, grant_id)
        assert grant is not None
        return store.sample_accountant_id(conn, grant.workspace_id)


def test_the_sample_accountant_brings_the_users_items_in(api: Api, real_checks: None) -> None:
    pack = player.pack_for(SMALL)
    marked = [e for e in pack.events if e.deliver_by_user]
    brought = {a.file: a.at for a in pack.actions if a.action == "deliver_file"}
    grant_id = _open(api)
    end = max(i.at for i in player.items_for(SMALL)) + timedelta(days=1)
    _skip(api, grant_id, end)
    # The walk waits for the agent before each decision: let it get to the end.
    run_worker_until_idle(str(api.platform.pool.conninfo))
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert timeline["now"]["now"] == _iso(end)
    assert timeline["now"]["deliveries"] == []
    with transaction(api.platform.pool) as conn:
        files = {f.sha256: f for f in store.list_files(conn, grant_id, end)}
    for e in marked:
        f = files[pack.sha256(e.name)]
        assert f.arrived_at == brought[e.name]  # at the step's own time
    shown = {p["event"]["name"]: p for p in timeline["just_happened"]}
    for e in marked:
        assert shown[e.name]["delivered_by_sample_accountant"] is True  # ruling 52


def test_without_skipping_nothing_is_made_for_the_user(api: Api) -> None:
    grant_id = _open(api)
    end = max(i.at for i in player.items_for(SMALL)) + timedelta(days=1)
    timeline = _post(api, f"/grants/{grant_id}/timeline", {"to": _iso(end)}).json()
    assert len(timeline["now"]["deliveries"]) == sum(
        1 for e in player.pack_for(SMALL).events if e.deliver_by_user
    )
    assert _scripted(api, grant_id) == []


def test_a_decision_waits_for_the_agents_runs_before_it(api: Api, real_checks: None) -> None:
    """The award letter's terms are confirmed once the agent has read them, at the step's
    own time, by the Sample accountant. The move played no event, so the decision shows
    under the event the clock stood on (ruling 60)."""
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)
    timeline = _skip(api, grant_id, confirm.at + timedelta(minutes=1))
    assert [s["state"] for s in _scripted(api, grant_id)] == ["pending"]  # the letter isn't read
    assert timeline["just_happened"] == []
    run_worker_until_idle(str(api.platform.pool.conninfo))
    [made] = _scripted(api, grant_id)
    assert made["state"] == "done"
    with transaction(api.platform.pool) as conn:
        records = store.list_records(conn, grant_id)
    decision = next(r for r in records if r.id == made["record_id"])
    assert decision.kind.value == "confirmation" and decision.author == Author.USER
    assert decision.author_user_id == _accountant(api, grant_id)
    assert decision.written_at == confirm.at
    [shown] = _get(api, f"/grants/{grant_id}/timeline")["just_happened"]
    assert shown["event"]["name"] == pack.events[0].name
    assert [r["id"] for r in shown["scripted_decisions"]] == [decision.id]


def test_a_decision_shows_under_the_moves_first_event_when_none_comes_before_it(
    api: Api, real_checks: None
) -> None:
    """Ruling 55: under the latest event at or before it; if none, the move's first."""
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    after = next(e for e in pack.events if e.at > confirm.at)
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)
    _skip(api, grant_id, after.at)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    just = _get(api, f"/grants/{grant_id}/timeline")["just_happened"]
    decisions = [d["id"] for p in just for d in p["scripted_decisions"]]
    assert len(decisions) == 1  # listed exactly once
    assert just[0]["event"]["name"] == after.name and just[0]["scripted_decisions"]


def test_a_step_whose_target_isnt_there_is_left_for_the_user(api: Api, real_checks: None) -> None:
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    grant_id = _open(api)  # the agent writes nothing: no terms wait
    _skip(api, grant_id, confirm.at + timedelta(minutes=1))
    run_worker_until_idle(str(api.platform.pool.conninfo))
    [left] = _scripted(api, grant_id)
    assert left["state"] == "left" and left["record_id"] is None


def _skip_through(api: Api, sample: str) -> str:
    """One skipping move from the sample's start to past its end, the agent (faked by
    agent_records.json) reading as the clock walks; returns the grant."""
    pack = player.pack_for(sample)
    grant_id = _open(api, "small_live" if sample == SMALL else "larger_live")
    _records_agent(api, pack, grant_id)
    end = max(i.at for i in player.items_for(sample)) + timedelta(days=1)
    _skip(api, grant_id, end)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    assert _get(api, f"/grants/{grant_id}/timeline")["now"]["now"] == _iso(end)
    return grant_id


def _wrong_buckets(api: Api, grant_id: str, sample: str) -> list[str]:
    key = json.loads((player.pack_for(sample).folder / "answer_key.json").read_text())
    grant = _grant(api, grant_id)
    return [
        f"{b['line_id']} at {b['at']}: {got} != {b['bucket']}"
        for b in key["buckets"]
        if (got := bucket_at(api.platform, grant, b["line_id"], datetime.fromisoformat(b["at"])))
        != b["bucket"]
    ]


def _emails_arrive_at_their_own_time(api: Api, grant_id: str, sample: str) -> None:
    """Every scheduled email arrives at its own time, or, held from a sender nobody named,
    when the script lets it in."""
    pack = player.pack_for(sample)
    let_in = {a.file: a.at for a in pack.actions if a.action == "let_in_mail"}
    with transaction(api.platform.pool) as conn:
        arrived = {
            f.sha256: f.arrived_at for f in store.list_files(conn, grant_id, store.END_OF_TIME)
        }
    for e in pack.events:
        if e.source.value != "gmail" or e.deliver_by_user:
            continue
        assert arrived.get(pack.sha256(e.name)) == let_in.get(e.name, e.at), e.name


LARGER = "salt-marsh-carbon"

# agent_records.json's link for L-1835-0015 (highlight 5) carries an amount but fills no
# checklist item that carries one, so the save's write check refuses it, and the run that
# writes it fails. The checks-only play stores the records directly and doesn't meet it.
# Strict: once the seed's record is fixed, this marker must go.
SEED_LINK = pytest.mark.xfail(
    strict=True, reason="agent_records.json: L-1835-0015's link carries an amount"
)


@pytest.mark.parametrize("sample", [SMALL, LARGER])
def test_skipping_through_a_sample_brings_every_email_at_its_own_time(
    api: Api, real_checks: None, sample: str
) -> None:
    """One skipping move to the end, the clock walking event by event and step by step:
    every scripted step is made, and every email arrives at its own time (or when the
    script lets it in), after the confirmation that makes its sender known."""
    grant_id = _skip_through(api, sample)
    assert {s["state"] for s in _scripted(api, grant_id)} == {"done"}
    _emails_arrive_at_their_own_time(api, grant_id, sample)


@pytest.mark.parametrize("sample", [SMALL, pytest.param(LARGER, marks=SEED_LINK)])
def test_skipping_through_a_sample_gives_the_keys_buckets(
    api: Api, real_checks: None, sample: str
) -> None:
    """The do-everything play by skipping, as a user making each step at its own time: every
    agent run saves, and every bucket in the answer key holds."""
    grant_id = _skip_through(api, sample)
    with transaction(api.platform.pool) as conn:
        runs = store.list_runs(conn, grant_id)
    assert {r.status.value for r in runs} == {"done"}
    assert _wrong_buckets(api, grant_id, sample) == []


def test_a_decision_made_after_a_later_move_is_listed_once(api: Api, real_checks: None) -> None:
    """A decision move A passed, made only after move B, is listed under B, once."""
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)
    _skip(api, grant_id, confirm.at + timedelta(minutes=1))  # waits for the letter's run
    later = _post(
        api, f"/grants/{grant_id}/timeline", {"to": _iso(confirm.at + timedelta(minutes=2))}
    )
    assert later.status_code == 200, later.text
    run_worker_until_idle(str(api.platform.pool.conninfo))
    just = _get(api, f"/grants/{grant_id}/timeline")["just_happened"]
    decisions = [d["id"] for p in just for d in p["scripted_decisions"]]
    assert len(decisions) == 1


def test_a_scripted_sign_off_waits_for_every_run(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = player.pack_for(SMALL)
    sign = UserAction(
        at=pack.starts_at + timedelta(minutes=5), action="sign_off", note="Signed by the script."
    )
    signed_pack = replace(pack, actions=(*pack.actions, sign))
    monkeypatch.setattr(player, "pack_for", lambda _sample: signed_pack)
    grant_id = _open(api)  # the letter's run is queued
    _skip(api, grant_id, sign.at + timedelta(minutes=1))
    [waiting] = [s for s in _scripted(api, grant_id) if s["state"] == "pending"]
    assert waiting["step"] == len(signed_pack.actions) - 1
    run_worker_until_idle(str(api.platform.pool.conninfo))
    [signed] = [s for s in _scripted(api, grant_id) if s["step"] == waiting["step"]]
    assert signed["state"] == "done"
    with transaction(api.platform.pool) as conn:
        record = next(r for r in store.list_records(conn, grant_id) if r.id == signed["record_id"])
    assert record.kind.value == "sign_off" and record.written_at == sign.at
    assert record.author_user_id == _accountant(api, grant_id)
