"""The timeline player's database side and its routes (issue 165, first version)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

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
    assert [o["choice"] for o in options] == [
        "small_live",
        "larger_live",
        "larger_prerun",
        "larger_expected",
    ]
    assert [o["needs_confirm"] for o in options] == [False, True, False, False]
    assert [o["available"] for o in options] == [True, True, False, False]
    assert options[2]["unavailable_reason"] and options[3]["unavailable_reason"]
    assert options[0]["name"] == "Small sample, read live"


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


@pytest.mark.parametrize(
    ("choice", "sample"), [("small_live", "nitrate-sensors"), ("larger_live", "salt-marsh-carbon")]
)
def test_every_timeline_event_carries_its_highlight(api: Api, choice: str, sample: str) -> None:
    """Ruling 58: Just happened, Now and Coming up carry each event's highlight label, so
    the panel's Next highlight can find the next one."""
    from .test_pack import _labels

    labels = _labels(sample)
    timeline = _get(api, f"/grants/{_open(api, choice)}/timeline")
    played = [p["event"] for p in timeline["just_happened"]]
    shown = {e["name"]: e["highlight"] for e in [*played, *timeline["coming_up"]]}
    assert {n: h for n, h in shown.items() if h is not None} == labels
    first = timeline["now"]["stopped_on"]
    assert first["highlight"] == labels[first["name"]]
    coming = [e for e in timeline["coming_up"] if e["highlight"] is not None]
    assert [e["name"] for e in coming] == [n for n in labels if n != first["name"]]


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


def test_a_ledger_files_event_shows_what_the_agent_wrote_for_its_charges(api: Api) -> None:
    """A whole ledger file names no single charge: its event carries the charges it brought
    in, and what the agent wrote from their runs."""
    from app.contracts.records import Answer, Author, Judgment, Question, Record

    grant_id = _open(api)
    timeline = _move(api, grant_id)
    [ledger] = timeline["just_happened"]
    run_worker_until_idle(str(api.platform.pool.conninfo))
    with transaction(api.platform.pool) as conn:
        grant = store.get_grant(conn, grant_id)
        assert grant is not None
        brought = [
            c.id
            for c in store.list_charges(conn, grant_id, store.END_OF_TIME)
            if c.arrived_at == datetime(2026, 11, 16, 17, 45, tzinfo=UTC)
        ]
        [run] = [r for r in store.list_runs(conn, grant_id) if r.trigger.kind.value == "charge"]
        record = Record(
            id=f"rec-allowable-{grant_id[-6:]}",
            workspace_id=grant.workspace_id,
            grant_id=grant_id,
            author=Author.AGENT,
            written_at=run.clock_now,
            read_through_seq=run.read_through_seq,
            data=Judgment(
                charge_id=brought[0],
                question=Question.ALLOWABLE,
                text="Is this cost allowable?",
                answer=Answer.SUPPORTS,
                reasoning="Sensor parts for the project.",
            ),
        )
        store.insert_records(conn, [record])
    assert sorted(ledger["charge_ids"]) == sorted(brought)
    [ledger] = _get(api, f"/grants/{grant_id}/timeline")["just_happened"]
    assert [r["id"] for r in ledger["agent_records"]] == [record.id]


def test_a_jump_stores_each_event_at_its_own_time_and_replays_in_order(api: Api) -> None:
    grant_id = _open(api)
    timeline = _move(api, grant_id, "2026-11-17T00:00:00Z")
    assert timeline["now"]["stopped_on"] is None
    played = _names(timeline["just_happened"])
    assert played[:3] == ["ledger.csv", "invoice_EES-5531.pdf", "invoice_EES-6012.pdf"]
    files = {f.name: f.arrived_at for f in _files(api, grant_id)}
    assert files["invoice_EES-5531.pdf"] == datetime(2026, 11, 16, 17, 50, tzinfo=UTC)
    assert files["expense_report_valley-wells-2026.pdf"] == datetime(
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


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def test_the_users_items_wait_under_now_until_delivered(api: Api) -> None:
    pack = player.pack_for("nitrate-sensors")
    marked = [e for e in pack.events if e.deliver_by_user]  # in time order
    first, last = marked[0].at, max(i.at for i in player.items_for("nitrate-sensors"))
    names = [e.name for e in marked]
    grant_id = _open(api)
    timeline = _move(api, grant_id, _iso(first - timedelta(minutes=1)))
    assert timeline["now"]["deliveries"] == []
    upcoming = {e["name"]: e["kind"] for e in timeline["coming_up"]}
    assert all(upcoming[n] == "user_delivery" for n in names)

    # The clock stops on them and never delivers them.
    timeline = _move(api, grant_id)
    assert timeline["now"]["now"] == _iso(first)
    assert timeline["now"]["stopped_on"]["name"] in [e.name for e in pack.events if e.at == first]
    due = [e.name for e in marked if e.at <= first]
    assert [d["event"]["name"] for d in timeline["now"]["deliveries"]] == due
    assert not {pack.sha256(n) for n in names} & {f.sha256 for f in _files(api, grant_id)}
    end = last + timedelta(days=1)
    timeline = _move(api, grant_id, _iso(end))
    assert [d["event"]["name"] for d in timeline["now"]["deliveries"]] == names
    assert timeline["finished"] is True

    # The user uploads one the ordinary way: it leaves Now and shows under Just happened.
    item = marked[0]
    uploaded = api.client.post(
        f"/grants/{grant_id}/evidence",
        files={"file": ("my_copy", pack.file_bytes(item.name), "application/octet-stream")},
        headers=api.headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert [d["event"]["name"] for d in timeline["now"]["deliveries"]] == names[1:]
    delivered = [p for p in timeline["just_happened"] if p["event"]["name"] == item.name]
    assert delivered and delivered[0]["event"]["file_id"] == uploaded.json()["id"]
    # Only under the move that brought it: never again under a later one.
    later = _move(api, grant_id, _iso(end + timedelta(days=1)))
    assert item.name not in _names(later["just_happened"])


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


def _known_sender(api: Api, grant_id: str, email: str) -> None:
    """The accountant adds a known sender: a person term with the address."""
    response = _post(
        api,
        f"/grants/{grant_id}/records",
        {
            "data": {
                "kind": "person",
                "name": {"value": "A sender", "text": "A sender"},
                "email": {"value": email, "text": email},
                "role": {"value": "Known sender", "text": "Known sender"},
            }
        },
    )
    assert response.status_code == 201, response.text


def test_gmail_and_drive_events_arrive_as_those_channels_bring_them(api: Api) -> None:
    from app.ingest.email_files import parse_headers

    pack = player.pack_for("salt-marsh-carbon")
    gmail = next(e for e in pack.events if e.source.value == "gmail")
    drive = next(e for e in pack.events if e.source.value == "drive")
    raw = pack.file_bytes(gmail.name)
    sender = parse_headers(raw).sender
    assert sender is not None
    grant_id = _open(api, "larger_live")
    _known_sender(api, grant_id, sender)
    _move(api, grant_id, _iso(max(gmail.at, drive.at)))
    by_sha = {f.sha256: f for f in _files(api, grant_id)}
    email = by_sha[pack.sha256(gmail.name)]
    assert email.source is Source.GMAIL and email.sender == sender
    assert email.document_date is not None
    assert email.document_date == parse_headers(raw).sent_on  # its Date header, as written
    assert email.arrived_at == gmail.at
    stored = by_sha[pack.sha256(drive.name)]
    assert stored.source is Source.DRIVE and stored.source_ref and stored.arrived_at == drive.at


def test_an_email_from_a_sender_who_isnt_known_is_held(api: Api) -> None:
    """Ruling 58: a scheduled email goes through the known-sender hold as live mail does,
    and arrives once it's let in."""
    from app.ingest.email_files import parse_headers

    pack = player.pack_for("salt-marsh-carbon")
    gmail = next(e for e in pack.events if e.source.value == "gmail")
    grant_id = _open(api, "larger_live")  # nobody named in confirmed terms yet
    _move(api, grant_id, _iso(gmail.at))
    assert pack.sha256(gmail.name) not in {f.sha256 for f in _files(api, grant_id)}
    with transaction(api.platform.pool) as conn:
        grant = store.get_grant(conn, grant_id)
        assert grant is not None
        [held] = [
            h
            for h in store.list_held_mail(conn, grant.workspace_id, gmail.at)
            if h.grant_id == grant_id
        ]
    assert held.files[0].sha256 == pack.sha256(gmail.name)
    assert held.sender == parse_headers(pack.file_bytes(gmail.name)).sender
    assert held.held_at == gmail.at and held.reason.value == "unknown_sender"
    let_in = _post(
        api,
        f"/grants/{grant_id}/records",
        {"data": {"kind": "mail_action", "held_mail_id": held.id, "action": "let_in"}},
    )
    assert let_in.status_code == 201, let_in.text
    assert pack.sha256(gmail.name) in {f.sha256 for f in _files(api, grant_id)}


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


def test_two_copies_of_a_sample_in_one_workspace_each_take_their_ledger(api: Api) -> None:
    """Ruling 56: ledger line IDs are unique per grant, so a second copy plays as the first."""
    workspace_id = _workspace(api)
    first = _open(api, "small_live", workspace_id)
    second = _open(api, "small_live", workspace_id)
    for grant_id in (first, second):
        _move(api, grant_id, "2026-11-17T00:00:00Z")
    with transaction(api.platform.pool) as conn:
        lines = [
            sorted(c.ledger_line_id for c in store.list_charges(conn, g, store.END_OF_TIME))
            for g in (first, second)
        ]
    assert len(lines[0]) == 7 and lines[0] == lines[1]


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
    # Ruling 72: the panel says so before the user tries.
    held = _get(api, f"/grants/{other}/timeline")
    assert held["move_unavailable_reason"] == detail["message"]
    assert held["next_highlight_unavailable_reason"] == detail["message"]
    assert _get(api, f"/grants/{small}/timeline")["move_unavailable_reason"] is None
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
        "larger_expected",
    ]


def test_a_ledger_uploaded_early_doesnt_stop_the_timeline(api: Api) -> None:
    """Decision 0027: nothing is blocked. The user uploads the sample's ledger before its
    event; the event then reads it as an upload does, and skips the lines on file."""
    grant_id = _open(api)
    ledger = player.pack_for("nitrate-sensors").ledger_bytes()
    uploaded = api.client.post(
        f"/grants/{grant_id}/ledger",
        files={"file": ("ledger.csv", ledger, "text/csv")},
        headers=api.headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    timeline = _move(api, grant_id, "2026-11-17T00:00:00Z")
    assert "ledger.csv" in _names(timeline["just_happened"])
    with transaction(api.platform.pool) as conn:
        charges = store.list_charges(conn, grant_id, store.END_OF_TIME)
    assert len(charges) == 7  # each line once, as the user's upload brought it
    first = next(c for c in charges if c.ledger_line_id == "L-1958-0001")
    assert first.arrived_at == SMALL_START


def _blocked(api: Api, take: Any) -> bool:
    """Whether `take(conn)` waits for a lock another transaction holds."""
    from psycopg.errors import LockNotAvailable

    with api.platform.pool.connection() as conn:
        conn.execute("set lock_timeout = '200ms'")
        try:
            take(conn)
        except LockNotAvailable:
            conn.rollback()
            return True
        conn.rollback()
        return False


def test_one_move_at_a_time_per_user(api: Api) -> None:
    from app.db import sample_store

    with transaction(api.platform.pool) as held:
        sample_store.lock_users_moves(held, api.user_id)
        assert _blocked(api, lambda conn: sample_store.lock_users_moves(conn, api.user_id))
        assert not _blocked(api, lambda conn: sample_store.lock_users_moves(conn, "someone-else"))
    assert not _blocked(api, lambda conn: sample_store.lock_users_moves(conn, api.user_id))


def test_next_highlight_on_the_route_waits_for_the_opening_highlights_step(api: Api) -> None:
    """Rulings 77 and 86, on the sample as it is: the award letter (highlight 1) is played
    at the opening, and its own step, confirming its terms, comes due before the next
    highlight. The first press stops there and holds it; Next highlight then waits for the
    user, saying why; once the user confirms, it goes on to the receipt. `to` is ignored."""
    from app.samples.script import WriteRecord, resolve

    pack = player.pack_for("nitrate-sensors")
    confirm = next(a for a in pack.actions if a.action == "confirm_terms")
    receipt = next(e for e in pack.events if e.deliver_by_user and e.highlight)
    assert confirm.highlight is not None
    grant_id = _open(api)  # on the award letter, the first highlight
    _reading(api, grant_id)
    first = _post(
        api,
        f"/grants/{grant_id}/timeline",
        {"next_highlight": True, "to": "2027-06-01T00:00:00Z"},
    )
    assert first.status_code == 200, first.text
    run_worker_until_idle(str(api.platform.pool.conninfo))  # the walk waits on the agent
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert timeline["now"]["now"] == _iso(confirm.at)
    reason = f"Confirm the terms read from {confirm.file} first: that's this highlight's step."
    assert timeline["next_highlight_unavailable_reason"] == reason
    refused = _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True})
    assert refused.status_code == 409 and refused.json()["detail"] == reason
    with transaction(api.platform.pool) as conn:
        grant = store.get_grant(conn, grant_id)
        assert grant is not None
        step = resolve(api.platform, conn, grant, pack, confirm, confirm.at)
    assert isinstance(step, WriteRecord)
    confirmed = _post(api, f"/grants/{grant_id}/records", {"data": step.data})
    assert confirmed.status_code == 201, confirmed.text
    assert _get(api, f"/grants/{grant_id}/timeline")["next_highlight_unavailable_reason"] is None
    second = _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True})
    assert second.status_code == 200, second.text
    run_worker_until_idle(str(api.platform.pool.conninfo))
    timeline = _get(api, f"/grants/{grant_id}/timeline")
    assert timeline["now"]["now"] == _iso(receipt.at)
    assert timeline["now"]["stopped_on"]["highlight"] == receipt.highlight


def _reading(api: Api, grant_id: str) -> None:
    """The agent, faked by the small sample's agent_records.json."""
    from tests.samples.test_skipping import _records_agent

    _records_agent(api, player.pack_for("nitrate-sensors"), grant_id)


def test_the_move_controls_say_why_they_cant_move(api: Api) -> None:
    """Ruling 72, in plain words; None while a control can move."""
    items = player.items_for("nitrate-sensors")
    grant_id = _open(api)
    opened = _get(api, f"/grants/{grant_id}/timeline")
    assert opened["move_unavailable_reason"] is None
    assert opened["next_highlight_unavailable_reason"] is None
    last_highlight = max(i.at for i in items if i.event and i.event.highlight)
    at_last = _move(api, grant_id, _iso(last_highlight))
    assert at_last["next_highlight_unavailable_reason"] == "No highlight is left to play."
    refused = _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True})
    assert refused.status_code == 409
    assert refused.json()["detail"] == "No highlight is left to play."
    end = _move(api, grant_id, "2030-01-01T00:00:00Z")
    assert end["move_unavailable_reason"] == "Nothing is left to play."
    assert end["next_highlight_unavailable_reason"] == "No highlight is left to play."


def test_the_view_guides_through_the_highlights(api: Api) -> None:
    """The timeline guide's data: the highlight reached, of how many, the user's step it
    waits for and what to open for it, and the scripted sign-off's date."""
    pack = player.pack_for("nitrate-sensors")
    labelled = [e for e in pack.events if e.highlight]
    grant_id = _open(api)
    _reading(api, grant_id)
    opening = _get(api, f"/grants/{grant_id}/timeline")
    assert (opening["highlight_index"], opening["highlight_total"]) == (1, len(labelled))
    assert opening["highlight_event"]["name"] == labelled[0].name
    assert opening["your_step"] is None and opening["sign_off_at"] is None
    moved = _post(api, f"/grants/{grant_id}/timeline", {"next_highlight": True})
    assert moved.status_code == 200, moved.text
    run_worker_until_idle(str(api.platform.pool.conninfo))
    waiting = _get(api, f"/grants/{grant_id}/timeline")
    assert waiting["your_step"] == {"action": "confirm_terms", "open": "terms", "id": None}
    larger = _open(api, "larger_live")
    assert _get(api, f"/grants/{larger}/timeline")["sign_off_at"] is not None
