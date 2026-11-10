"""Which browser origins may call the API (CORS, cross-origin resource sharing).

The app's pages are served from another origin than the API (another host, or another
port locally), so the browser asks the API first. Only the origins listed in
`FUNDTRAIL_ALLOWED_ORIGINS` (comma-separated, for example
`https://fundtrail.example,https://staging.fundtrail.example`) are allowed. With none
listed, a local Supabase stack (the same rule as the dev email sign-in) allows the
frontend's local addresses; anything else allows no origin.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import is_local

LOCAL_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def allowed_origins(env: Mapping[str, str] | None = None) -> list[str]:
    env = os.environ if env is None else env
    listed = [o.strip().rstrip("/") for o in env.get("FUNDTRAIL_ALLOWED_ORIGINS", "").split(",")]
    listed = [o for o in listed if o]
    if listed:
        return listed
    supabase_url = env.get("SUPABASE_URL") or ""
    return list(LOCAL_ORIGINS) if supabase_url and is_local(supabase_url) else []


def add_cors(app: FastAPI, origins: list[str] | None = None) -> None:
    """Let the allowed origins call the API with the signed-in user's token."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins() if origins is None else origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
