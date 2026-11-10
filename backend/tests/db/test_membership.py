"""Workspace membership (issue 160): one place answers who may reach a workspace or a
grant, and a user-authored row is written by a member of its workspace."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import psycopg
import pytest

from app.api.report import report_inputs
from app.contracts.charges import Charge
from app.contracts.records import Author, Record
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant, User
from app.db import actions, store
from app.db.platform import Platform
from app.db.pool import transaction
from tests.db.platform_fixtures import (  # noqa: F401 - fixtures
    new_auth_user,
    platform,
    platform_database_url,
)

LETTER = actions.Upload("letter.txt", "text/plain", b"NSF award letter")
WHAT = ("list", "workspace", "grant", "file", "charge", "record")
AT = datetime(2026, 4, 1, tzinfo=UTC)


def _user(p: Platform, email: str = "pat@university.example") -> str:
    user_id = new_auth_user(p)
    with transaction(p.pool) as conn:
        store.upsert_user(conn, User(id=user_id, email=email))
    return user_id


def _record(grant: Grant, author_user_id: str) -> Record:
    return Record.model_validate(
        {
            "id": str(uuid.uuid4()),
            "workspace_id": grant.workspace_id,
            "grant_id": grant.id,
            "author": Author.USER,
            "author_user_id": author_user_id,
            "written_at": AT,
            "data": {
                "kind": "other_term",
                "dated": {"value": "2026-04-01"},
                "label": "Note",
                "statement": {"value": "Look."},
            },
        }
    )


def _message(grant: Grant, charge_id: str, author_user_id: str) -> ThreadMessage:
    return ThreadMessage(
        id=str(uuid.uuid4()),
        workspace_id=grant.workspace_id,
        grant_id=grant.id,
        charge_id=charge_id,
        author=Author.USER,
        author_user_id=author_user_id,
        text="Is this the right invoice?",
        written_at=AT,
    )


def _grant(p: Platform, owner_id: str) -> Grant:
    """A grant with a file, a charge and a record the owner wrote."""
    with transaction(p.pool) as conn:
        workspace = store.create_workspace(conn, owner_id, "Lab")
    grant = actions.add_grant(p, workspace.id, LETTER)
    charge = Charge(
        id=str(uuid.uuid4()),
        workspace_id=grant.workspace_id,
        grant_id=grant.id,
        ledger_line_id=f"L-{uuid.uuid4().hex[:6]}",
        transaction_date=date(2025, 11, 12),
        posting_date=date(2025, 11, 14),
        arrived_at=datetime(2025, 11, 14, tzinfo=UTC),
        amount_cents=124000,
        description="Sediment core liners",
        account="55016 Lab Instruments and Supplies",
    )
    with transaction(p.pool) as conn:
        store.insert_charges(conn, [charge])
        store.insert_records(conn, [_record(grant, owner_id)])
    return grant


def _member(p: Platform, workspace_id: str, user_id: str, role: str) -> None:
    with transaction(p.pool) as conn:
        conn.execute(
            """insert into public.workspace_members (workspace_id, user_id, role)
               values (%s, %s, %s)""",
            (workspace_id, user_id, role),
        )


def _reach(p: Platform, grant: Grant, user_id: str) -> dict[str, bool]:
    end = datetime.max.replace(tzinfo=UTC)
    with transaction(p.pool) as conn:
        [f] = store.list_files(conn, grant.id, end)
        [c] = store.list_charges(conn, grant.id, end)
        [r] = store.list_records(conn, grant.id)
        return {
            "list": any(w.id == grant.workspace_id for w in store.list_workspaces(conn, user_id)),
            "workspace": store.get_workspace(conn, grant.workspace_id, user_id) is not None,
            "grant": store.get_grant(conn, grant.id, user_id) is not None,
            "file": store.get_file(conn, f.id, user_id) is not None,
            "charge": store.get_charge(conn, c.id, user_id) is not None,
            "record": store.get_record(conn, r.id, user_id) is not None,
        }


def _hears(p: Platform, user_id: str, topic: str) -> bool:
    with transaction(p.pool) as conn:
        conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
        row = conn.execute("select private.can_hear_topic(%s) as ok", (topic,)).fetchone()
    assert row is not None
    return row["ok"]


def _sample(p: Platform, grant: Grant) -> str:
    with transaction(p.pool) as conn:
        return store.sample_accountant_id(conn, grant.workspace_id)


def test_the_creator_is_the_owner_member_and_reaches_everything(
    platform: Platform,  # noqa: F811
) -> None:
    owner = _user(platform)
    grant = _grant(platform, owner)
    sample = _sample(platform, grant)
    with transaction(platform.pool) as conn:
        rows = conn.execute(
            """select user_id::text, role from public.workspace_members
               where workspace_id = %s order by role""",
            (grant.workspace_id,),
        ).fetchall()
    assert rows == [{"user_id": owner, "role": "owner"}, {"user_id": sample, "role": "sample"}]
    assert _reach(platform, grant, owner) == dict.fromkeys(WHAT, True)


def test_each_workspace_has_its_own_sample_accountant(platform: Platform) -> None:  # noqa: F811
    owner = _user(platform)
    first, second = _grant(platform, owner), _grant(platform, owner)
    a, b = _sample(platform, first), _sample(platform, second)
    with transaction(platform.pool) as conn:
        user = store.get_user(conn, a)
        with pytest.raises(psycopg.errors.UniqueViolation), conn.transaction():
            _member_sql = """insert into public.workspace_members (workspace_id, user_id, role)
                             values (%s, %s, 'sample')"""
            conn.execute(_member_sql, (first.workspace_id, owner))
    assert a != b
    assert user is not None and user.name == "Sample accountant"
    assert user.email.endswith("@fundtrail.example")
    # It's a member, so a past decision can be written as it.
    with transaction(platform.pool) as conn:
        store.insert_records(conn, [_record(first, a)])


def test_the_sample_accountants_auth_row_is_outside_gotrue_and_banned(
    platform: Platform,  # noqa: F811
) -> None:
    """On Supabase-shaped auth: no instance or audience, so GoTrue never loads the row, and
    banned until a finite far date GoTrue can read. The stub has only the ID, so the
    columns are added for this test."""
    with transaction(platform.pool) as conn:
        conn.execute(
            """alter table auth.users
                 add column if not exists banned_until timestamptz,
                 add column if not exists instance_id uuid,
                 add column if not exists aud varchar(255),
                 add column if not exists email varchar(255),
                 add column if not exists encrypted_password varchar(255)"""
        )
    grant = _grant(platform, _user(platform))
    sample = _sample(platform, grant)
    with transaction(platform.pool) as conn:
        row = conn.execute(
            """select banned_until, instance_id, aud, email, encrypted_password
               from auth.users where id = %s""",
            (sample,),
        ).fetchone()
    assert row == {
        "banned_until": datetime(9999, 12, 31, tzinfo=UTC),
        "instance_id": None,
        "aud": None,
        "email": None,
        "encrypted_password": None,
    }


def test_a_stranger_or_the_sample_accountant_reaches_nothing(
    platform: Platform,  # noqa: F811
) -> None:
    owner, stranger = _user(platform), _user(platform)
    grant = _grant(platform, owner)
    sample = _sample(platform, grant)
    nothing = dict.fromkeys(WHAT, False)
    assert _reach(platform, grant, stranger) == nothing
    assert _reach(platform, grant, sample) == nothing
    for topic in (f"grant:{grant.id}", f"workspace:{grant.workspace_id}"):
        assert _hears(platform, owner, topic)
        assert not _hears(platform, stranger, topic)
        assert not _hears(platform, sample, topic)


def test_a_records_or_messages_author_is_a_member(platform: Platform) -> None:  # noqa: F811
    grant = _grant(platform, _user(platform))
    stranger = _user(platform)
    with pytest.raises(psycopg.errors.ForeignKeyViolation), transaction(platform.pool) as conn:
        store.insert_records(conn, [_record(grant, stranger)])
    with transaction(platform.pool) as conn:
        [charge] = store.list_charges(conn, grant.id, datetime.max.replace(tzinfo=UTC))
    with pytest.raises(psycopg.errors.ForeignKeyViolation), transaction(platform.pool) as conn:
        store.insert_messages(conn, [_message(grant, charge.id, stranger)])


def test_a_workspace_with_user_written_rows_can_be_deleted(
    platform: Platform,  # noqa: F811
) -> None:
    owner = _user(platform)
    grant = _grant(platform, owner)
    sample = _sample(platform, grant)
    with transaction(platform.pool) as conn:
        [charge] = store.list_charges(conn, grant.id, datetime.max.replace(tzinfo=UTC))
        store.insert_records(conn, [_record(grant, sample)])
        store.insert_messages(conn, [_message(grant, charge.id, owner)])
    with transaction(platform.pool) as conn:
        conn.execute("delete from public.workspaces where id = %s", (grant.workspace_id,))
        left = conn.execute(
            """select (select count(*) from public.records where workspace_id = %s)
                    + (select count(*) from public.thread_messages where workspace_id = %s)
                    + (select count(*) from public.workspace_members where workspace_id = %s)
                      as n""",
            (grant.workspace_id, grant.workspace_id, grant.workspace_id),
        ).fetchone()
    assert left == {"n": 0}


def test_known_senders_and_the_preparer_come_from_members(platform: Platform) -> None:  # noqa: F811
    owner = _user(platform, "Pat@University.example")
    grant = _grant(platform, owner)
    second = _user(platform, "lee@university.example")
    _member(platform, grant.workspace_id, second, "owner")
    with transaction(platform.pool) as conn:
        assert store.acting_member_emails(conn, grant.workspace_id) == [
            "lee@university.example",
            "pat@university.example",
        ]
        now = store.list_runs(conn, grant.id)[0].clock_now
        conn.execute("update public.grants set clock_now = %s where id = %s", (now, grant.id))
        inputs = report_inputs(platform, conn, grant, now, second, None)
    assert inputs.preparer.id == second
