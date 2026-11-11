"""Ruling 71 (how far the agent is, and its last run's summary) and ruling 74 (a budget
sub-line names its parent)."""

from __future__ import annotations

from typing import Any

from app.api.views import _reading  # pyright: ignore[reportPrivateUsage]
from app.db import store
from app.db.pool import transaction
from tests.api.conftest import Api
from tests.db.platform_fixtures import sample_into_db

LEDGER = (
    b"line_id,transaction_date,posting_date,amount,description,account,vendor,reference,"
    b"original_line_id\n"
    b"L-1,2025-11-12,2025-11-14,10.00,Liners,55016 Lab Instruments and Supplies,V,R1,\n"
    b"L-2,2025-11-12,2025-11-14,20.00,Tubes,55016 Lab Instruments and Supplies,V,R2,\n"
    b"L-3,2025-11-12,2025-11-14,30.00,Gloves,55016 Lab Instruments and Supplies,V,R3,\n"
)


def _summary(api: Api, workspace_id: str, grant_id: str) -> Any:
    rows = api.client.get(f"/workspaces/{workspace_id}/grants", headers=api.headers).json()
    return next(r for r in rows if r["grant"]["id"] == grant_id)


def _finish(api: Api, grant_id: str, summary: str | None = None) -> None:
    """Finish the grant's oldest unfinished run, as the worker would."""
    with transaction(api.platform.pool) as conn:
        conn.execute(
            """update public.agent_runs set status = 'done', finished_at = clock_timestamp(),
                 summary = %s
               where id = (select id from public.agent_runs
                           where grant_id = %s and status in ('queued', 'running')
                           order by queued_at, id limit 1)""",
            (summary, grant_id),
        )


def test_the_grant_list_shows_how_far_the_agent_is(api: Api) -> None:
    c, h = api.client, api.headers
    workspace = c.post("/workspaces", json={"name": "Lab"}, headers=h).json()["id"]
    grant = c.post(
        f"/workspaces/{workspace}/grants",
        files={"file": ("award_letter.txt", b"Award SYN-1", "text/plain")},
        headers=h,
    ).json()["id"]
    reading = _summary(api, workspace, grant)["reading"]
    assert reading == {"files_read": 0, "files_total": 1, "lines_read": 0, "lines_total": 0}
    c.post(
        f"/grants/{grant}/evidence",
        files={"file": ("invoice.txt", b"Total: $10.00", "text/plain")},
        headers=h,
    )
    c.post(f"/grants/{grant}/ledger", files={"file": ("ledger.csv", LEDGER, "text/csv")}, headers=h)
    # The letter's run finishes while the others wait: it stays counted, as read.
    _finish(api, grant, "Read the award letter.")
    reading = _summary(api, workspace, grant)["reading"]
    assert reading == {"files_read": 1, "files_total": 2, "lines_read": 0, "lines_total": 3}
    _finish(api, grant)
    _finish(api, grant, "Linked the invoice to L-1.")
    summary = _summary(api, workspace, grant)
    assert summary["reading"] is None
    assert summary["last_run_summary"] == "Linked the invoice to L-1."


def test_read_never_exceeds_total() -> None:
    progress = _reading({"files_read": 3, "files_total": 2, "lines_read": 5, "lines_total": 4})
    assert progress is not None
    assert (progress.files_read, progress.lines_read) == (2, 4)
    assert _reading(None) is None


def test_a_budget_sub_line_names_its_parent(api: Api) -> None:
    sample = sample_into_db(api.platform, api.user_id)
    with transaction(api.platform.pool) as conn:
        assert store.list_records(conn, sample.grant.id)
    lines = api.client.get(f"/grants/{sample.grant.id}", headers=api.headers).json()["budget"][
        "lines"
    ]
    parents = {line["line"]["data"]["category"]: line["parent"] for line in lines}
    assert parents["materials_and_supplies"] == "other_direct_costs"
    assert parents["other_direct_costs"] is None
    assert parents["participant_support"] is None
