"""Set the platform up from the environment, and run the job worker.

Inside the API process (WORKER_MODE=inline, the default) the worker runs as a
background task of the app. On its own: `uv run python -m app.db.worker`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import procrastinate

from .config import Settings
from .jobs import QUEUE
from .jobs import app as jobs_app
from .platform import Platform, set_platform
from .pool import open_pool
from .ports import ModuleAgent, ModuleChecks
from .supabase import SupabasePinger, SupabaseStorage

# How often the worker looks for jobs when no notification arrives.
POLLING_SECONDS = 5.0


def platform_from_env(settings: Settings) -> Platform:
    if not (settings.supabase_url and settings.supabase_service_role_key):
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are needed for file storage")
    return Platform(
        pool=open_pool(settings.database_url),
        checks=ModuleChecks(),
        agent=ModuleAgent(),
        storage=SupabaseStorage(settings.supabase_url, settings.supabase_service_role_key),
        pinger=SupabasePinger(settings.supabase_url, settings.supabase_service_role_key),
    )


@asynccontextmanager
async def open_worker_app(database_url: str) -> AsyncIterator[procrastinate.App]:
    """The jobs app, connected to this database and open, for the length of the block."""
    connector = procrastinate.PsycopgConnector(conninfo=database_url)
    with jobs_app.replace_connector(connector) as app:
        async with app.open_async():
            yield app


async def run_worker(app: procrastinate.App, concurrency: int, *, wait: bool = True) -> None:
    await app.run_worker_async(
        queues=[QUEUE],
        concurrency=concurrency,
        wait=wait,
        listen_notify=True,
        fetch_job_polling_interval=POLLING_SECONDS,
        install_signal_handlers=False,
    )


@asynccontextmanager
async def inline_worker(database_url: str, concurrency: int) -> AsyncIterator[None]:
    """Run the worker beside the API until the block ends."""
    async with open_worker_app(database_url) as app:
        task = asyncio.create_task(run_worker(app, concurrency))
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def main() -> None:
    settings = Settings.from_env()
    set_platform(platform_from_env(settings))

    async def go() -> None:
        async with open_worker_app(settings.database_url) as app:
            await run_worker(app, settings.worker_concurrency)

    asyncio.run(go())


if __name__ == "__main__":
    main()
