"""Apply the Supabase migrations to a throwaway Postgres database.

Set TEST_DATABASE_URL to a Postgres server where the user may create databases,
for example ``postgresql://postgres:postgres@localhost:5432/postgres``. Each test
session creates a fresh database, applies the stubs below and every file in
``supabase/migrations/`` in order, and drops the database at the end. Without
TEST_DATABASE_URL, the tests skip. With it set and no server answering, they fail.

Supabase's own schemas aren't in a plain Postgres, so the session stubs the two
pieces the migrations touch: ``auth.users`` (only its ``id``) and
``storage.buckets`` (``id``, ``name``, ``public``). Against Supabase's own
Postgres image the real ones are already there, and the stubs do nothing. The
migrations grant nothing to Supabase's roles, so no roles are stubbed.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "supabase" / "migrations"

SUPABASE_STUBS = """
create schema if not exists auth;
create table if not exists auth.users (id uuid primary key);
create schema if not exists storage;
create table if not exists storage.buckets (
  id text primary key,
  name text not null,
  public boolean default false
);
"""


def _migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    server_url = os.environ.get("TEST_DATABASE_URL")
    if not server_url:
        pytest.skip("TEST_DATABASE_URL is not set")
    psycopg = pytest.importorskip("psycopg")
    from psycopg import conninfo, sql

    try:
        admin = psycopg.connect(server_url, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as error:
        # Set but unreachable is a broken setup, such as a CI service that didn't
        # start, so it fails rather than skipping every database test.
        pytest.fail(f"TEST_DATABASE_URL is set, but no Postgres answers there: {error}")

    name = f"fundtrail_test_{uuid.uuid4().hex[:12]}"
    with admin:
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
        url = conninfo.make_conninfo(server_url, dbname=name)
        try:
            with psycopg.connect(url, autocommit=True) as conn:
                conn.execute(SUPABASE_STUBS)
                for path in _migration_files():
                    conn.execute(path.read_text())
            yield url
        finally:
            admin.execute(
                sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name))
            )


@pytest.fixture
def db(database_url: str) -> Iterator[psycopg.Connection]:
    """A connection in a transaction that's rolled back after the test."""
    import psycopg

    with psycopg.connect(database_url) as conn:
        try:
            yield conn
        finally:
            conn.rollback()
