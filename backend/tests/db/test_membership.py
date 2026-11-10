"""Workspace membership (issue 160): one place answers who may reach a workspace or a
grant, and a user-authored row is written by a member of its workspace."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from app.api.report import report_inputs
from app.contracts.records import Author, Record
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


def _user(p: Platform, email: str = "pat@university.example") -> str:
    user_id = new_auth_user(p)
    with transaction(p.pool) as conn:
        store.upsert_user(conn, User(id=user_id, email=email))
    return user_id


def _grant(p: Platform, owner_id: str) -> Grant:
    with transaction(p.pool) as conn:
        workspace = store.create_workspace(conn, owner_id, "Lab")
    return actions.add_grant(p, workspace.id, LETTER)


def _member(p: Platform, workspace_id: str, user_id: str, role: str) -> None:
    with transaction(p.pool) as conn:
        conn.execute(
            """insert into public.workspace_members (workspace_id, user_id, role)
               values (%s, %s, %s)""",
            (workspace_id, user_id, role),
        )


def _reach(p: Platform, grant: Grant, user_id: str) -> dict[str, bool]:
    with transaction(p.pool) as conn:
        [f] = store.list_files(conn, grant.id, datetime.max.replace(tzinfo=UTC))
        return {
            "list": any(w.id == grant.workspace_id for w in store.list_workspaces(conn, user_id)),
            "workspace": store.get_workspace(conn, grant.workspace_id, user_id) is not None,
            "grant": store.get_grant(conn, grant.id, user_id) is not None,
            "file": store.get_file(conn, f.id, user_id) is not None,
        }


def test_the_creator_is_the_owner_member_and_reaches_everything(
    platform: Platform,  # noqa: F811
) -> None:
    owner = _user(platform)
    grant = _grant(platform, owner)
    with transaction(platform.pool) as conn:
        sample = store.sample_accountant_id(conn, grant.workspace_id)
        rows = conn.execute(
            """select user_id::text, role from public.workspace_members
               where workspace_id = %s order by role""",
            (grant.workspace_id,),
        ).fetchall()
    assert rows == [{"user_id": owner, "role": "owner"}, {"user_id": sample, "role": "sample"}]
    assert _reach(platform, grant, owner) == dict.fromkeys(
        ("list", "workspace", "grant", "file"), True
    )


def test_each_workspace_has_its_own_sample_accountant_nobody_signs_in_as(
    platform: Platform,  # noqa: F811
) -> None:
    owner = _user(platform)
    first, second = _grant(platform, owner), _grant(platform, owner)
    with transaction(platform.pool) as conn:
        a = store.sample_accountant_id(conn, first.workspace_id)
        b = store.sample_accountant_id(conn, second.workspace_id)
        user = store.get_user(conn, a)
        with pytest.raises(psycopg.errors.UniqueViolation), conn.transaction():
            conn.execute(
                """insert into public.workspace_members (workspace_id, user_id, role)
                   values (%s, %s, 'sample')""",
                (first.workspace_id, owner),
            )
    assert a != b
    assert user is not None and user.name == "Sample accountant"
    assert user.email.endswith("@fundtrail.example")
    # The stub auth schema has only the ID; on Supabase the row has no email, phone or
    # password and is banned, so there's nothing to sign in with.
    assert _reach(platform, first, a) == dict.fromkeys(
        ("list", "workspace", "grant", "file"), False
    )
    # It's a member, so a past decision can be written as it.
    record = _record(first, a)
    with transaction(platform.pool) as conn:
        store.insert_records(conn, [record])


def test_a_stranger_or_the_sample_accountant_reaches_nothing(
    platform: Platform,  # noqa: F811
) -> None:
    grant = _grant(platform, _user(platform))
    stranger = _user(platform)
    with transaction(platform.pool) as conn:
        sample = store.sample_accountant_id(conn, grant.workspace_id)
    nothing = dict.fromkeys(("list", "workspace", "grant", "file"), False)
    assert _reach(platform, grant, stranger) == nothing
    assert _reach(platform, grant, sample) == nothing


def test_the_screen_pings_ask_the_same_rule(platform: Platform) -> None:  # noqa: F811
    owner, stranger = _user(platform), _user(platform)
    grant = _grant(platform, owner)

    def hears(user_id: str, topic: str) -> bool:
        with transaction(platform.pool) as conn:
            conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            row = conn.execute("select private.can_hear_topic(%s) as ok", (topic,)).fetchone()
        assert row is not None
        return row["ok"]

    for topic in (f"grant:{grant.id}", f"workspace:{grant.workspace_id}"):
        assert hears(owner, topic) and not hears(stranger, topic)


def _record(grant: Grant, author_user_id: str) -> Record:
    return Record.model_validate(
        {
            "id": str(uuid.uuid4()),
            "workspace_id": grant.workspace_id,
            "grant_id": grant.id,
            "author": Author.USER,
            "author_user_id": author_user_id,
            "written_at": datetime(2026, 4, 1, tzinfo=UTC),
            "data": {
                "kind": "other_term",
                "dated": {"value": "2026-04-01"},
                "label": "Note",
                "statement": {"value": "Look."},
            },
        }
    )


def test_a_records_author_is_a_member_of_its_workspace(platform: Platform) -> None:  # noqa: F811
    grant = _grant(platform, _user(platform))
    record = _record(grant, _user(platform))
    with pytest.raises(psycopg.errors.ForeignKeyViolation), transaction(platform.pool) as conn:
        store.insert_records(conn, [record])


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
        conn.execute(
            "update public.workspaces set clock_now = %s where id = %s", (now, grant.workspace_id)
        )
        inputs = report_inputs(platform, conn, grant, now, second, None)
    assert inputs.preparer.id == second
