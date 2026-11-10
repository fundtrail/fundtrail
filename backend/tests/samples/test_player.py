"""The timeline player's database side and its routes (issue 165, first version)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from app.contracts.evidence import Source
from app.contracts.runs import TriggerKind
from app.db import store
from app.db.pool import transaction
from app.samples import player
from tests.api.conftest import Api
from tests.db.platform_fixtures import run_worker_until_idle

SMALL_START = datetime(2026, 11, 16, 17, 30, tzinfo=UTC)
LARGER_START = datetime(2024, 1, 18, 17, tzinfo=UTC)


def _post(api: Api, path: str, body: Any, headers: dict[str, str] | None = None) -> Any:
    return api.client.post(path, json=body, headers=headers or api.headers)


def _get(api: Api, path: str) -> Any:
    response = api.client.get(path, headers=api.headers)
    assert response.status_code == 200, response.text
    return response.json()


def _workspace(api: Api, headers: dict[str, str] | None = None) -> str:
    response = _post(api, "/workspaces", {"name": "Lab"}, headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _open(api: Api, choice: str = "small_live", workspace_id: str | None = None) -> str:
    workspace_id = workspace_id or _workspace(api)
    body = {"choice": choice, "confirmed": choice == "larger_live"}
    response = _post(api, f"/workspaces/{workspace_id}/samples", body)
    assert response.status_code == 201, response.text
    return response.json()["grant"]["id"]


def _move(api: Api, grant_id: str, to: str | None = None) -> Any:
    response = _post(api, f"/grants/{grant_id}/timeline", {"to": to})
    assert response.status_code == 200, response.text
    return response.json()


def _names(events: list[dict[str, Any]]) -> list[str]:
    return [e["event"]["name"] if "event" in e else e["name"] for e in events]


def _files(api: Api, grant_id: str) -> list[Any]:
    with transaction(api.platform.pool) as conn:
        return store.list_files(conn, grant_id, store.END_OF_TIME)


# The choices.


def test_the_choices_come_from_the_packs(api: Api) -> None:
    options = _get(api, "/samples")
    assert [o["choice"] for o in options] == ["small_live", "larger_live", "larger_prerun"]
    assert [o["needs_confirm"] for o in options] == [False, True, False]
    assert [o["available"] for o in options] == [True, True, False]
    assert options[2]["unavailable_reason"]
    assert options[0]["name"].startswith("Placeholder")


def test_the_larger_live_sample_needs_a_confirm(api: Api) -> None:
    workspace_id = _workspace(api)
    response = _post(api, f"/workspaces/{workspace_id}/samples", {"choice": "larger_live"})
    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "needs_confirm"
    prerun = _post(api, f"/workspaces/{workspace_id}/samples", {"choice": "larger_prerun"})
    assert prerun.status_code == 422


# Opening and moving.


def test_a_sample_opens_at_its_first_event(api: Api) -> None:
    workspace_id = _workspace(api)
    response = _post(api, f"/workspaces/{workspace_id}/samples", {"choice": "small_live"})
    assert response.status_code == 201, response.text
    summary = response.json()
    grant_id = summary["grant"]["id"]
    assert summary["now"] == "2026-11-16T17:30:00Z"
    assert summary["grant"]["sample"] == {"sample": "nitrate-sensors", "choice": "small_live"}
    assert summary["grant"]["clock_now"] == "2026-11-16T17:30:00Z"

    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert _names(timeline["just_happened"]) == ["award_letter.pdf"]
    assert timeline["now"]["stopped_on"]["name"] == "award_letter.pdf"
    assert timeline["now"]["now"] == "2026-11-16T17:30:00Z"
    assert timeline["coming_up"][0]["name"] == "ledger.csv"
    assert timeline["catching_up"] is True and timeline["finished"] is False

    [letter] = _files(api, grant_id)
    assert (letter.name, letter.source, letter.arrived_at) == (
        "award_letter.pdf",
        Source.UPLOAD,
        SMALL_START,
    )
    assert timeline["just_happened"][0]["event"]["file_id"] == letter.id
    with transaction(api.platform.pool) as conn:
        [run] = store.list_runs(conn, grant_id)
    assert (run.trigger.kind, run.trigger.id, run.clock_now) == (
        TriggerKind.FILE,
        letter.id,
        SMALL_START,
    )


def test_next_plays_the_ledger_and_its_later_lines_wait(api: Api) -> None:
    grant_id = _open(api)
    timeline = _move(api, grant_id)
    assert timeline["now"]["now"] == "2026-11-16T17:45:00Z"
    assert _names(timeline["just_happened"]) == ["ledger.csv"]
    with transaction(api.platform.pool) as conn:
        charges = store.list_charges(conn, grant_id, store.END_OF_TIME)
    arrived = {c.ledger_line_id: c.arrived_at for c in charges}
    assert len(arrived) == 7
    assert arrived["L-1958-0001"] == datetime(2026, 11, 16, 17, 45, tzinfo=UTC)
    assert arrived["L-1958-0006"] == datetime(2026, 11, 24, tzinfo=UTC)
    assert arrived["L-1958-0007"] == datetime(2026, 12, 7, tzinfo=UTC)
    upcoming = _names(timeline["coming_up"])
    assert "L-1958-0006" in upcoming and "ledger.csv" not in upcoming


def test_a_jump_stores_each_event_at_its_own_time_and_replays_in_order(api: Api) -> None:
    grant_id = _open(api)
    timeline = _move(api, grant_id, "2026-11-17T00:00:00Z")
    assert timeline["now"]["stopped_on"] is None
    played = _names(timeline["just_happened"])
    assert played[:3] == ["ledger.csv", "invoice_EES-5531.pdf", "invoice_EES-6012.pdf"]
    files = {f.name: f.arrived_at for f in _files(api, grant_id)}
    assert files["invoice_EES-5531.pdf"] == datetime(2026, 11, 16, 17, 50, tzinfo=UTC)
    assert files["expense_report_valley-wells-2026.txt"] == datetime(
        2026, 11, 16, 17, 55, tzinfo=UTC
    )
    with transaction(api.platform.pool) as conn:
        runs = {r.id: r for r in store.list_runs(conn, grant_id)}
        jobs = conn.execute("select args from procrastinate_jobs order by id").fetchall()
    # The catch-up runs are queued in arrival order, each as of its own arrival.
    times = [runs[j["args"]["run_id"]].clock_now for j in jobs if j["args"]["run_id"] in runs]
    assert len(times) == len(runs) and times == sorted(times)
    assert times[0] == SMALL_START  # the award letter's run, from opening
    run_worker_until_idle(str(api.platform.pool.conninfo))
    assert _get(api, f"/grants/{grant_id}/timeline")["catching_up"] is False


def test_the_users_items_wait_under_now_until_delivered(api: Api) -> None:
    grant_id = _open(api)
    timeline = _move(api, grant_id, "2026-11-18T16:00:00Z")
    assert timeline["now"]["deliveries"] == []
    marked = ["email_invoice_ESS-32410.eml", "hardware_receipt.jpg", "invoice_EES-7420.pdf"]
    assert [e["name"] for e in timeline["coming_up"][:3]] == marked
    assert {e["kind"] for e in timeline["coming_up"][:3]} == {"user_delivery"}

    # The clock stops on them once and never delivers them.
    timeline = _move(api, grant_id)
    assert timeline["now"]["now"] == "2026-11-18T17:00:00Z"
    assert timeline["now"]["stopped_on"]["name"] == marked[0]
    assert [d["event"]["name"] for d in timeline["now"]["deliveries"]] == marked
    assert not {f.name for f in _files(api, grant_id)} & set(marked)
    timeline = _move(api, grant_id, "2026-12-31T00:00:00Z")
    assert [d["event"]["name"] for d in timeline["now"]["deliveries"]] == marked
    assert timeline["finished"] is True

    # The user uploads one the ordinary way: it leaves Now and shows under Just happened.
    from app.samples.player import pack_for

    receipt = pack_for("nitrate-sensors").file_bytes("hardware_receipt.jpg")
    uploaded = api.client.post(
        f"/grants/{grant_id}/evidence",
        files={"file": ("my_photo.jpg", receipt, "image/jpeg")},
        headers=api.headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert [d["event"]["name"] for d in timeline["now"]["deliveries"]] == [marked[0], marked[2]]
    delivered = [p for p in timeline["just_happened"] if p["event"]["name"] == marked[1]]
    assert delivered and delivered[0]["event"]["file_id"] == uploaded.json()["id"]
    # Only under the move that brought it: never again under a later one.
    later = _move(api, grant_id, "2027-01-02T00:00:00Z")
    assert marked[1] not in _names(later["just_happened"])


def test_the_timeline_only_moves_forward(api: Api) -> None:
    grant_id = _open(api)
    back = _post(api, f"/grants/{grant_id}/timeline", {"to": "2026-01-01T00:00:00Z"})
    assert back.status_code == 409 and "forward" in back.json()["detail"]
    timeline = _move(api, grant_id, "2027-01-01T00:00:00Z")
    assert timeline["finished"] is True
    # Only dates the checks work out are left; "next" steps through them, then stops.
    done, steps = _post(api, f"/grants/{grant_id}/timeline", {}), 0
    while done.status_code == 200 and steps < 10:
        assert {e["kind"] for e in done.json()["coming_up"]} <= {"checks_date"}
        done, steps = _post(api, f"/grants/{grant_id}/timeline", {}), steps + 1
    assert done.status_code == 409 and "Nothing" in done.json()["detail"]


def test_gmail_and_drive_events_arrive_as_those_channels_bring_them(api: Api) -> None:
    grant_id = _open(api, "larger_live")
    _move(api, grant_id, "2024-09-06T00:00:00Z")
    files = {f.name: f for f in _files(api, grant_id)}
    email = next(f for f in files.values() if f.source is Source.GMAIL)
    assert email.sender == "harper.fixture@university.example"
    assert email.document_date == date(2024, 5, 14)  # its Date header, as written
    assert email.arrived_at == datetime(2024, 5, 14, 20, 5, tzinfo=UTC)
    drive = files["usage_statement_SIF-2408-77.txt"]
    assert drive.source is Source.DRIVE and drive.source_ref


def test_a_grant_that_isnt_a_sample_has_no_timeline(api: Api) -> None:
    workspace_id = _workspace(api)
    created = api.client.post(
        f"/workspaces/{workspace_id}/grants",
        files={"file": ("award_letter.txt", b"Award SYN-2300117", "text/plain")},
        headers=api.headers,
    )
    grant_id = created.json()["id"]
    assert api.client.get(f"/grants/{grant_id}/timeline", headers=api.headers).status_code == 404
    assert _post(api, f"/grants/{grant_id}/timeline", {}).status_code == 404


def test_another_users_sample_is_404(api: Api, signer: Any) -> None:
    grant_id = _open(api)
    other = api.as_other_user(signer)
    assert api.client.get(f"/grants/{grant_id}/timeline", headers=other).status_code == 404
    assert _post(api, f"/grants/{grant_id}/timeline", {}, other).status_code == 404


def test_a_second_copy_of_a_sample_in_one_workspace_is_refused(api: Api) -> None:
    workspace_id = _workspace(api)
    _open(api, "small_live", workspace_id)
    again = _post(api, f"/workspaces/{workspace_id}/samples", {"choice": "small_live"})
    assert again.status_code == 422 and "already has this sample" in again.json()["detail"][0]


# The read-live limit (ruling 48, first version).


def test_a_larger_live_sample_still_reading_holds_another_ones_clock(api: Api) -> None:
    working = _open(api, "larger_live")  # its letter's run is queued
    other = _open(api, "larger_live")
    small = _open(api, "small_live")
    refused = _post(api, f"/grants/{other}/timeline", {})
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["reason"] == "another_sample_working"
    assert detail["grant"]["grant"]["id"] == working
    # A small sample is never held.
    assert _post(api, f"/grants/{small}/timeline", {}).status_code == 200
    # Opening is never refused for it.
    _open(api, "larger_live")
    run_worker_until_idle(str(api.platform.pool.conninfo))
    assert _post(api, f"/grants/{other}/timeline", {}).status_code == 200


def test_the_limit_is_per_user(api: Api, signer: Any) -> None:
    _open(api, "larger_live")
    headers = api.as_other_user(signer)
    workspace_id = _workspace(api, headers)
    body = {"choice": "larger_live", "confirmed": True}
    created = _post(api, f"/workspaces/{workspace_id}/samples", body, headers)
    assert created.status_code == 201, created.text
    theirs = created.json()["grant"]["id"]
    assert _post(api, f"/grants/{theirs}/timeline", {}, headers).status_code == 200


def test_options_are_in_the_contracts_order() -> None:
    assert [o.choice.value for o in player.options()] == [
        "small_live",
        "larger_live",
        "larger_prerun",
    ]
