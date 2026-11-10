""" "Deliver for me", "Get the file" and start over on a sample grant (issue 165, first
version)."""

from __future__ import annotations

import pytest

from app.contracts.evidence import Source
from app.contracts.runs import RunStatus
from app.db import jobs, store
from app.db.pool import transaction
from app.db.ports import AgentInput, AgentResult
from app.samples import player
from app.samples.pack import EventKind, event_id
from tests.api.conftest import Api
from tests.db.platform_fixtures import FakeAgent, FakeStorage, run_worker_until_idle

from .test_player import SMALL_START, _files, _get, _move, _names, _open, _post

RECEIPT = event_id(EventKind.FILE, "hardware_receipt.jpg")
LETTER = event_id(EventKind.FILE, "award_letter.pdf")


def _at_the_receipts_date(api: Api) -> str:
    grant_id = _open(api)
    _move(api, grant_id, "2026-11-18T17:00:00Z")
    return grant_id


# Deliver for me.


def test_deliver_for_me_brings_the_item_in_as_the_users_upload(api: Api) -> None:
    grant_id = _at_the_receipts_date(api)
    response = _post(api, f"/grants/{grant_id}/timeline/deliveries/{RECEIPT}", None)
    assert response.status_code == 200, response.text
    timeline = response.json()
    assert "hardware_receipt.jpg" not in [d["event"]["name"] for d in timeline["now"]["deliveries"]]
    [shown] = [p for p in timeline["just_happened"] if p["event"]["name"] == "hardware_receipt.jpg"]
    # The user's own delivery, "Deliver for me" included (ruling 52).
    assert shown["delivered_by_sample_accountant"] is False
    [receipt] = [f for f in _files(api, grant_id) if f.name == "hardware_receipt.jpg"]
    assert shown["event"]["file_id"] == receipt.id
    assert receipt.source is Source.UPLOAD and receipt.media_type == "image/jpeg"
    assert receipt.arrived_at.isoformat() == "2026-11-18T17:00:00+00:00"
    with transaction(api.platform.pool) as conn:
        runs = [r for r in store.list_runs(conn, grant_id) if r.trigger.id == receipt.id]
    assert len(runs) == 1


def test_an_item_already_delivered_isnt_delivered_again(api: Api) -> None:
    grant_id = _at_the_receipts_date(api)
    path = f"/grants/{grant_id}/timeline/deliveries/{RECEIPT}"
    assert _post(api, path, None).status_code == 200
    again = _post(api, path, None)
    assert again.status_code == 409 and "already on the grant" in again.json()["detail"]
    assert [f.name for f in _files(api, grant_id)].count("hardware_receipt.jpg") == 1


def test_only_the_users_items_can_be_delivered_or_fetched(api: Api) -> None:
    grant_id = _at_the_receipts_date(api)
    for item in (LETTER, "no-such-event"):
        assert _post(api, f"/grants/{grant_id}/timeline/deliveries/{item}", None).status_code == 404
        file = api.client.get(
            f"/grants/{grant_id}/timeline/deliveries/{item}/file", headers=api.headers
        )
        assert file.status_code == 404


# Get the file.


def test_get_the_file_gives_a_short_lived_link_to_the_original(api: Api) -> None:
    grant_id = _open(api)
    path = f"/grants/{grant_id}/timeline/deliveries/{RECEIPT}/file"
    link = _get(api, path)
    pack = player.pack_for("nitrate-sensors")
    staged = f"samples/nitrate-sensors/{pack.sha256('hardware_receipt.jpg')}/hardware_receipt.jpg"
    assert staged in link["url"] and link["media_type"] == "image/jpeg" and link["expires_at"]
    storage = api.platform.storage
    assert isinstance(storage, FakeStorage)
    assert storage.objects[staged][0] == pack.file_bytes("hardware_receipt.jpg")
    # Staged once: asking again (here or on another grant) doesn't store it again.
    assert _get(api, path)["url"] == link["url"]
    player._STAGED.clear()  # pyright: ignore[reportPrivateUsage] - as a new process would
    assert staged in _get(api, path)["url"]


# Start over.


def test_start_over_needs_the_confirm(api: Api) -> None:
    grant_id = _open(api)
    refused = _post(api, f"/grants/{grant_id}/timeline/start-over", {"confirmed": False})
    assert refused.status_code == 409 and refused.json()["detail"]["reason"] == "needs_confirm"


def test_start_over_resets_that_one_grant(api: Api) -> None:
    grant_id = _at_the_receipts_date(api)
    other = _open(api)
    _post(api, f"/grants/{grant_id}/timeline/deliveries/{RECEIPT}", None)
    with transaction(api.platform.pool) as conn:
        grant = store.get_grant(conn, grant_id)
        assert grant is not None
        conn.execute(
            "update public.grants set award_number = 'SYN-2511958', address_code = 'k3y'"
            " where id = %s",
            (grant_id,),
        )
    response = _post(api, f"/grants/{grant_id}/timeline/start-over", {"confirmed": True})
    assert response.status_code == 200, response.text
    timeline = response.json()
    assert timeline["now"]["now"] == "2026-11-16T17:30:00Z"
    assert _names(timeline["just_happened"]) == ["award_letter.pdf"]
    assert [f.name for f in _files(api, grant_id)] == ["award_letter.pdf"]
    with transaction(api.platform.pool) as conn:
        fresh = store.get_grant(conn, grant_id)
        charges = store.list_charges(conn, grant_id, store.END_OF_TIME)
        runs = store.list_runs(conn, grant_id)
        queued = conn.execute(
            "select count(*) as n from procrastinate_jobs where lock = %s and status = 'todo'",
            (jobs.grant_lock(grant_id),),
        ).fetchone()
    assert fresh is not None and fresh.clock_now == SMALL_START
    assert fresh.sample == grant.sample and fresh.workspace_id == grant.workspace_id
    assert fresh.award_number is None and fresh.address_code == "k3y"
    assert charges == []
    assert [(r.trigger.kind.value, r.clock_now) for r in runs] == [("file", SMALL_START)]
    assert queued is not None and queued["n"] == 1
    # The other sample grant is untouched.
    assert len(_files(api, other)) == 1
    assert _get(api, f"/grants/{other}/timeline")["now"]["now"] == "2026-11-16T17:30:00Z"


def test_a_run_in_progress_saves_nothing_into_the_fresh_copy(api: Api) -> None:
    grant_id = _open(api)
    agent = api.platform.agent
    assert isinstance(agent, FakeAgent)
    seen: list[str] = []

    def behave(i: AgentInput) -> AgentResult:
        seen.append(i.run.id)
        if len(seen) == 1:
            # The user starts over while the agent reads the letter.
            with transaction(api.platform.pool) as conn:
                grant = store.get_grant(conn, grant_id)
            assert grant is not None
            player.start_over(api.platform, grant)
            return AgentResult(summary="read before the start over")
        return AgentResult(summary="read after")

    agent.behave = behave
    run_worker_until_idle(str(api.platform.pool.conninfo))
    with transaction(api.platform.pool) as conn:
        runs = store.list_runs(conn, grant_id)
    assert len(seen) == 2 and seen[0] not in {r.id for r in runs}
    assert [(r.status, r.summary) for r in runs] == [(RunStatus.DONE, "read after")]


def test_save_run_refuses_a_run_whose_row_is_gone(api: Api) -> None:
    grant_id = _open(api)
    with transaction(api.platform.pool) as conn:
        [run] = store.list_runs(conn, grant_id)
        conn.execute("delete from public.agent_runs where id = %s", (run.id,))
    with pytest.raises(jobs.RunGone), transaction(api.platform.pool) as conn:
        jobs.save_run(api.platform, conn, run, AgentResult())
