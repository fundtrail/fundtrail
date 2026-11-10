"""Request dependencies: the platform, the signed-in user, and ownership checks.

Anything outside the user's workspaces is a 404, so the API doesn't say it exists.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.contracts.workspaces import Grant, User, Workspace
from app.db import store
from app.db.platform import Platform
from app.db.pool import transaction

from .auth import InvalidToken, TokenVerifier


def get_platform(request: Request) -> Platform:
    return request.app.state.platform


def get_verifier(request: Request) -> TokenVerifier:
    return request.app.state.verifier


PlatformDep = Annotated[Platform, Depends(get_platform)]


def current_user(
    request: Request,
    platform: PlatformDep,
    verifier: Annotated[TokenVerifier, Depends(get_verifier)],
) -> User:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sign in first.", headers={"WWW-Authenticate": "Bearer"}
        )
    try:
        user = verifier.verify(token)
    except InvalidToken:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "The sign-in token isn't valid.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    with transaction(platform.pool) as conn:
        store.upsert_user(conn, user)
    return user


UserDep = Annotated[User, Depends(current_user)]

NOT_FOUND = "Not found."


def owned_workspace(workspace_id: str, user: UserDep, platform: PlatformDep) -> Workspace:
    with transaction(platform.pool) as conn:
        workspace = store.get_workspace(conn, workspace_id, user.id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return workspace


def owned_grant(grant_id: str, user: UserDep, platform: PlatformDep) -> Grant:
    with transaction(platform.pool) as conn:
        grant = store.get_grant(conn, grant_id, user.id)
    if grant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return grant


WorkspaceDep = Annotated[Workspace, Depends(owned_workspace)]
GrantDep = Annotated[Grant, Depends(owned_grant)]
