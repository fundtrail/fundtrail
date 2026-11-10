"""The HTTP API. `main.py` includes `router` and runs `lifespan`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from .routes import router

__all__ = ["lifespan", "router"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Set the platform up from the environment, unless a test already put one on app.state,
    and run the job worker inside the process when WORKER_MODE is "inline"."""
    if getattr(app.state, "platform", None) is not None:
        yield
        return
    from app.db.config import Settings
    from app.db.platform import set_platform
    from app.db.worker import inline_worker, platform_from_env

    from .auth import SupabaseTokenVerifier

    settings = Settings.from_env()
    platform = platform_from_env(settings)
    assert settings.supabase_url is not None
    app.state.platform = platform
    app.state.verifier = SupabaseTokenVerifier(
        settings.supabase_url, jwt_secret=settings.supabase_jwt_secret
    )
    set_platform(platform)
    async with AsyncExitStack() as stack:
        if settings.worker_mode == "inline":
            await stack.enter_async_context(
                inline_worker(settings.database_url, settings.worker_concurrency)
            )
        try:
            yield
        finally:
            set_platform(None)
            platform.pool.close()
