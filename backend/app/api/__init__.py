"""The HTTP API. `main.py` includes `router` and runs `lifespan`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from .routes import router
from .screen_routes import router as _screen_router

router.include_router(_screen_router)

__all__ = ["lifespan", "router"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Set the platform up from the environment, unless a test already put one on app.state,
    and run the job worker inside the process when WORKER_MODE is "inline".

    The server refuses to start with LangSmith or LangChain tracing turned on (#82): the
    agent would refuse every run, and tracing would send evidence to a third party."""
    from app.agent import check_no_tracing

    check_no_tracing()
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
        settings.supabase_url,
        jwt_secret=settings.supabase_jwt_secret,
        allow_email_signin=settings.dev_email_signin,
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
