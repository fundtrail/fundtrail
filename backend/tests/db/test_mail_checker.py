"""The scheduled Gmail and Drive checker: its routes, one checker at a time, and a check
that brings mail in through the sink."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contracts.workspaces import Grant, User
from app.db import actions, jobs, mail_checker, mail_sink, store
from app.db.platform import Platform
from app.db.pool import transaction
from app.ingest.sources import DiskMailbox
from tests.db.platform_fixtures import (  # noqa: F401 - fixtures
    new_auth_user,
    platform,
    platform_database_url,
)
from tests.ingest.mail_factory import MAILBOX, STRANGER, email

OWNER = "pat.rivera@university.example"
CLOCK = datetime(2026, 4, 10, 17, tzinfo=UTC)


def _grant(p: Platform, tag: str | None, *, clock: datetime | None = None) -> Grant:
    user_id = new_auth_user(p)
    with transaction(p.pool) as conn:
        store.upsert_user(conn, User(id=user_id, email=OWNER))
        workspace = store.create_workspace(conn, user_id, "Lab")
    grant = actions.add_grant(p, workspace.id, actions.Upload("letter.txt", "text/plain", b"NSF"))
    if clock is not None:
        with transaction(p.pool) as conn:
            store.set_grant_clock(conn, grant.id, clock)
    if tag is not None:
        with transaction(p.pool) as conn:
            conn.execute(
                "update public.grants set address_code = %s, drive_folder_id = 'f1' where id = %s",
                (tag, grant.id),
            )
    return grant


def _routes(p: Platform) -> dict[str, mail_checker.GrantRoute]:
    with transaction(p.pool) as conn:
        return {r.grant_id: r for r in mail_checker.routes(conn)}


def test_each_grant_with_an_address_is_a_route(platform: Platform) -> None:  # noqa: F811
    real = _grant(platform, "realtag2")
    sample = _grant(platform, "smpltag2", clock=CLOCK)
    none = _grant(platform, None)
    found = _routes(platform)
    assert none.id not in found
    route = found[real.id]
    assert route.tag == "realtag2" and route.drive_folder_id == "f1"
    assert OWNER in route.known_senders  # a member who can act
    assert not route.channel_times_from_grant_now
    assert found[sample.id].channel_times_from_grant_now


def test_nothing_runs_until_the_checker_is_set_up(
    platform: Platform,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_TOKEN_FILE", raising=False)
    monkeypatch.delenv("FUNDTRAIL_MAILBOX", raising=False)
    assert mail_checker.run(platform) is False


def test_one_checker_at_a_time(platform: Platform, tmp_path: Path) -> None:  # noqa: F811
    source = DiskMailbox(tmp_path)
    with platform.pool.connection() as other:
        other.execute("select pg_advisory_lock(hashtext(%s))", (mail_checker.LOCK_KEY,))
        try:
            assert mail_checker.run(platform, mail=source, mailbox=MAILBOX) is False
        finally:
            other.execute("select pg_advisory_unlock(hashtext(%s))", (mail_checker.LOCK_KEY,))
    assert mail_checker.run(platform, mail=source, mailbox=MAILBOX) is True


def test_a_check_brings_a_members_mail_in_and_holds_a_strangers(
    platform: Platform,  # noqa: F811
    tmp_path: Path,
) -> None:
    grant = _grant(platform, "chkrtag2")
    address = "fundtrail-demo+chkrtag2@mail.example"
    (tmp_path / "a1.eml").write_bytes(email(to=address, delivered_to=address).as_bytes())
    (tmp_path / "a2.eml").write_bytes(
        email(sender=STRANGER, to=address, delivered_to=address).as_bytes()
    )
    assert mail_checker.run(platform, mail=DiskMailbox(tmp_path), mailbox=MAILBOX)
    with transaction(platform.pool) as conn:
        files = store.list_files(conn, grant.id, datetime.max.replace(tzinfo=UTC))
        held = store.list_held_mail(conn, grant.workspace_id, datetime.max.replace(tzinfo=UTC))
    assert [f.source_ref for f in files if f.source == "gmail"] == ["a1"]
    assert [h.source_ref for h in held] == ["a2"]


def test_the_check_is_scheduled_with_one_lock() -> None:
    task = jobs.app.tasks["check_mail_and_drive"]
    assert task.lock == "mail_checker" and task.queueing_lock == "mail_checker"


def test_the_lock_is_held_by_an_idle_session_not_an_open_transaction(
    platform: Platform,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """During the check, the session holding the checker's lock isn't idle in a
    transaction, so an idle-transaction timeout can't drop the lock mid-check."""
    states: list[str] = []

    def check(*args: object, **kwargs: object) -> None:
        with transaction(platform.pool) as conn:
            rows = conn.execute(
                """select a.state from pg_locks l join pg_stat_activity a on a.pid = l.pid
                   where l.locktype = 'advisory' and l.granted and a.pid <> pg_backend_pid()"""
            ).fetchall()
        states.extend(r["state"] for r in rows)

    monkeypatch.setattr(mail_sink, "check_and_save", check)
    assert mail_checker.run(platform, mail=DiskMailbox(Path(".")), mailbox=MAILBOX)
    assert states == ["idle"]
