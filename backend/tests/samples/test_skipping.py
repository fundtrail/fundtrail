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
from app.db import sample_store, store
from app.db.actions import WriteRejected
from app.db.jobs import grant_lock
from app.db.pings import grant_topic
from app.db.pool import transaction
from app.db.ports import AgentInput, AgentResult, ModuleChecks
from app.samples import player, skipping
from app.samples.pack import SamplePack, UserAction
from app.samples.script import WriteRecord, resolve
from tests.api.conftest import Api
from tests.db.platform_fixtures import FakeAgent, FakePinger, run_worker_until_idle

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


@pytest.mark.parametrize("sample", [SMALL, LARGER])
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


# What the walk has played, and a walk that goes wrong.


def _walk(api: Api, grant_id: str) -> tuple[datetime | None, str | None]:
    """Where the grant's walk is going (None when there's none), and why the last move's
    walk stopped short (None when it didn't)."""
    with transaction(api.platform.pool) as conn:
        target = sample_store.walk_target(conn, grant_id)
        last = sample_store.last_move(conn, grant_id)
    return target, last.walk_stopped if last else None


def _runs(api: Api, grant_id: str) -> set[str]:
    with transaction(api.platform.pool) as conn:
        return {r.status.value for r in store.list_runs(conn, grant_id)}


def test_just_happened_and_coming_up_follow_the_walks_clock(api: Api, real_checks: None) -> None:
    """While the walk waits at a decision, Just happened lists only what it has played and
    Coming up still lists the rest. A plain Next event during the walk takes on what the
    walk plays after it, so every played event is under exactly one move."""
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    after = [e for e in pack.events if e.at > confirm.at]
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)
    waiting = _skip(api, grant_id, after[1].at)  # the walk waits at the confirmation
    assert waiting["now"]["now"] == _iso(confirm.at)
    assert waiting["just_happened"] == []
    coming = [e["name"] for e in waiting["coming_up"]]
    assert after[0].name in coming and after[1].name in coming
    # Next event during the walk: from the walk's date to the next item after it.
    moved = _post(api, f"/grants/{grant_id}/timeline", {})
    assert moved.status_code == 200, moved.text
    assert moved.json()["just_happened"] == []  # still nothing played
    run_worker_until_idle(str(api.platform.pool.conninfo))
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert timeline["now"]["now"] == _iso(after[2].at)
    shown = [p["event"]["name"] for p in timeline["just_happened"]]
    assert shown == [e.name for e in after[:3]]  # played after the later move: listed there
    assert sum(len(p["scripted_decisions"]) for p in timeline["just_happened"]) == 1
    assert all(e["name"] not in shown for e in timeline["coming_up"])


def test_a_failing_decision_is_left_and_the_walk_goes_on(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    end = next(e for e in pack.events if e.at > confirm.at).at
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)

    def fails(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("the write broke")

    monkeypatch.setattr(skipping, "write_record", fails)
    _skip(api, grant_id, end)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    [left] = _scripted(api, grant_id)
    assert left["state"] == "left" and left["record_id"] is None
    assert _walk(api, grant_id) == (None, None)  # it went on to its end
    assert _get(api, f"/grants/{grant_id}/timeline")["now"]["now"] == _iso(end)
    assert _runs(api, grant_id) == {"done"}


def test_a_refused_decision_is_left_and_the_walk_goes_on(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    end = next(e for e in pack.events if e.at > confirm.at).at
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)

    def refused(*_args: Any, **_kwargs: Any) -> Any:
        raise WriteRejected(["refused by the write check"])

    monkeypatch.setattr(skipping, "write_record", refused)
    _skip(api, grant_id, end)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    assert [s["state"] for s in _scripted(api, grant_id)] == ["left"]
    assert _walk(api, grant_id) == (None, None)
    assert _get(api, f"/grants/{grant_id}/timeline")["now"]["now"] == _iso(end)


def test_a_failing_delivery_is_left_and_the_walk_goes_on(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = player.pack_for(SMALL)
    deliver = next(a for a in pack.actions if a.action == "deliver_file")
    end = deliver.at + timedelta(hours=1)
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)

    def fails(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("storage is down")

    monkeypatch.setattr(skipping, "arrive_files", fails)
    _skip(api, grant_id, end)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    states = {pack.actions[s["step"]].action: s["state"] for s in _scripted(api, grant_id)}
    assert states == {"confirm_terms": "done", "deliver_file": "left"}
    assert _walk(api, grant_id) == (None, None)
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert timeline["now"]["now"] == _iso(end)
    assert [d["event"]["name"] for d in timeline["now"]["deliveries"]] == [deliver.file]


def test_a_walk_that_cant_play_stops_with_a_reason_and_the_run_stands(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Playing fails in the walk going on after the letter's run: the run is saved, the
    decision made before it stands, and the walk stops where it is, with the reason."""
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    end = next(e for e in pack.events if e.at > confirm.at).at
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)
    _skip(api, grant_id, end)  # waits for the letter's run

    def fails(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("a broken event")

    monkeypatch.setattr(player, "store_events", fails)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    assert _runs(api, grant_id) == {"done"}
    assert [s["state"] for s in _scripted(api, grant_id)] == ["done"]
    target, stopped = _walk(api, grant_id)
    assert target is None
    assert stopped is not None and "couldn't be played (RuntimeError)" in stopped
    assert _get(api, f"/grants/{grant_id}/timeline")["now"]["now"] == _iso(confirm.at)


def test_an_error_going_on_with_the_walk_never_undoes_the_run(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The walk raises after the letter's run saves: the run and its records stand. The
    check every minute takes the walk on once nothing breaks it."""
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    end = next(e for e in pack.events if e.at > confirm.at).at
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)
    _skip(api, grant_id, end)

    def breaks(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("the walk broke")

    monkeypatch.setattr(skipping, "advance", breaks)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    assert _runs(api, grant_id) == {"done"}
    with transaction(api.platform.pool) as conn:
        assert any(r.author is Author.AGENT for r in store.list_records(conn, grant_id))
    assert _walk(api, grant_id) == (end, None)  # still under way, nothing taking it on
    monkeypatch.undo()
    skipping.check_walks(api.platform)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    assert [s["state"] for s in _scripted(api, grant_id)] == ["done"]
    assert _walk(api, grant_id) == (None, None)
    assert _get(api, f"/grants/{grant_id}/timeline")["now"]["now"] == _iso(end)


def test_a_walk_waiting_on_a_run_with_no_job_stops(api: Api, real_checks: None) -> None:
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    grant_id = _open(api)
    _skip(api, grant_id, confirm.at + timedelta(minutes=1))  # waits for the letter's run
    skipping.check_walks(api.platform)
    assert _walk(api, grant_id)[0] is not None  # its run's job is waiting: nothing to do
    with transaction(api.platform.pool) as conn:
        conn.execute("delete from procrastinate_jobs where lock = %s", (grant_lock(grant_id),))
    skipping.check_walks(api.platform)
    assert _walk(api, grant_id)[0] is not None  # once could be a run ending as it checked
    skipping.check_walks(api.platform)
    target, stopped = _walk(api, grant_id)
    assert target is None
    assert stopped is not None and "nothing left to run it" in stopped
    assert [s["state"] for s in _scripted(api, grant_id)] == ["left"]


def test_a_users_upload_during_a_walk(api: Api, real_checks: None) -> None:
    """The user uploads while the walk waits: the file arrives at the walk's clock, its run
    is waited for like any other, and the walk goes on to its end."""
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    end = next(e for e in pack.events if e.at > confirm.at).at
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)
    _skip(api, grant_id, end)
    uploaded = api.client.post(
        f"/grants/{grant_id}/evidence",
        files={"file": ("lab_note.txt", b"A note from the lab, synthetic.", "text/plain")},
        headers=api.headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["arrived_at"] == _iso(confirm.at)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    assert [s["state"] for s in _scripted(api, grant_id)] == ["done"]
    assert _walk(api, grant_id) == (None, None)
    assert _runs(api, grant_id) == {"done"}
    assert _get(api, f"/grants/{grant_id}/timeline")["now"]["now"] == _iso(end)


def test_a_users_own_move_during_a_walk_extends_it(api: Api, real_checks: None) -> None:
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    after = [e for e in pack.events if e.at > confirm.at]
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)
    _skip(api, grant_id, after[0].at)
    moved = _post(api, f"/grants/{grant_id}/timeline", {"to": _iso(after[3].at)})
    assert moved.status_code == 200, moved.text
    assert _walk(api, grant_id) == (after[3].at, None)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert timeline["now"]["now"] == _iso(after[3].at)
    assert [p["event"]["name"] for p in timeline["just_happened"]] == [e.name for e in after[:4]]
    assert _walk(api, grant_id) == (None, None)


def test_a_users_own_decision_during_a_walk(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The user confirms the letter's terms before the walk gets to it: the scripted step
    finds nothing left to confirm and is left, and the walk goes on to its end."""
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    end = next(e for e in pack.events if e.at > confirm.at).at
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)
    _skip(api, grant_id, end)
    # Hold the walk where it is while the letter's run saves.
    monkeypatch.setattr(skipping, "go_on", lambda *_args: None)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    monkeypatch.undo()
    with transaction(api.platform.pool) as conn:
        step = resolve(api.platform, conn, _grant(api, grant_id), pack, confirm, confirm.at)
    assert isinstance(step, WriteRecord)
    mine = _post(api, f"/grants/{grant_id}/records", {"data": step.data})
    assert mine.status_code == 201, mine.text
    skipping.check_walks(api.platform)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    [left] = _scripted(api, grant_id)
    assert left["state"] == "left"
    assert _walk(api, grant_id) == (None, None)
    with transaction(api.platform.pool) as conn:
        records = {r.id: r for r in store.list_records(conn, grant_id)}
    assert records[mine.json()["id"]].author_user_id != _accountant(api, grant_id)
    assert _get(api, f"/grants/{grant_id}/timeline")["now"]["now"] == _iso(end)


def test_skipping_again_after_a_walk_stopped(api: Api, real_checks: None) -> None:
    """A stopped walk leaves for the user only the steps whose time has come; the later
    ones go, so the next skipping move queues them again and makes them."""
    pack = player.pack_for(SMALL)
    deliver = next(a for a in pack.actions if a.action == "deliver_file")
    end = deliver.at + timedelta(hours=1)
    grant_id = _open(api)
    _skip(api, grant_id, end)  # waits at the confirmation for the letter's run
    with transaction(api.platform.pool) as conn:
        conn.execute("delete from procrastinate_jobs where lock = %s", (grant_lock(grant_id),))
    skipping.check_walks(api.platform)
    skipping.check_walks(api.platform)
    assert _walk(api, grant_id)[0] is None
    steps = [(pack.actions[s["step"]].action, s["state"]) for s in _scripted(api, grant_id)]
    assert steps == [("confirm_terms", "left")]  # the delivery's time hadn't come
    again = _skip(api, grant_id, end)
    assert again["now"]["now"] == _iso(end)
    states = {pack.actions[s["step"]].action: s["state"] for s in _scripted(api, grant_id)}
    assert states == {"confirm_terms": "left", "deliver_file": "done"}
    assert _walk(api, grant_id) == (None, None)


def _pinged(api: Api, grant_id: str) -> set[str]:
    pinger = api.platform.pinger
    assert isinstance(pinger, FakePinger)
    return {
        w
        for topic, event, payload in pinger.pings
        if topic == grant_topic(grant_id) and event == "changed"
        for w in payload["what"]
    }


def _held_after_the_letter(api: Api, monkeypatch: pytest.MonkeyPatch) -> str:
    """A skipping move past the confirmation, the walk held while the letter's run saves."""
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    end = next(e for e in pack.events if e.at > confirm.at).at
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)
    _skip(api, grant_id, end)
    with monkeypatch.context() as held:
        held.setattr(skipping, "go_on", lambda *_args: None)
        run_worker_until_idle(str(api.platform.pool.conninfo))
    pinger = api.platform.pinger
    assert isinstance(pinger, FakePinger)
    pinger.pings.clear()
    return grant_id


def test_the_minute_check_pings_the_grants_screens_when_it_takes_a_walk_on(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    grant_id = _held_after_the_letter(api, monkeypatch)
    skipping.check_walks(api.platform)  # the decision, then the events
    assert [s["state"] for s in _scripted(api, grant_id)] == ["done"]
    assert {"charges", "evidence", "records", "statuses", "thread"} <= _pinged(api, grant_id)


def test_going_on_after_a_run_pings_the_grants_screens(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    grant_id = _held_after_the_letter(api, monkeypatch)
    skipping.go_on(api.platform, grant_id)
    assert _walk(api, grant_id) == (None, None)
    assert {"charges", "evidence", "records", "statuses", "thread"} <= _pinged(api, grant_id)


def test_a_check_finding_nothing_pending_starts_the_idle_count_again(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = player.pack_for(SMALL)
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    grant_id = _open(api)
    _skip(api, grant_id, confirm.at + timedelta(minutes=1))  # waits for the letter's run
    with transaction(api.platform.pool) as conn:
        conn.execute("delete from procrastinate_jobs where lock = %s", (grant_lock(grant_id),))
    skipping.check_walks(api.platform)  # one idle check

    def idle() -> int:
        with transaction(api.platform.pool) as conn:
            row = conn.execute(
                "select idle_checks from public.sample_walks where grant_id = %s", (grant_id,)
            ).fetchone()
        assert row is not None
        return int(row["idle_checks"])

    assert idle() == 1
    with transaction(api.platform.pool) as conn:  # the run ends after all
        conn.execute(
            "update public.agent_runs set status = 'done' where grant_id = %s", (grant_id,)
        )
    monkeypatch.setattr(skipping, "advance", lambda *_args: skipping.Walked())
    skipping.check_walks(api.platform)
    assert idle() == 0


# Next highlight (ruling 77).


def _highlight_pack(monkeypatch: pytest.MonkeyPatch) -> tuple[SamplePack, str]:
    """The small sample with its receipt delivery marked as the receipt highlight's own
    step, and a scripted sign-off before it: built here, not in data/. Returns the pack
    and the receipt highlight's label."""
    pack = player.pack_for(SMALL)
    receipt = next(e for e in pack.events if e.deliver_by_user)
    assert receipt.highlight is not None
    sign = UserAction(
        at=receipt.at - timedelta(days=1), action="sign_off", note="Signed by the script."
    )
    actions = [
        replace(a, highlight=receipt.highlight) if a.action == "deliver_file" else a
        for a in pack.actions
    ]
    marked = replace(pack, actions=tuple(sorted([*actions, sign], key=lambda a: a.at)))
    monkeypatch.setattr(player, "pack_for", lambda _sample: marked)
    return marked, receipt.highlight


def _states(api: Api, pack: SamplePack, grant_id: str) -> dict[str, str]:
    return {pack.actions[s["step"]].action: s["state"] for s in _scripted(api, grant_id)}


def _next_highlight(api: Api, grant_id: str) -> Any:
    return _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True})


def test_next_highlight_leaves_its_own_step_and_never_signs_off(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack, label = _highlight_pack(monkeypatch)
    receipt = next(e for e in pack.events if e.highlight == label)
    grant_id = _open(api)  # stands on the award letter, the first highlight
    _records_agent(api, pack, grant_id)
    _next_highlight(api, grant_id)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert timeline["now"]["now"] == _iso(receipt.at)
    assert timeline["now"]["stopped_on"]["highlight"] == label
    # The unmarked step before it is made; its own step and the sign-off wait for the user.
    assert _states(api, pack, grant_id) == {
        "confirm_terms": "done",
        "sign_off": "held",
        "deliver_file": "held",
    }
    assert [d["event"]["name"] for d in timeline["now"]["deliveries"]] == [receipt.name]
    assert _walk(api, grant_id) == (None, None)


def test_a_later_skip_makes_the_steps_next_highlight_left(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack, label = _highlight_pack(monkeypatch)
    receipt = next(e for e in pack.events if e.highlight == label)
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)
    _next_highlight(api, grant_id)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    _skip(api, grant_id, None)  # Next event, skipping the human steps
    run_worker_until_idle(str(api.platform.pool.conninfo))
    states = _states(api, pack, grant_id)
    assert states["deliver_file"] == "done" and states["sign_off"] != "held"
    with transaction(api.platform.pool) as conn:
        files = store.list_files(conn, grant_id, store.END_OF_TIME)
    [brought] = [f for f in files if f.sha256 == pack.sha256(receipt.name)]
    assert brought.arrived_at == receipt.at  # at the clock when the later skip took it up
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert timeline["now"]["deliveries"] == []
    assert _walk(api, grant_id) == (None, None)


def test_the_user_making_a_held_step_first_is_never_made_again(
    api: Api, real_checks: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack, label = _highlight_pack(monkeypatch)
    receipt = next(e for e in pack.events if e.highlight == label)
    grant_id = _open(api)
    _records_agent(api, pack, grant_id)
    _next_highlight(api, grant_id)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    uploaded = api.client.post(
        f"/grants/{grant_id}/evidence",
        files={"file": ("receipt.jpg", pack.file_bytes(receipt.name), "image/jpeg")},
        headers=api.headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    _skip(api, grant_id, None)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    assert _states(api, pack, grant_id)["deliver_file"] == "left"  # the user brought it
    with transaction(api.platform.pool) as conn:
        files = store.list_files(conn, grant_id, store.END_OF_TIME)
    assert [f.id for f in files if f.sha256 == pack.sha256(receipt.name)] == [uploaded.json()["id"]]


def test_next_highlight_stops_on_a_ledger_lines_posting(api: Api) -> None:
    """A highlight on a ledger line: Next highlight stops where the line posts."""
    pack = player.pack_for(LARGER)
    items = player.items_for(LARGER)
    line = next(i for i in items if i.line_id and i.event and i.event.highlight)
    before = max(i.at for i in items if i.at < line.at and i.event and i.event.highlight)
    grant_id = _open(api, "larger_live")
    moved = _post(api, f"/grants/{grant_id}/timeline", {"to": _iso(before)})
    assert moved.status_code == 200, moved.text
    _next_highlight(api, grant_id)
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert timeline["now"]["now"] == _iso(line.at)
    assert timeline["now"]["stopped_on"]["name"] == line.name
    assert line.event is not None
    assert timeline["now"]["stopped_on"]["highlight"] == line.event.highlight
    assert line.name in pack.ledger_line_ids()


def test_next_highlight_with_none_left_is_refused(api: Api) -> None:
    grant_id = _open(api)
    last = max(i.at for i in player.items_for(SMALL) if i.event and i.event.highlight)
    _post(api, f"/grants/{grant_id}/timeline", {"to": _iso(last)})
    refused = _next_highlight(api, grant_id)
    assert refused.status_code == 409 and "No highlight" in refused.json()["detail"]
