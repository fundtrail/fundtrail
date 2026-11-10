"""Sample grants (issue 165, first version): the choices, opening one, and its timeline.

Every timeline route is 404 on a grant that isn't a sample. The grant dependency checks
that the user may reach the grant before anything moves its clock.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from app.contracts.api import (
    FileLink,
    GrantSummary,
    SampleCreate,
    SampleOption,
    SampleRefusal,
    SampleRefusalReason,
)
from app.contracts.timeline import TimelineMove, TimelineStartOver, TimelineView
from app.contracts.workspaces import Grant, SampleChoice
from app.db.platform import Platform
from app.db.pool import transaction
from app.samples import player
from app.samples.timeline import MoveRefused

from .deps import NOT_FOUND, GrantDep, PlatformDep, UserDep, WorkspaceDep
from .routes import PlainErrorsRoute, signed_link
from .views import load_snapshot, summary

router = APIRouter(route_class=PlainErrorsRoute)

_REFUSAL: dict[int | str, dict[str, Any]] = {
    409: {"model": SampleRefusal, "description": "The refusal, as SampleRefusal in `detail`"}
}


def _refused(refusal: SampleRefusal) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"detail": refusal.model_dump(mode="json")}
    )


def _summary(platform: Platform, grant: Grant) -> GrantSummary:
    with transaction(platform.pool) as conn:
        return summary(load_snapshot(platform, conn, grant))


def _view(platform: Platform, grant: Grant) -> TimelineView:
    with transaction(platform.pool) as conn:
        snap = load_snapshot(platform, conn, grant)
        return player.view(platform, conn, snap.grant, summary(snap))


def _sample_grant(grant: Grant) -> Grant:
    if grant.sample is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return grant


@router.get("/samples")
def list_samples(user: UserDep) -> list[SampleOption]:
    """The sample choices, in the Add a grant dropdown's order."""
    return player.options()


@router.post(
    "/workspaces/{workspace_id}/samples",
    status_code=status.HTTP_201_CREATED,
    responses=_REFUSAL,
)
def open_sample(
    workspace: WorkspaceDep, body: SampleCreate, user: UserDep, platform: PlatformDep
) -> GrantSummary:
    """Open a sample grant in the workspace, its clock at its timeline's first event."""
    if body.choice is SampleChoice.LARGER_LIVE and not body.confirmed:
        return _refused(  # pyright: ignore[reportReturnType]
            SampleRefusal(
                reason=SampleRefusalReason.NEEDS_CONFIRM,
                message="Reading the larger sample live takes a while and costs model calls. "
                "Confirm to open it.",
            )
        )
    try:
        grant = player.open_sample(platform, user.id, workspace.id, body.choice)
    except player.SampleError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, [str(error)]) from error
    return _summary(platform, grant)


@router.get("/grants/{grant_id}/timeline")
def get_timeline(grant: GrantDep, platform: PlatformDep) -> TimelineView:
    return _view(platform, _sample_grant(grant))


@router.post("/grants/{grant_id}/timeline", responses=_REFUSAL)
def move_timeline(
    grant: GrantDep, body: TimelineMove, user: UserDep, platform: PlatformDep
) -> TimelineView:
    """Move the sample's timeline forward: to `to`, or with nothing, to the next item."""
    _sample_grant(grant)
    if body.skip_human_steps:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED, "Skipping the human steps isn't built yet."
        )
    try:
        player.move(platform, user.id, grant, body.to)
    except player.GrantGone as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from error
    except MoveRefused as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except player.SampleError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, [str(error)]) from error
    except player.AnotherSampleWorking as busy:
        name = busy.grant.award_number or "another larger sample"
        return _refused(  # pyright: ignore[reportReturnType]
            SampleRefusal(
                reason=SampleRefusalReason.ANOTHER_SAMPLE_WORKING,
                message=f"The agent is still reading {name}. Its clock can move again "
                "once it's done.",
                grant=_summary(platform, busy.grant),
            )
        )
    return _view(platform, grant)


@router.post("/grants/{grant_id}/timeline/start-over", responses=_REFUSAL)
def start_over(
    grant: GrantDep, body: TimelineStartOver, user: UserDep, platform: PlatformDep
) -> TimelineView:
    """Reset that one sample grant and start its timeline again at the first event. The
    read-live limit never refuses it."""
    _sample_grant(grant)
    if not body.confirmed:
        return _refused(  # pyright: ignore[reportReturnType]
            SampleRefusal(
                reason=SampleRefusalReason.NEEDS_CONFIRM,
                message="Starting over removes everything on this sample grant, including "
                "what you uploaded and decided. Confirm to start over.",
            )
        )
    try:
        fresh = player.start_over(platform, user.id, grant)
    except player.GrantGone as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from error
    return _view(platform, fresh)


@router.post("/grants/{grant_id}/timeline/deliveries/{event_id}")
def deliver_for_me(grant: GrantDep, event_id: str, platform: PlatformDep) -> TimelineView:
    """ "Deliver for me": the item comes in as the user's own upload would (ruling 44)."""
    _sample_grant(grant)
    try:
        player.deliver_for_me(platform, grant, event_id)
    except (player.NoSuchItem, player.GrantGone) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from error
    except player.SampleError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return _view(platform, grant)


@router.get("/grants/{grant_id}/timeline/deliveries/{event_id}/file")
def get_the_file(grant: GrantDep, event_id: str, platform: PlatformDep) -> FileLink:
    """ "Get the file": a short-lived link to the item's original, like an evidence file's."""
    _sample_grant(grant)
    try:
        path, media_type = player.item_file(platform, grant, event_id)
    except player.NoSuchItem as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from error
    except Exception as error:  # noqa: BLE001 - the original couldn't be staged this time
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The file can't be fetched right now. Try again."
        ) from error
    return signed_link(platform, path, media_type)
