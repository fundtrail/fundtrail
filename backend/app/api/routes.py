"""The thin path's endpoints (contracts.md section 12): put a grant, a ledger or a file in,
write a record, and read records, runs and charges with their status.

The grant page, the charge page, the evidence cards, the problem list, threads, the
clock and the report follow the agreed screen bodies (#22) in a later pull request.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.contracts.api import FileLink, LedgerUploadResult, WorkspaceCreate
from app.contracts.evidence import EvidenceFile
from app.contracts.records import BudgetAssignment, Record
from app.contracts.rules import RecordState
from app.contracts.runs import AgentRun
from app.contracts.workspaces import Grant, Workspace
from app.db import actions, store
from app.db.pool import transaction, workspace_now

from .bodies import ChargeRow, NewRecordIn
from .deps import NOT_FOUND, GrantDep, PlatformDep, UserDep, WorkspaceDep

router = APIRouter()

# How long a link to an original file works.
CONTENT_LINK_SECONDS = 300


async def _upload(file: UploadFile) -> actions.Upload:
    return actions.Upload(
        name=file.filename or "file",
        media_type=file.content_type or "application/octet-stream",
        data=await file.read(),
    )


def _rejected(error: actions.WriteRejected) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": error.problems}
    )


_REJECTED: dict[int | str, dict[str, Any]] = {
    422: {"description": "The write check's problems, as plain sentences in `detail`"}
}


@router.get("/workspaces")
def list_workspaces(user: UserDep, platform: PlatformDep) -> list[Workspace]:
    with transaction(platform.pool) as conn:
        return store.list_workspaces(conn, user.id)


@router.post("/workspaces", status_code=status.HTTP_201_CREATED)
def create_workspace(body: WorkspaceCreate, user: UserDep, platform: PlatformDep) -> Workspace:
    with transaction(platform.pool) as conn:
        return store.create_workspace(conn, user.id, body.name)


@router.post("/workspaces/{workspace_id}/grants", status_code=status.HTTP_201_CREATED)
async def create_grant(workspace: WorkspaceDep, platform: PlatformDep, file: UploadFile) -> Grant:
    """A new grant from its award letter. The grant comes back at once; its terms
    appear as the agent writes them."""
    upload = await _upload(file)

    return await run_in_threadpool(actions.add_grant, platform, workspace.id, upload)


@router.post("/grants/{grant_id}/ledger", responses=_REJECTED)
async def upload_ledger(
    grant: GrantDep, platform: PlatformDep, file: UploadFile
) -> LedgerUploadResult:

    content = await file.read()
    try:
        return await run_in_threadpool(actions.add_ledger, platform, grant, content)
    except actions.WriteRejected as error:
        return _rejected(error)  # pyright: ignore[reportReturnType]


@router.post("/grants/{grant_id}/evidence", status_code=status.HTTP_201_CREATED)
async def upload_evidence(grant: GrantDep, platform: PlatformDep, file: UploadFile) -> EvidenceFile:

    upload = await _upload(file)
    return await run_in_threadpool(actions.add_evidence, platform, grant, upload)


@router.get("/grants/{grant_id}/records")
def list_records(grant: GrantDep, platform: PlatformDep) -> list[Record]:
    """Every record on the grant, replaced and waiting ones included, in the order written."""
    with transaction(platform.pool) as conn:
        now = workspace_now(store.workspace_by_id(conn, grant.workspace_id))
        return store.list_records(conn, grant.id, now)


@router.post("/grants/{grant_id}/records", status_code=status.HTTP_201_CREATED, responses=_REJECTED)
def create_record(
    body: NewRecordIn, grant: GrantDep, user: UserDep, platform: PlatformDep
) -> Record:
    try:
        return actions.add_record(platform, grant, user.id, body.data, body.replaces_id)
    except actions.WriteRejected as error:
        return _rejected(error)  # pyright: ignore[reportReturnType]


@router.get("/grants/{grant_id}/runs")
def list_runs(grant: GrantDep, platform: PlatformDep) -> list[AgentRun]:
    with transaction(platform.pool) as conn:
        return store.list_runs(conn, grant.id)


@router.get("/grants/{grant_id}/charges")
def list_charges(grant: GrantDep, platform: PlatformDep) -> list[ChargeRow]:
    """Each charge that has arrived, with its latest status, its assigned budget line and its
    account group's categories. Posting date order, then ledger line ID."""
    with transaction(platform.pool) as conn:
        now = workspace_now(store.workspace_by_id(conn, grant.workspace_id))
        charges = store.list_charges(conn, grant.id, now)
        records = store.list_records(conn, grant.id, now)
        files = store.list_files(conn, grant.id, now)
        statuses = store.current_statuses(conn, grant.id)
    state = RecordState(records, files)
    lines: dict[str, Record] = {}
    for r in state.current():
        if isinstance(r.data, BudgetAssignment):
            line = state.current_version(r.data.record_id)
            if line is not None:
                lines[r.data.charge_id] = line
    rows: list[ChargeRow] = []
    for c in charges:
        charge_status = statuses.get(("charge", c.id))
        rows.append(
            ChargeRow(
                charge=c,
                status=charge_status,  # pyright: ignore[reportArgumentType]
                budget_line=lines.get(c.id),
                account_categories=list(platform.checks.account_categories(c.account)),
            )
        )
    return rows


@router.get("/evidence/{file_id}/content")
def file_content(file_id: str, user: UserDep, platform: PlatformDep) -> FileLink:
    """A short-lived link to the original file."""
    with transaction(platform.pool) as conn:
        f = store.get_file(conn, file_id, user.id)
        now = workspace_now(store.workspace_by_id(conn, f.workspace_id)) if f else None
    if f is None or now is None or f.arrived_at > now:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    expires_at = datetime.now(UTC) + timedelta(seconds=CONTENT_LINK_SECONDS)
    return FileLink(
        url=platform.storage.signed_url(f.storage_path, CONTENT_LINK_SECONDS), expires_at=expires_at
    )
