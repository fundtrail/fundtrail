"""Apply the Supabase migrations to a throwaway Postgres database.

Set TEST_DATABASE_URL to a Postgres server where the user may create databases,
for example ``postgresql://postgres:postgres@localhost:5432/postgres``. Each test
session creates a fresh database, applies the stubs below and every file in
``supabase/migrations/`` in order, and drops the database at the end. Without
TEST_DATABASE_URL, the tests skip. With it set and no server answering, they fail.

Supabase's own schemas aren't in a plain Postgres, so the session stubs the pieces
the migrations touch, each only where it's missing:

- ``auth.users`` (only its ``id``) and ``auth.uid()``, which reads the signed-in
  user's ID from ``request.jwt.claim.sub`` as Supabase's does.
- ``storage.buckets`` (``id``, ``name``, ``public``).
- ``realtime.messages`` (``id``, ``topic``, ``extension``, ``event``, ``payload``, with
  row level security on) and ``realtime.topic()``, which reads ``realtime.topic`` as
  Supabase's does.
- The ``anon`` and ``authenticated`` roles, with every privilege on new tables in
  ``public``, as Supabase grants them. A role belongs to the whole server, so it's
  created only if the server doesn't have it.
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
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if to_regprocedure('auth.uid()') is null then
    create function auth.uid() returns uuid language sql stable
      as $f$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $f$;
  end if;
end;
$$;
create schema if not exists realtime;
create table if not exists realtime.messages (
  id bigint generated always as identity primary key,
  topic text not null,
  extension text not null,
  event text,
  payload jsonb
);
alter table realtime.messages enable row level security;
do $$
begin
  if to_regprocedure('realtime.topic()') is null then
    create function realtime.topic() returns text language sql stable
      as $f$ select nullif(current_setting('realtime.topic', true), '') $f$;
  end if;
end;
$$;
grant usage on schema auth, realtime to authenticated;
grant select on realtime.messages to authenticated;
-- As Supabase does: every privilege on new tables in public goes to anon and authenticated.
alter default privileges in schema public grant all on tables to anon, authenticated;
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
