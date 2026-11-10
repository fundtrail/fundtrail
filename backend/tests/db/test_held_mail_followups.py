"""The follow-ups to issue 43's migration: a mail_action record's held message is on its
grant, and the screen ping policy reads only the channel the user joined."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.db.test_first_migration import make_grant, make_record, record_values, rejects
from tests.db.test_held_mail_and_progress import make_held

if TYPE_CHECKING:
    import psycopg
    from psycopg import errors
else:
    psycopg = pytest.importorskip("psycopg")
    errors = pytest.importorskip("psycopg.errors")


@pytest.fixture
def g(db: psycopg.Connection) -> dict[str, Any]:
    return make_grant(db)


def test_a_mail_action_names_a_held_message_on_its_own_grant(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    accountant = {"author": "user", "author_user_id": g["user_id"]}
    mine = make_held(db, g)
    make_record(
        db, g, {"kind": "mail_action", "held_mail_id": mine, "action": "let_in"}, **accountant
    )
    # A grant in the same workspace, holding a message of its own.
    other = {**g, "grant_id": make_grant_in(db, g["workspace_id"])}
    theirs = make_held(db, other, "msg-2")
    data = {"kind": "mail_action", "held_mail_id": theirs, "action": "dismiss"}
    rejects(db, errors.ForeignKeyViolation, "records", **record_values(g, data, **accountant))


def make_grant_in(db: psycopg.Connection, workspace_id: str) -> str:
    row = db.execute(
        "insert into public.grants (workspace_id) values (%s) returning id", [workspace_id]
    ).fetchone()
    assert row is not None
    return str(row[0])


def reads(db: psycopg.Connection, g: dict[str, Any], joined: str, other_topic: str) -> int:
    """How many of `other_topic`'s broadcasts the owner reads while joined to `joined`."""
    db.execute(
        "insert into realtime.messages (topic, extension, event, payload) "
        "values (%s, 'broadcast', 'changed', '{}'), (%s, 'broadcast', 'changed', '{}')",
        [joined, other_topic],
    )
    db.execute("set local role authenticated")
    db.execute("select set_config('request.jwt.claim.sub', %s, true)", [str(g["user_id"])])
    db.execute("select set_config('realtime.topic', %s, true)", [joined])
    row = db.execute(
        "select count(*) from realtime.messages where topic = %s", [other_topic]
    ).fetchone()
    mine = db.execute("select count(*) from realtime.messages where topic = %s", [joined])
    heard = mine.fetchone()
    assert heard is not None and heard[0] >= 1  # the joined channel is still heard
    db.execute("reset role")
    assert row is not None
    return int(row[0])


def test_a_user_reads_only_the_channel_they_joined(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    stranger = make_grant(db)
    assert reads(db, g, f"grant:{g['grant_id']}", f"grant:{stranger['grant_id']}") == 0
    assert reads(db, g, f"grant:{g['grant_id']}", f"workspace:{stranger['workspace_id']}") == 0


def test_even_their_own_other_channels_wait_for_their_own_join(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    assert reads(db, g, f"grant:{g['grant_id']}", f"workspace:{g['workspace_id']}") == 0
