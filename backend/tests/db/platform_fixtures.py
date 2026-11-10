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
from pathlib import Path
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
    GrantNote,
    GrantStatus,
    OpenQuestion,
    Problem,
    Reason,
    RecordStatus,
)
from app.contracts.evidence import storage_path
from app.contracts.fixtures import SampleGrant, load_sample_grant
from app.contracts.records import BudgetCategory, DefaultItem, Question, Record
from app.contracts.runs import TriggerKind
from app.contracts.workspaces import User
from app.db import store
from app.db.platform import Platform, set_platform
from app.db.pool import open_pool, transaction
from app.db.ports import AgentInput, AgentResult

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "supabase" / "migrations"
SUPABASE_URL = "https://project.supabase.example"

SUPABASE_STUBS = """
create schema if not exists auth;
create table if not exists auth.users (id uuid primary key);
create schema if not exists storage;
create table if not exists storage.buckets (
  id text primary key, name text not null, public boolean default false
);
"""


@pytest.fixture(scope="session")
def platform_database_url() -> Iterator[str]:
    """A fresh database with the Supabase stubs, every migration and Procrastinate's schema."""
    server_url = os.environ.get("TEST_DATABASE_URL")
    if not server_url:
        pytest.skip("TEST_DATABASE_URL is not set")
    import psycopg
    from procrastinate.schema import SchemaManager
    from psycopg import conninfo, sql

    try:
        admin = psycopg.connect(server_url, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as error:
        pytest.skip(f"no Postgres at TEST_DATABASE_URL: {error}")
    name = f"fundtrail_platform_{uuid.uuid4().hex[:12]}"
    with admin:
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
        url = conninfo.make_conninfo(server_url, dbname=name)
        try:
            with psycopg.connect(url, autocommit=True) as conn:
                conn.execute(SUPABASE_STUBS)
                for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
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
        self.grant_problems: list[Problem] = []
        self.record_problems: dict[str, list[Problem]] = {}  # by record ID
        self.notes: list[str] = []
        self.reason_records: dict[str, list[str]] = {}  # by ledger line ID

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
            reason = Reason(
                check="fake",
                problem=bucket.value,
                text="fake reason",
                bucket=bucket,
                record_ids=tuple(self.reason_records.get(c.ledger_line_id, [])),
            )
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
        visible = {r.id: r for r in checks_input.records}
        records += [
            RecordStatus(
                grant_id=visible[i].grant_id, record_id=i, problems=tuple(ps), flagged=True
            )
            for i, ps in self.record_problems.items()
            if i in visible
        ]
        grant_ids = {c.grant_id for c in checks_input.charges} | {
            f.grant_id for f in checks_input.files
        }
        grants = [
            GrantStatus(grant_id=g, problems=tuple(self.grant_problems), flagged=True)
            for g in grant_ids
            if self.grant_problems
        ]
        notes = [
            GrantNote(grant_id=g, check="budget", text=text)
            for g in grant_ids
            for text in self.notes
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
            grants=tuple(grants),
            questions=tuple(questions),
            notes=tuple(notes),
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


def sample_into_db(
    p: Platform, user_id: str | None = None, clock_now: datetime | None = None
) -> SampleGrant:
    """The sample grant (contracts.md section 15) stored under fresh IDs, owned by `user_id`
    (a new user by default), with the workspace clock at `clock_now` (the sample's own by
    default)."""
    sample = load_sample_grant()
    user_id = user_id or new_auth_user(p)
    suffix = uuid.uuid4().hex[:6]
    ids = {sample.workspace.id, sample.grant.id}
    ids |= {c.id for c in sample.charges} | {f.id for f in sample.files}
    ids |= {r.id for r in sample.records}
    renamed = {i: f"{i}-{suffix}" for i in ids} | {sample.user.id: user_id}

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            out = {k: walk(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
            if "storage_path" in out:
                out["storage_path"] = storage_path(
                    out["workspace_id"], out["grant_id"], out["id"], out["name"]
                )
            return out
        if isinstance(value, list):
            return [walk(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
        return renamed.get(value, value) if isinstance(value, str) else value

    sample = type(sample).model_validate(walk(sample.model_dump(mode="json")))
    with transaction(p.pool) as conn:
        store.upsert_user(conn, User(id=user_id, email="robin.example@university.example"))
        conn.execute(
            "insert into public.workspaces (id, owner_id, name, clock_now) values (%s, %s, %s, %s)",
            (
                sample.workspace.id,
                user_id,
                sample.workspace.name,
                clock_now or sample.workspace.clock_now,
            ),
        )
        conn.execute(
            "insert into public.grants (id, workspace_id, award_number, title)"
            " values (%s, %s, %s, %s)",
            (sample.grant.id, sample.workspace.id, sample.grant.award_number, sample.grant.title),
        )
        store.insert_charges(conn, sample.charges)
        for f in sample.files:
            store.insert_file(conn, f)
        store.insert_records(conn, sample.records)
    return sample


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
