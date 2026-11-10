"""The screens' endpoints (#22 as agreed, with PR 40's names), the threads and the clock."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse, Response

from app.contracts.api import (
    ArrivalSource,
    ChargeDetail,
    ClockMove,
    EvidenceCard,
    GrantDetail,
    GrantSummary,
    NewMessage,
    NextArrival,
    ProblemList,
    Thread,
)
from app.contracts.checks import RecordStatus
from app.contracts.records import Record, SignOff
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant
from app.db import actions, store
from app.db.clock import ClockError, ClockState, clock_state, move_clock
from app.db.pool import transaction, workspace_now

from .deps import NOT_FOUND, GrantDep, PlatformDep, UserDep, WorkspaceDep
from .report import draft_report
from .routes import PlainErrorsRoute
from .screens import ClockView
from .views import (
    GrantSnapshot,
    charge_detail,
    evidence_cards,
    grant_detail,
    load_snapshot,
    problem_rows,
    record_chain,
    summary,
    thread,
)

router = APIRouter(route_class=PlainErrorsRoute)


def _rejected(problems: list[str]) -> JSONResponse:
    """A 422 in the one shape every route uses: the contracts' WriteRejected."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": problems}
    )


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)


@router.get("/workspaces/{workspace_id}/grants")
def list_grants(workspace: WorkspaceDep, platform: PlatformDep) -> list[GrantSummary]:
    with transaction(platform.pool) as conn:
        grants = store.list_grants(conn, workspace.id)
        return [summary(load_snapshot(platform, conn, g)) for g in grants]


@router.get("/grants/{grant_id}")
def get_grant(grant: GrantDep, platform: PlatformDep) -> GrantDetail:
    with transaction(platform.pool) as conn:
        return grant_detail(conn, load_snapshot(platform, conn, grant))


@router.get("/grants/{grant_id}/problems")
def get_problems(grant: GrantDep, platform: PlatformDep) -> ProblemList:
    with transaction(platform.pool) as conn:
        return ProblemList(rows=tuple(problem_rows(load_snapshot(platform, conn, grant))))


@router.get("/grants/{grant_id}/evidence")
def get_evidence(grant: GrantDep, platform: PlatformDep) -> list[EvidenceCard]:
    with transaction(platform.pool) as conn:
        return evidence_cards(load_snapshot(platform, conn, grant))


def _charge_snapshot(platform: Any, user_id: str, charge_id: str) -> tuple[GrantSnapshot, Any]:
    with transaction(platform.pool) as conn:
        charge = store.get_charge(conn, charge_id, user_id)
        if charge is None:
            raise _not_found()
        grant = store.get_grant(conn, charge.grant_id)
        assert grant is not None
        snap = load_snapshot(platform, conn, grant)
        if charge.id not in snap.charges_by_id:
            raise _not_found()  # not arrived by the clock
        rows = store.status_history(conn, charge_id=charge.id)
    return snap, rows


@router.get("/charges/{charge_id}")
def get_charge(charge_id: str, user: UserDep, platform: PlatformDep) -> ChargeDetail:
    snap, rows = _charge_snapshot(platform, user.id, charge_id)
    return charge_detail(platform, snap, snap.charges_by_id[charge_id], rows)


@router.get("/charges/{charge_id}/thread")
def get_charge_thread(charge_id: str, user: UserDep, platform: PlatformDep) -> Thread:
    snap, rows = _charge_snapshot(platform, user.id, charge_id)
    return thread(snap, charge_id=charge_id, history=rows)


@router.post("/charges/{charge_id}/thread", status_code=status.HTTP_201_CREATED)
def post_charge_thread(
    charge_id: str, body: NewMessage, user: UserDep, platform: PlatformDep
) -> ThreadMessage:
    snap, _ = _charge_snapshot(platform, user.id, charge_id)
    return actions.add_message(platform, snap.grant, user.id, body.text, charge_id=charge_id)


def _record_snapshot(platform: Any, user_id: str, record_id: str) -> tuple[GrantSnapshot, Record]:
    with transaction(platform.pool) as conn:
        record = store.get_record(conn, record_id, user_id)
        if record is None:
            raise _not_found()
        grant = store.get_grant(conn, record.grant_id)
        assert grant is not None
        snap = load_snapshot(platform, conn, grant)
    if record.id not in snap.state.by_id:
        raise _not_found()  # written after the clock's "now"
    return snap, record


def _thread_subject(snap: GrantSnapshot, record: Record) -> Record:
    """A record's thread follows the record that replaces it (answer 13)."""
    return snap.state.current_version(record.id) or record


@router.get("/records/{record_id}/thread")
def get_record_thread(record_id: str, user: UserDep, platform: PlatformDep) -> Thread:
    snap, record = _record_snapshot(platform, user.id, record_id)
    subject = _thread_subject(snap, record)
    chain = record_chain(snap, subject.id)
    with transaction(platform.pool) as conn:
        rows = store.status_history(conn, record_ids=chain)
    return thread(snap, record_ids=chain, history=rows)


@router.post("/records/{record_id}/thread", status_code=status.HTTP_201_CREATED)
def post_record_thread(
    record_id: str, body: NewMessage, user: UserDep, platform: PlatformDep
) -> ThreadMessage:
    snap, record = _record_snapshot(platform, user.id, record_id)
    subject = _thread_subject(snap, record)
    chain = record_chain(snap, subject.id)
    with transaction(platform.pool) as conn:
        had_problem = any(
            isinstance(row.status, RecordStatus) and row.status.problems
            for row in store.status_history(conn, record_ids=chain)
        )
    has_thread = any(m.record_id in chain for m in snap.messages)
    if not (had_problem or has_thread):
        return _rejected(  # pyright: ignore[reportReturnType]
            ["Only a record with a problem has a thread (contracts.md section 10)."]
        )
    return actions.add_message(platform, snap.grant, user.id, body.text, record_id=subject.id)


# The report.


def _pdf(pdf: bytes, grant: Grant, suffix: str = "") -> Response:
    name = f"evidence-report-{_slug(grant)}{suffix}.pdf"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )


@router.get(
    "/grants/{grant_id}/report",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "The current draft"}},
)
def get_report(grant: GrantDep, user: UserDep, platform: PlatformDep) -> Response:
    """The current draft of the evidence report (decision 0022). A signed report is fetched
    through its sign-off: GET /records/{record_id}/report."""
    with transaction(platform.pool) as conn:
        now = workspace_now(store.workspace_by_id(conn, grant.workspace_id))
        pdf = draft_report(platform, conn, grant, now, user.id)
    return _pdf(pdf, grant, "-draft")


@router.get(
    "/records/{record_id}/report",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "The signed report"}},
)
def get_signed_report(record_id: str, user: UserDep, platform: PlatformDep) -> Response:
    """The report a sign-off stored: never made again (decision 0022)."""
    with transaction(platform.pool) as conn:
        record = store.get_record(conn, record_id, user.id)
        grant = store.get_grant(conn, record.grant_id) if record else None
    if record is None or grant is None or not isinstance(record.data, SignOff):
        raise _not_found()
    return _pdf(platform.storage.get(record.data.report_path), grant, f"-signed-{record.id[:8]}")


def _slug(grant: Grant) -> str:
    return "".join(
        ch if ch.isalnum() or ch == "-" else "-" for ch in grant.award_number or grant.id
    )


# The clock.


def _clock_view(state: ClockState) -> ClockView:
    arrival = state.next_arrival
    return ClockView(
        now=state.now,
        simulated=state.simulated,
        next_arrival_at=arrival.at if arrival else None,
        next_arrival=NextArrival(
            at=arrival.at, source=ArrivalSource(arrival.source), name=arrival.name
        )
        if arrival
        else None,
        catching_up=state.catching_up,
    )


@router.get("/workspaces/{workspace_id}/clock")
def get_clock(workspace: WorkspaceDep, platform: PlatformDep) -> ClockView:
    with transaction(platform.pool) as conn:
        return _clock_view(clock_state(conn, store.workspace_by_id(conn, workspace.id)))


@router.post("/workspaces/{workspace_id}/clock", responses={422: {"description": "A refused move"}})
def post_clock(workspace: WorkspaceDep, body: ClockMove, platform: PlatformDep) -> ClockView:
    """Move the demo workspace's clock forward: to `to`, or with nothing, to the next arrival."""
    try:
        return _clock_view(move_clock(platform, workspace.id, body.to))
    except ClockError as error:
        return _rejected([str(error)])  # pyright: ignore[reportReturnType]
