import hashlib
from datetime import UTC, datetime
from typing import Any

from app.contracts.fixtures import LEDGER_FILE
from app.contracts.records import BudgetCategory
from tests.api.conftest import Api
from tests.db.platform_fixtures import FakeChecks, FakePinger, FakeStorage


def _workspace(api: Api) -> dict[str, Any]:
    response = api.client.post("/workspaces", json={"name": "Lab"}, headers=api.headers)
    assert response.status_code == 201
    return response.json()


def _grant(api: Api, workspace_id: str) -> dict[str, Any]:
    response = api.client.post(
        f"/workspaces/{workspace_id}/grants",
        files={"file": ("award_letter.txt", b"Award SYN-2300117", "text/plain")},
        headers=api.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _set_clock(api: Api, workspace_id: str, now: datetime) -> None:
    with api.platform.pool.connection() as conn:
        conn.execute(
            "update public.grants set clock_now = %s where workspace_id = %s", (now, workspace_id)
        )


def _ledger(api: Api, grant_id: str, content: bytes) -> Any:
    return api.client.post(
        f"/grants/{grant_id}/ledger",
        files={"file": ("ledger.csv", content, "text/csv")},
        headers=api.headers,
    )


def test_workspaces_are_created_and_listed(api: Api) -> None:
    workspace = _workspace(api)
    assert workspace["name"] == "Lab" and "clock_now" not in workspace
    assert workspace["owner_id"] == api.user_id
    assert api.client.get("/workspaces", headers=api.headers).json() == [workspace]


def test_a_grant_from_its_award_letter_stores_the_letter_and_queues_a_run(api: Api) -> None:
    workspace = _workspace(api)
    grant = _grant(api, workspace["id"])
    assert grant["workspace_id"] == workspace["id"]
    assert grant["award_number"] is None and grant["title"] is None

    storage = api.platform.storage
    assert isinstance(storage, FakeStorage)
    [(path, (data, media_type))] = storage.objects.items()
    assert path.startswith(f"{workspace['id']}/{grant['id']}/") and path.endswith(
        "/award_letter.txt"
    )
    assert (data, media_type) == (b"Award SYN-2300117", "text/plain")

    [run] = api.client.get(f"/grants/{grant['id']}/runs", headers=api.headers).json()
    assert run["status"] == "queued" and run["trigger"]["kind"] == "file"
    with api.platform.pool.connection() as conn:
        job = conn.execute("select lock, priority, args from procrastinate_jobs").fetchone()
    assert job is not None
    assert job["lock"] == f"grant:{grant['id']}" and job["priority"] == 0
    assert job["args"]["run_id"] == run["id"]
    pinger = api.platform.pinger
    assert isinstance(pinger, FakePinger)
    assert ("workspace:" + workspace["id"], "changed", {"grant_id": grant["id"]}) in pinger.pings


def test_a_ledger_upload_adds_new_lines_once_and_reports_bad_rows(api: Api) -> None:
    grant = _grant(api, _workspace(api)["id"])
    content = LEDGER_FILE.read_bytes()
    assert _ledger(api, grant["id"], content).json() == {
        "added": 2,
        "already_present": 0,
        "rejected": [],
    }
    bad = content + b"L-1003,2026-02-30,2026-03-01,12.5x,Bad row,55016 Lab,,,\n"
    result = _ledger(api, grant["id"], bad).json()
    assert result["added"] == 0 and result["already_present"] == 2
    [error] = result["rejected"]
    assert error["row"] == 4 and "transaction_date" in error["message"]

    runs = api.client.get(f"/grants/{grant['id']}/runs", headers=api.headers).json()
    # Both lines arrived at the same moment, so one run covers them.
    assert sorted(r["trigger"]["kind"] for r in runs) == ["charge", "file"]


def test_a_file_that_isnt_a_ledger_is_a_422(api: Api) -> None:
    grant = _grant(api, _workspace(api)["id"])
    response = _ledger(api, grant["id"], b"name,total\nx,1\n")
    assert response.status_code == 422
    assert "missing required columns" in response.json()["detail"][0]


def test_charges_come_with_status_budget_line_and_account_categories(api: Api) -> None:
    workspace = _workspace(api)
    grant = _grant(api, workspace["id"])
    _ledger(api, grant["id"], LEDGER_FILE.read_bytes())
    rows = api.client.get(f"/grants/{grant['id']}/charges", headers=api.headers).json()
    assert [r["charge"]["ledger_line_id"] for r in rows] == ["L-1001", "L-1002"]
    assert rows[0]["status"]["bucket"] == "evidence_complete"
    assert rows[0]["account_categories"] == [BudgetCategory.MATERIALS_AND_SUPPLIES.value]
    assert rows[1]["account_categories"] == []
    assert rows[0]["budget_line"] is None

    line = _post_record(
        api,
        grant["id"],
        {
            "kind": "budget_line",
            "dated": {"value": "2023-01-10"},
            "name": {"value": "Materials and Supplies"},
            "amount": {"value": 4000000},
            "category": "materials_and_supplies",
        },
    )
    assert line.status_code == 201, line.text
    assignment = _post_record(
        api,
        grant["id"],
        {
            "kind": "budget_assignment",
            "charge_id": rows[0]["charge"]["id"],
            "record_id": line.json()["id"],
            "reason": "Lab supplies",
        },
    )
    assert assignment.status_code == 201, assignment.text
    rows = api.client.get(f"/grants/{grant['id']}/charges", headers=api.headers).json()
    assert rows[0]["budget_line"]["id"] == line.json()["id"]


def test_the_clock_hides_charges_that_havent_arrived(api: Api) -> None:
    workspace = _workspace(api)
    grant = _grant(api, workspace["id"])
    _set_clock(api, workspace["id"], datetime(2025, 12, 1, tzinfo=UTC))
    _ledger(api, grant["id"], LEDGER_FILE.read_bytes())
    rows = api.client.get(f"/grants/{grant['id']}/charges", headers=api.headers).json()
    assert [r["charge"]["ledger_line_id"] for r in rows] == ["L-1001"]
    runs = api.client.get(f"/grants/{grant['id']}/runs", headers=api.headers).json()
    assert [r["trigger"]["kind"] for r in runs].count("charge") == 1


def _post_record(api: Api, grant_id: str, data: dict[str, Any], replaces_id: str | None = None):
    return api.client.post(
        f"/grants/{grant_id}/records",
        json={"data": data, "replaces_id": replaces_id},
        headers=api.headers,
    )


def test_a_term_added_without_a_date_is_dated_by_the_clock(api: Api) -> None:
    workspace = _workspace(api)
    grant = _grant(api, workspace["id"])
    _set_clock(api, workspace["id"], datetime(2026, 4, 10, 17, tzinfo=UTC))
    response = _post_record(
        api,
        grant["id"],
        {
            "kind": "person",
            "name": {"value": "Lee Example"},
            "email": {"value": "lee.example@university.example"},
            "role": {"value": "Lab manager"},
        },
    )
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["data"]["dated"]["value"] == "2026-04-10"
    assert record["author"] == "user" and record["author_user_id"] == api.user_id
    assert record["written_at"] == "2026-04-10T17:00:00Z"
    assert api.client.get(f"/grants/{grant['id']}/records", headers=api.headers).json() == [record]
    checks = api.platform.checks
    assert isinstance(checks, FakeChecks)
    assert checks.calls[-1].records[-1].id == record["id"]


def test_a_term_with_its_own_date_keeps_it(api: Api) -> None:
    grant = _grant(api, _workspace(api)["id"])
    data = {
        "kind": "other_term",
        "dated": {"value": "2025-06-01"},
        "label": "PI on leave",
        "statement": {"value": "The PI is on leave in July."},
    }
    response = _post_record(api, grant["id"], data)
    assert response.json()["data"]["dated"]["value"] == "2025-06-01"


def test_a_write_the_write_check_rejects_is_a_422_with_its_problems(api: Api) -> None:
    grant = _grant(api, _workspace(api)["id"])
    response = _post_record(
        api,
        grant["id"],
        {"kind": "budget_assignment", "charge_id": "nope", "record_id": "nope", "reason": "x"},
    )
    assert response.status_code == 422
    problems = response.json()["detail"]
    assert problems and all(isinstance(p, str) for p in problems)
    assert api.client.get(f"/grants/{grant['id']}/records", headers=api.headers).json() == []


def test_a_record_the_contracts_refuse_is_a_422(api: Api) -> None:
    grant = _grant(api, _workspace(api)["id"])
    response = _post_record(api, grant["id"], {"kind": "no_such_kind"})
    assert response.status_code == 422


def test_a_record_that_leaves_a_question_for_the_agent_queues_a_run(api: Api) -> None:
    grant = _grant(api, _workspace(api)["id"])
    checks = api.platform.checks
    assert isinstance(checks, FakeChecks)
    data = {"kind": "other_term", "label": "Note", "statement": {"value": "Something."}}
    checks.agent_questions = True
    _ledger(api, grant["id"], LEDGER_FILE.read_bytes())

    def runs() -> list[dict[str, Any]]:
        return api.client.get(f"/grants/{grant['id']}/runs", headers=api.headers).json()

    def set_status(status: str) -> None:
        with api.platform.pool.connection() as conn:
            conn.execute(
                "update public.agent_runs set status = %s where grant_id = %s",
                (status, grant["id"]),
            )

    # A queued run that hasn't started reads the new record when it starts, so it's shared.
    before = len(runs())
    _post_record(api, grant["id"], data)
    assert len(runs()) == before
    # With a run in progress and none queued, the record queues one to run after it.
    set_status("done")
    with api.platform.pool.connection() as conn:
        conn.execute(
            "update public.agent_runs set status = 'running' where id = %s", (runs()[0]["id"],)
        )
    record = _post_record(api, grant["id"], data).json()
    assert runs()[0]["trigger"] == {"kind": "record", "id": record["id"]}
    # On a quiet grant, likewise.
    set_status("done")
    record = _post_record(api, grant["id"], data).json()
    assert runs()[0]["trigger"] == {"kind": "record", "id": record["id"]}


def test_evidence_upload_and_its_content_link(api: Api) -> None:
    grant = _grant(api, _workspace(api)["id"])
    response = api.client.post(
        f"/grants/{grant['id']}/evidence",
        files={"file": ("invoice 1001.txt", b"INVOICE INV-1001", "text/plain")},
        headers=api.headers,
    )
    assert response.status_code == 201, response.text
    f = response.json()
    assert f["source"] == "upload" and f["name"] == "invoice 1001.txt"
    assert f["sha256"] == hashlib.sha256(b"INVOICE INV-1001").hexdigest()
    link = api.client.get(f"/evidence/{f['id']}/content", headers=api.headers).json()
    assert link["url"].endswith(f"{f['storage_path']}?token=fake&ttl=300")
    assert api.client.get("/evidence/missing/content", headers=api.headers).status_code == 404


def test_every_422_from_the_records_route_is_a_list_of_sentences(api: Api) -> None:
    grant = _grant(api, _workspace(api)["id"])
    for body in ({"data": {"kind": "no_such_kind"}}, {"nothing": 1}):
        response = api.client.post(f"/grants/{grant['id']}/records", json=body, headers=api.headers)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail and all(isinstance(p, str) for p in detail)


def test_an_upload_over_the_limit_is_refused(api: Api, monkeypatch: Any) -> None:
    from app.api import routes

    grant = _grant(api, _workspace(api)["id"])
    monkeypatch.setattr(routes, "MAX_UPLOAD_BYTES", 10)
    response = api.client.post(
        f"/grants/{grant['id']}/evidence",
        files={"file": ("big.txt", b"x" * 11, "text/plain")},
        headers=api.headers,
    )
    assert response.status_code == 413


def test_runs_dont_show_the_debug_log_path(api: Api) -> None:
    grant = _grant(api, _workspace(api)["id"])
    [run] = api.client.get(f"/grants/{grant['id']}/runs", headers=api.headers).json()
    assert "log_path" not in run


def test_a_notice_that_counts_names_the_grant(api: Api) -> None:
    """Issue 118: once a notice counts, its award number and title are the grant's."""
    grant = _grant(api, _workspace(api)["id"])
    response = _post_record(
        api,
        grant["id"],
        {
            "kind": "notice",
            "dated": {"value": "2023-01-10"},
            "amendment_number": {"value": "000"},
            "amendment_type": {"value": "New Project"},
            "award_number": {"value": "SYN-2300117"},
            "title": {"value": "Sediment Microbiome Survey of Example Bay"},
        },
    )
    assert response.status_code == 201, response.text
    with api.platform.pool.connection() as conn:
        row = conn.execute(
            "select award_number, title from public.grants where id = %s", (grant["id"],)
        ).fetchone()
    assert row == {
        "award_number": "SYN-2300117",
        "title": "Sediment Microbiome Survey of Example Bay",
    }
