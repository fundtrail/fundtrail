"""Issue 43's migration: held mail, skipped files and the checker's progress, a mail_action
record's held message, a status row's grant, and the screen pings' Realtime policy."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from app.contracts.mail import (
    CheckerProgress,
    HeldFile,
    HeldMail,
    HoldReason,
    SkippedFile,
    SkipReason,
)
from tests.db.test_first_migration import (
    NOW,
    OVER_LIMIT,
    insert,
    make_bill,
    make_charge,
    make_file,
    make_grant,
    make_record,
    on_table,
    record_values,
    rejects,
    status_values,
)

if TYPE_CHECKING:
    import psycopg
    from psycopg import errors, sql
    from psycopg.types.json import Jsonb
else:
    psycopg = pytest.importorskip("psycopg")
    errors = pytest.importorskip("psycopg.errors")
    sql = pytest.importorskip("psycopg.sql")
    Jsonb = pytest.importorskip("psycopg.types.json").Jsonb

HELD_AT = datetime(2026, 2, 21, 12, tzinfo=UTC)


@pytest.fixture
def g(db: psycopg.Connection) -> dict[str, Any]:
    return make_grant(db)


def held_message(g: dict[str, Any], source_ref: str = "msg-1") -> HeldMail:
    return HeldMail(
        id=f"held-{g['grant_id']}-{source_ref}",
        workspace_id=g["workspace_id"],
        grant_id=g["grant_id"],
        sender="someone@vendor.example",
        reason=HoldReason.UNKNOWN_SENDER,
        source_ref=source_ref,
        subject="Invoice",
        held_at=HELD_AT,
        files=(
            HeldFile(
                name="message.eml",
                media_type="message/rfc822",
                storage_path=f"{g['workspace_id']}/{g['grant_id']}/held/message.eml",
                sha256="0" * 64,
            ),
        ),
        skipped=(
            SkippedFile(
                workspace_id=g["workspace_id"],
                grant_id=g["grant_id"],
                name="scan.tiff",
                source="gmail",
                source_ref=source_ref,
                reason=SkipReason.TOO_LARGE,
                skipped_at=HELD_AT,
            ),
        ),
    )


def make_held(db: psycopg.Connection, g: dict[str, Any], source_ref: str = "msg-1") -> str:
    return insert(db, "held_mail", **held_message(g, source_ref).model_dump(mode="json"))


def held_row(g: dict[str, Any], **values: Any) -> dict[str, Any]:
    row = held_message(g).model_dump(mode="json")
    row.update(values)
    return row


def skipped_row(g: dict[str, Any], **values: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "workspace_id": g["workspace_id"],
        "grant_id": g["grant_id"],
        "name": "slides.key",
        "source": "drive",
        "source_ref": "folder-1",
        "reason": "not_exportable",
        "skipped_at": NOW,
    }
    row.update(values)
    return row


# The new tables match their models.


def fields(model: type[BaseModel]) -> set[str]:
    return set(model.model_fields)


ROWS: dict[str, tuple[set[str], set[str]]] = {
    "held_mail": (fields(HeldMail), set()),
    "skipped_files": (fields(SkippedFile), {"id"}),
    "checker_progress": (fields(CheckerProgress), {"id"}),  # the key that allows one row
}


@pytest.mark.parametrize("table", sorted(ROWS))
def test_columns_match_the_contract_models(db: psycopg.Connection, table: str) -> None:
    rows = db.execute(
        "select column_name from information_schema.columns "
        "where table_schema = 'public' and table_name = %s",
        [table],
    ).fetchall()
    model_fields, added = ROWS[table]
    assert {name for (name,) in rows} == model_fields | added


@pytest.mark.parametrize("table", sorted(ROWS))
def test_the_new_tables_have_row_level_security(db: psycopg.Connection, table: str) -> None:
    row = db.execute("select relrowsecurity from pg_class where oid = %s::regclass", [table])
    assert row.fetchone() == (True,)


# Held mail.


def test_a_held_message_is_stored_with_its_files_and_skips(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    held_id = make_held(db, g)
    row = db.execute(
        "select id, workspace_id, grant_id, sender, reason, source_ref, subject, held_at, "
        "files, skipped from public.held_mail where id = %s",
        [held_id],
    ).fetchone()
    assert row is not None
    names = ["id", "workspace_id", "grant_id", "sender", "reason", "source_ref", "subject"]
    stored = dict(zip([*names, "held_at", "files", "skipped"], row, strict=True))
    assert HeldMail.model_validate(stored) == held_message(g)


def test_a_held_message_has_no_skips_by_default(db: psycopg.Connection, g: dict[str, Any]) -> None:
    values = held_row(g)
    del values["skipped"]
    held_id = insert(db, "held_mail", **values)
    row = db.execute("select skipped from public.held_mail where id = %s", [held_id])
    assert row.fetchone() == ([],)


def test_a_message_is_held_once_per_grant(db: psycopg.Connection, g: dict[str, Any]) -> None:
    make_held(db, g)
    rejects(db, errors.UniqueViolation, "held_mail", **held_row(g, id="held-again"))
    make_held(db, make_grant(db))  # the same message, delivered to another grant's address


@pytest.mark.parametrize(
    "wrong",
    [
        {"reason": "spam"},
        {"files": {"name": "message.eml"}},
        {"skipped": Jsonb("scan.tiff")},
    ],
)
def test_a_held_message_keeps_its_shape(
    db: psycopg.Connection, g: dict[str, Any], wrong: dict[str, Any]
) -> None:
    rejects(db, errors.CheckViolation, "held_mail", **held_row(g, **wrong))


def test_held_mail_and_skipped_files_are_never_updated(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    held_id = make_held(db, g)
    skipped_id = insert(db, "skipped_files", **skipped_row(g))
    with pytest.raises(errors.RestrictViolation), db.transaction():
        db.execute("update public.held_mail set subject = 'x' where id = %s", [held_id])
    with pytest.raises(errors.RestrictViolation), db.transaction():
        db.execute("update public.skipped_files set name = 'x' where id = %s", [int(skipped_id)])


def test_deleting_a_workspace_clears_its_held_mail_and_skips(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    held_id = make_held(db, g)
    insert(db, "skipped_files", **skipped_row(g))
    data = {"kind": "mail_action", "held_mail_id": held_id, "action": "dismiss"}
    make_record(db, g, data, author="user", author_user_id=g["user_id"])
    db.execute("delete from public.workspaces where id = %s", [g["workspace_id"]])
    for table in ["held_mail", "skipped_files", "records"]:
        row = db.execute(on_table("select count(*) from {table}", table)).fetchone()
        assert row == (0,), table


# Skipped files.


@pytest.mark.parametrize("wrong", [{"source": "upload"}, {"reason": "virus"}])
def test_a_skipped_file_keeps_its_shape(
    db: psycopg.Connection, g: dict[str, Any], wrong: dict[str, Any]
) -> None:
    insert(db, "skipped_files", **skipped_row(g))
    rejects(db, errors.CheckViolation, "skipped_files", **skipped_row(g, **wrong))


# The checker's progress.


def test_the_checker_saves_one_progress_row_and_updates_it(db: psycopg.Connection) -> None:
    db.execute("insert into public.checker_progress default values")
    with pytest.raises(errors.UniqueViolation), db.transaction():
        db.execute("insert into public.checker_progress default values")
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute("insert into public.checker_progress (id) values (false)")
    progress = CheckerProgress(
        mail_cursor="cursor-9",
        seen_message_ids=("msg-1",),
        first_search_done=("grant-1",),
    )
    db.execute(
        "update public.checker_progress set mail_cursor = %s, seen_message_ids = %s, "
        "drive_versions = %s, first_search_done = %s",
        [
            progress.mail_cursor,
            Jsonb(list(progress.seen_message_ids)),
            Jsonb([]),
            Jsonb(list(progress.first_search_done)),
        ],
    )
    row = db.execute(
        "select mail_cursor, seen_message_ids, drive_versions, first_search_done "
        "from public.checker_progress"
    ).fetchone()
    assert row is not None
    stored = dict(
        zip(
            ["mail_cursor", "seen_message_ids", "drive_versions", "first_search_done"],
            row,
            strict=True,
        )
    )
    assert CheckerProgress.model_validate(stored) == progress


def test_the_progress_lists_are_json_arrays(db: psycopg.Connection) -> None:
    for column in ["seen_message_ids", "drive_versions", "first_search_done"]:
        with pytest.raises(errors.CheckViolation), db.transaction():
            db.execute(
                sql.SQL("insert into public.checker_progress ({}) values ('{{}}')").format(
                    sql.Identifier(column)
                )
            )


# A mail_action record names a held message that exists.


def test_a_mail_action_names_a_held_message(db: psycopg.Connection, g: dict[str, Any]) -> None:
    held_id = make_held(db, g)
    data = {"kind": "mail_action", "held_mail_id": held_id, "action": "let_in"}
    record_id = make_record(db, g, data, author="user", author_user_id=g["user_id"])
    row = db.execute("select held_mail_id from public.records where id = %s", [record_id])
    assert row.fetchone() == (held_id,)
    missing = {"kind": "mail_action", "held_mail_id": "nope", "action": "let_in"}
    rejects(
        db,
        errors.ForeignKeyViolation,
        "records",
        **record_values(g, missing, author="user", author_user_id=g["user_id"]),
    )


# A status row's grant is its subject's grant.


def test_a_status_is_on_its_subjects_grant(db: psycopg.Connection, g: dict[str, Any]) -> None:
    other = make_grant(db)
    about = {
        "charge_id": make_charge(db, other),
        "record_id": make_bill(db, other),
        "file_id": make_file(db, other),
    }
    for column, subject_id in about.items():
        extra = {"bucket": "needs_human"} if column == "charge_id" else {"problems": OVER_LIMIT}
        rejects(
            db,
            errors.ForeignKeyViolation,
            "statuses",
            **status_values(g, **{column: subject_id}, **extra),
        )
        insert(db, "statuses", **status_values(other, **{column: subject_id}, **extra))
    insert(db, "statuses", **status_values(g, problems=OVER_LIMIT))  # the grant's own row


# The screen pings' Realtime policy.


def hears(db: psycopg.Connection, user_id: uuid.UUID, topic: str, extension: str) -> bool:
    """Whether a signed-in user, joined to `topic`, can read a message sent on it."""
    db.execute(
        "insert into realtime.messages (topic, extension, event, payload) "
        "values (%s, %s, 'changed', '{}')",
        [topic, extension],
    )
    db.execute("set local role authenticated")
    db.execute("select set_config('request.jwt.claim.sub', %s, true)", [str(user_id)])
    db.execute("select set_config('realtime.topic', %s, true)", [topic])
    row = db.execute(
        "select count(*) from realtime.messages where topic = %s and extension = %s",
        [topic, extension],
    ).fetchone()
    db.execute("reset role")
    return row == (1,)


def test_an_owner_hears_their_workspace_and_grant_pings(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    assert hears(db, g["user_id"], f"grant:{g['grant_id']}", "broadcast")
    assert hears(db, g["user_id"], f"workspace:{g['workspace_id']}", "broadcast")


def test_no_one_else_hears_them(db: psycopg.Connection, g: dict[str, Any]) -> None:
    stranger = make_grant(db)["user_id"]
    assert not hears(db, stranger, f"grant:{g['grant_id']}", "broadcast")
    assert not hears(db, stranger, f"workspace:{g['workspace_id']}", "broadcast")


@pytest.mark.parametrize("topic", ["grant:nope", "workspace:nope", "everyone", "grant:"])
def test_other_topics_are_heard_by_no_one(
    db: psycopg.Connection, g: dict[str, Any], topic: str
) -> None:
    assert not hears(db, g["user_id"], topic, "broadcast")


def test_only_broadcasts_are_heard(db: psycopg.Connection, g: dict[str, Any]) -> None:
    assert not hears(db, g["user_id"], f"grant:{g['grant_id']}", "presence")


# TRUNCATE, which row level security doesn't stop.


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_the_browsers_roles_cannot_truncate_any_table(db: psycopg.Connection, role: str) -> None:
    tables = db.execute(
        "select relname, has_table_privilege(%s, oid, 'TRUNCATE'), "
        "has_table_privilege(%s, oid, 'SELECT') "
        "from pg_class where relnamespace = 'public'::regnamespace and relkind = 'r'",
        [role, role],
    ).fetchall()
    assert {"records", "held_mail", "procrastinate_jobs"} <= {name for name, _, _ in tables}
    assert [name for name, truncate, _ in tables if truncate] == []
    # Supabase's other grants stay; row level security is what stops them.
    assert all(select for _, _, select in tables)


def test_tables_made_later_cannot_be_truncated_either(db: psycopg.Connection) -> None:
    db.execute("create table public.made_later (id int)")
    row = db.execute(
        "select has_table_privilege('anon', 'public.made_later', 'TRUNCATE'), "
        "has_table_privilege('authenticated', 'public.made_later', 'TRUNCATE')"
    ).fetchone()
    assert row == (False, False)
