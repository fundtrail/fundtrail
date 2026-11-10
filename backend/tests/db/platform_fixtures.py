"""Fixtures for the platform's tests: a throwaway database with the migrations and
Procrastinate's schema, fakes for the other areas, and locally signed sign-in tokens.

Set TEST_DATABASE_URL to a Postgres server where the user may create databases. Without
it, or without a reachable server, the tests that need a database skip. No Supabase
project or key is needed: tokens are signed here with a key made for the session.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, LiteralString, cast

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.api.auth import SupabaseTokenVerifier
from app.contracts.charges import Charge
from app.contracts.checks import (
    Bucket,
    ChargeStatus,
    ChecksInput,
    ChecksOutput,
    OpenQuestion,
    Problem,
    Reason,
    RecordStatus,
)
from app.contracts.records import BudgetCategory, DefaultItem, Question, Record
from app.contracts.runs import TriggerKind
from app.db.platform import Platform, set_platform
from app.db.pool import open_pool
from app.db.ports import AgentInput, AgentResult
from tests.db.conftest import SUPABASE_STUBS
from tests.db.conftest import _migration_files as migration_files  # noqa: PLC2701

SUPABASE_URL = "https://project.supabase.example"


@pytest.fixture(scope="session")
def platform_database_url() -> Iterator[str]:
    """A fresh database with the Supabase stubs, every migration and Procrastinate's schema.

    Built like main's `database_url` (tests/db/conftest.py), from its stubs and migrations:
    skipped without TEST_DATABASE_URL, failed when it's set and no Postgres answers.
    """
    server_url = os.environ.get("TEST_DATABASE_URL")
    if not server_url:
        pytest.skip("TEST_DATABASE_URL is not set")
    import psycopg
    from procrastinate.schema import SchemaManager
    from psycopg import conninfo, sql

    try:
        admin = psycopg.connect(server_url, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as error:
        pytest.fail(f"TEST_DATABASE_URL is set, but no Postgres answers there: {error}")
    name = f"fundtrail_platform_{uuid.uuid4().hex[:12]}"
    with admin:
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
        url = conninfo.make_conninfo(server_url, dbname=name)
        try:
            with psycopg.connect(url, autocommit=True) as conn:
                conn.execute(SUPABASE_STUBS)
                for path in migration_files():
                    conn.execute(cast(LiteralString, path.read_text()))
                conn.execute(SchemaManager.get_schema())
            yield url
        finally:
            admin.execute(
                sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name))
            )


# Fakes for the other areas.


class FakeChecks:
    """Every charge passes unless a test says otherwise. A failed run raises a problem on
    the file or charge that triggered it, as W2's checks do."""

    def __init__(self) -> None:
        self.calls: list[ChecksInput] = []
        self.buckets: dict[str, Bucket] = {}  # by ledger line ID
        self.agent_questions: bool = False

    def run_checks(self, checks_input: ChecksInput, /) -> ChecksOutput:
        self.calls.append(checks_input)
        failed_files = {
            r.trigger.id for r in checks_input.failed_runs if r.trigger.kind == TriggerKind.FILE
        }
        failed_charges = {
            r.trigger.id for r in checks_input.failed_runs if r.trigger.kind == TriggerKind.CHARGE
        }
        charges: list[ChargeStatus] = []
        for c in checks_input.charges:
            bucket = self.buckets.get(c.ledger_line_id, Bucket.EVIDENCE_COMPLETE)
            if c.id in failed_charges:
                bucket = Bucket.NEEDS_HUMAN
            reason = Reason(check="fake", problem=bucket.value, text="fake reason", bucket=bucket)
            charges.append(
                ChargeStatus(
                    grant_id=c.grant_id,
                    charge_id=c.id,
                    bucket=bucket,
                    reasons=(reason,),
                    checklist=(),
                    flagged=bucket in (Bucket.NEEDS_HUMAN, Bucket.POSSIBLE_CONFLICT),
                )
            )
        records = [
            RecordStatus(
                grant_id=f.grant_id,
                file_id=f.id,
                problems=(Problem(check="agent_run", problem="failed", text="The agent failed."),),
                flagged=True,
            )
            for f in checks_input.files
            if f.id in failed_files
        ]
        questions = (
            [
                OpenQuestion(charge_id=c.id, question=Question.ALLOWABLE, answer_by="agent")  # pyright: ignore[reportArgumentType]
                for c in checks_input.charges
            ]
            if self.agent_questions
            else []
        )
        return ChecksOutput(
            charges=tuple(charges),
            records=tuple(records),
            grants=(),
            questions=tuple(questions),
            notes=(),
        )

    def default_items(self, charge: Charge, records: Sequence[Record], /) -> Sequence[DefaultItem]:
        return []

    def account_categories(self, account: str, /) -> Sequence[BudgetCategory]:
        return [BudgetCategory.MATERIALS_AND_SUPPLIES] if account.startswith("55016") else []


@dataclass
class FakeAgent:
    """Calls `behave` for each run; by default a run writes nothing."""

    behave: Callable[[AgentInput], AgentResult] = lambda _: AgentResult(summary="nothing to do")
    inputs: list[AgentInput] = field(default_factory=list[AgentInput])

    def run(self, agent_input: AgentInput, /) -> AgentResult:
        self.inputs.append(agent_input)
        return self.behave(agent_input)


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, path: str, data: bytes, media_type: str, /) -> None:
        if path in self.objects:
            raise RuntimeError("already stored")
        self.objects[path] = (data, media_type)

    def get(self, path: str, /) -> bytes:
        return self.objects[path][0]

    def signed_url(self, path: str, expires_in: int, /) -> str:
        return f"{SUPABASE_URL}/storage/v1/object/sign/evidence/{path}?token=fake&ttl={expires_in}"


class FakePinger:
    def __init__(self) -> None:
        self.pings: list[tuple[str, str, dict[str, Any]]] = []

    def ping(self, topic: str, event: str, payload: dict[str, Any], /) -> None:
        self.pings.append((topic, event, payload))


@pytest.fixture
def platform(platform_database_url: str) -> Iterator[Platform]:
    pool = open_pool(platform_database_url, max_size=4)
    with pool.connection() as conn:
        conn.execute("delete from procrastinate_jobs")
    p = Platform(
        pool=pool,
        checks=FakeChecks(),
        agent=FakeAgent(),
        storage=FakeStorage(),
        pinger=FakePinger(),
        run_retry_wait_seconds=0,
    )
    set_platform(p)
    try:
        yield p
    finally:
        set_platform(None)
        pool.close()


def run_worker_until_idle(database_url: str, concurrency: int = 1) -> None:
    """Run the job worker until no agent run is waiting for it, then stop.

    A worker that isn't told to wait stops as soon as it finds no job it may start, which
    happens while a grant's lock holds its other jobs back, so it's started again.
    """
    import psycopg

    from app.db.jobs import QUEUE, TASK_NAME
    from app.db.worker import open_worker_app

    async def go() -> None:
        async with open_worker_app(database_url) as app:
            await app.run_worker_async(
                queues=[QUEUE],
                concurrency=concurrency,
                wait=False,
                listen_notify=False,
                install_signal_handlers=False,
            )

    for _ in range(20):
        asyncio.run(go())
        with psycopg.connect(database_url) as conn:
            row = conn.execute(
                "select count(*) from procrastinate_jobs where task_name = %s and status = 'todo'",
                (TASK_NAME,),
            ).fetchone()
        if row is None or row[0] == 0:
            return
    raise AssertionError("the worker didn't finish the queued runs")


# Users and tokens.


@dataclass(frozen=True)
class Signer:
    key: ec.EllipticCurvePrivateKey

    def token(self, user_id: str, email: str, **overrides: Any) -> str:
        claims: dict[str, Any] = {
            "sub": user_id,
            "email": email,
            "aud": "authenticated",
            "iss": f"{SUPABASE_URL}/auth/v1",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "user_metadata": {"full_name": "Pat Example"},
        }
        claims.update(overrides)
        return jwt.encode(claims, self.key, algorithm="ES256")

    def verifier(self) -> SupabaseTokenVerifier:
        public = self.key.public_key()
        return SupabaseTokenVerifier(SUPABASE_URL, signing_key=lambda _token: public)


@pytest.fixture(scope="session")
def signer() -> Signer:
    return Signer(ec.generate_private_key(ec.SECP256R1()))


def new_auth_user(p: Platform) -> str:
    """A Supabase auth user (the stub table), as signing up would make one."""
    user_id = str(uuid.uuid4())
    with p.pool.connection() as conn:
        conn.execute("insert into auth.users (id) values (%s)", (user_id,))
    return user_id
