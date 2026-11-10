"""Shared by the API and the worker: the pool, and the other areas behind their interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg import Connection
from psycopg_pool import ConnectionPool

from .ports import Agent, Checks, Pinger, Storage

# How many times a failed agent run is tried again before it fails for good, and how
# long the worker waits before each new try. A run that fails for good is passed to
# the checks, which raise a problem on the file or charge that triggered it.
RUN_RETRIES = 2
RUN_RETRY_WAIT_SECONDS = 30


@dataclass
class Platform:
    pool: ConnectionPool[Connection[dict[str, Any]]]
    checks: Checks
    agent: Agent
    storage: Storage
    pinger: Pinger
    run_retries: int = RUN_RETRIES
    run_retry_wait_seconds: int = RUN_RETRY_WAIT_SECONDS


_current: Platform | None = None


def set_platform(platform: Platform | None) -> None:
    """Make this the platform the job worker's tasks use."""
    global _current
    _current = platform


def get_platform() -> Platform:
    if _current is None:
        raise RuntimeError("the platform isn't set up: call set_platform first")
    return _current
