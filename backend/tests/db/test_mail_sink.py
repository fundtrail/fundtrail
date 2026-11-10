"""The checker's sink: what Gmail and Drive bring is stored once, even when the checker
lost its progress and brings it again, and the checker's progress is saved."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.contracts.mail import CheckerProgress, DriveVersion, HoldReason, SkippedFile, SkipReason
from app.contracts.workspaces import Grant, User
from app.db import actions, mail_sink, store
from app.db.mail_sink import DbSink, check_and_save, drive_version, merged_progress
from app.db.platform import Platform
from app.db.pool import transaction
from app.ingest.checker import CheckState, check_drive, check_mail
from app.ingest.drive_files import SETTLE, drive_file, version_of
from app.ingest.incoming import GrantRoute, IncomingFile, PendingHold
from app.ingest.sources import DiskDrive, DiskMailbox, DriveEntry
from tests.db.platform_fixtures import (  # noqa: F401 - fixtures
    FakeChecks,
    new_auth_user,
    platform,
    platform_database_url,
)
from tests.ingest.mail_factory import MAILBOX, PI, STRANGER, email, with_attachments

AT = datetime(2026, 4, 1, 9, tzinfo=UTC)


def _now(_workspace_id: str) -> datetime:
    return AT


def _grant(p: Platform) -> Grant:
    user_id = new_auth_user(p)
    with transaction(p.pool) as conn:
        store.upsert_user(conn, User(id=user_id, email="pat@university.example"))
        workspace = store.create_workspace(conn, user_id, "Lab")
    return actions.add_grant(p, workspace.id, actions.Upload("letter.txt", "text/plain", b"NSF"))


def _route(grant: Grant, folder: str = "folder1") -> GrantRoute:
    return GrantRoute(
        workspace_id=grant.workspace_id,
        grant_id=grant.id,
        tag="abc23def",
        drive_folder_id=folder,
        known_senders=frozenset({PI}),
        address_created_at=datetime(2026, 3, 1, tzinfo=UTC),
    )


def _touch(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    stamp = (datetime.now(UTC) - SETTLE * 2).timestamp()
    os.utime(path, (stamp, stamp))


def _files(p: Platform, grant: Grant, source: str) -> list[str]:
    with transaction(p.pool) as conn:
        return [f.name for f in store.list_files(conn, grant.id, AT) if f.source == source]


def _progress(p: Platform) -> CheckerProgress:
    with transaction(p.pool) as conn:
        return store.lock_progress(conn)


def test_drive_version_reads_the_checkers_key(tmp_path: Path) -> None:
    _touch(tmp_path / "f" / "quote.pdf", b"%PDF quote")
    source = DiskDrive(tmp_path)
    [entry] = source.list_tree("f")
    assert isinstance(entry, DriveEntry)
    incoming = drive_file(source, entry, grant_id="g", workspace_id="w")
    assert drive_version(incoming) == version_of(entry)


def test_a_drive_file_brought_again_is_stored_once(
    platform: Platform,  # noqa: F811
    tmp_path: Path,
) -> None:
    grant = _grant(platform)
    _touch(tmp_path / "folder1" / "quote.pdf", b"%PDF quote v1")
    source, sink = DiskDrive(tmp_path), DbSink(platform)
    # A fresh state each time: the checker lost its progress after storing.
    for _ in range(2):
        check_drive(source, routes=[_route(grant)], state=CheckState(), now=_now, sink=sink)
    assert _files(platform, grant, "drive") == ["quote.pdf"]
    [version] = [v for v in _progress(platform).drive_versions if v.grant_id == grant.id]
    # A new version is a new file.
    _touch(tmp_path / "folder1" / "quote.pdf", b"%PDF quote v2")
    check_drive(source, routes=[_route(grant)], state=CheckState(), now=_now, sink=sink)
    assert _files(platform, grant, "drive") == ["quote.pdf", "quote.pdf"]
    [newer] = [v for v in _progress(platform).drive_versions if v.grant_id == grant.id]
    assert newer.version != version.version
    with transaction(platform.pool) as conn:
        runs = store.list_runs(conn, grant.id)
    assert sum(r.trigger.kind == "file" for r in runs) == 3  # the letter and two versions


def test_a_message_brought_again_is_stored_or_held_once(
    platform: Platform,  # noqa: F811
    tmp_path: Path,
) -> None:
    grant = _grant(platform)
    folder = tmp_path / "mail"
    folder.mkdir()
    source, sink = DiskMailbox(folder), DbSink(platform)
    address = f"{MAILBOX.split('@')[0]}+abc23def@{MAILBOX.split('@')[1]}"
    (folder / "m1.eml").write_bytes(with_attachments(email(delivered_to=address)).as_bytes())
    (folder / "m2.eml").write_bytes(email(sender=STRANGER, delivered_to=address).as_bytes())
    for _ in range(2):
        check_mail(
            source, mailbox=MAILBOX, routes=[_route(grant)], state=CheckState(), now=_now, sink=sink
        )
    assert len(_files(platform, grant, "gmail")) == 2  # the message and its attachment
    with transaction(platform.pool) as conn:
        held = store.list_held_mail(conn, grant.workspace_id, AT)
    assert [h.source_ref for h in held] == ["m2"]
    assert {"m1", "m2"} <= set(_progress(platform).seen_message_ids)


def test_a_skipped_file_reported_again_is_saved_once_and_reaches_the_checks(
    platform: Platform,  # noqa: F811
) -> None:
    grant = _grant(platform)
    skipped = SkippedFile(
        workspace_id=grant.workspace_id,
        grant_id=grant.id,
        name="Board.gdraw",
        source="drive",
        source_ref="folder1",
        reason=SkipReason.NOT_EXPORTABLE,
        skipped_at=AT,
    )
    sink = DbSink(platform)
    sink.skip(skipped)
    sink.skip(skipped)
    with transaction(platform.pool) as conn:
        assert store.list_skipped(conn, grant.id, AT) == [skipped]
    checks = platform.checks
    assert isinstance(checks, FakeChecks)
    assert checks.calls[-1].skipped_files == (skipped,)


def test_check_and_save_saves_the_checkers_progress(
    platform: Platform,  # noqa: F811
    tmp_path: Path,
) -> None:
    grant = _grant(platform)
    _touch(tmp_path / "folder1" / "quote.pdf", b"%PDF quote")
    source = DiskDrive(tmp_path)
    check_and_save(
        platform, mail=None, drive=source, mailbox=MAILBOX, routes=[_route(grant)], now=_now
    )
    check_and_save(
        platform, mail=None, drive=source, mailbox=MAILBOX, routes=[_route(grant)], now=_now
    )
    assert _files(platform, grant, "drive") == ["quote.pdf"]
    saved = CheckState.from_progress(_progress(platform))
    assert (grant.id, "folder1/quote.pdf") in saved.drive.taken


def _message(grant: Grant, message_id: str) -> list[IncomingFile]:
    return [
        IncomingFile(
            key=message_id,
            grant_id=grant.id,
            workspace_id=grant.workspace_id,
            source="gmail",
            name="message.txt",
            media_type="text/plain",
            data=b"Approved.",
            document_date=date(2026, 3, 3),
            sender=STRANGER,
            source_ref=message_id,
        )
    ]


def _pending(grant: Grant, message_id: str) -> PendingHold:
    return PendingHold(
        workspace_id=grant.workspace_id,
        grant_id=grant.id,
        sender=STRANGER,
        from_header=STRANGER,
        gmail_message_id=message_id,
        subject=None,
        files=tuple(_message(grant, message_id)),
        held_at=AT,
        reason=HoldReason.UNKNOWN_SENDER,
    )


def _held(p: Platform, grant: Grant) -> list[str]:
    with transaction(p.pool) as conn:
        return [h.source_ref for h in store.list_held_mail(conn, grant.workspace_id, AT)]


def test_one_check_keeps_a_message_from_being_both_held_and_arrived(
    platform: Platform,  # noqa: F811
) -> None:
    grant, sink = _grant(platform), DbSink(platform)
    sink.store([f.arriving(AT) for f in _message(grant, "arrived")])
    sink.hold(_pending(grant, "arrived"))
    assert _held(platform, grant) == []
    sink.hold(_pending(grant, "held"))
    sink.store([f.arriving(AT) for f in _message(grant, "held")])
    assert _held(platform, grant) == ["held"]
    assert _files(platform, grant, "gmail") == ["message.txt"]  # only "arrived"


def test_a_held_file_keeps_its_sent_date(platform: Platform) -> None:  # noqa: F811
    grant = _grant(platform)
    DbSink(platform).hold(_pending(grant, "m1"))
    with transaction(platform.pool) as conn:
        [held] = store.list_held_mail(conn, grant.workspace_id, AT)
    assert [f.document_date for f in held.files] == [date(2026, 3, 3)]


def test_a_checks_save_keeps_what_a_concurrent_check_saved(
    platform: Platform,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grant = _grant(platform)
    other = DriveVersion(grant_id=grant.id, drive_file_id="f/other.pdf", version="md5:1")

    def concurrent(**kwargs: object) -> None:
        state = kwargs["state"]
        assert isinstance(state, CheckState)
        state.mail_cursor = "next"
        state.seen_messages.add("mine")
        with transaction(platform.pool) as conn:  # another check's sink saves meanwhile
            saved = store.lock_progress(conn)
            store.save_progress(
                conn,
                saved.model_copy(
                    update={
                        "seen_message_ids": (*saved.seen_message_ids, "theirs"),
                        "drive_versions": (*saved.drive_versions, other),
                    }
                ),
            )

    monkeypatch.setattr(mail_sink, "check_once", concurrent)
    check_and_save(platform, mail=None, drive=None, mailbox=MAILBOX, routes=[], now=_now)
    saved = _progress(platform)
    assert {"mine", "theirs"} <= set(saved.seen_message_ids)
    assert other in saved.drive_versions
    assert saved.mail_cursor == "next"


def test_merged_progress_keeps_the_stored_version_of_a_file() -> None:
    old = DriveVersion(grant_id="g", drive_file_id="f", version="md5:old")
    new = DriveVersion(grant_id="g", drive_file_id="f", version="md5:new")
    stored = CheckerProgress(mail_cursor="b", drive_versions=(new,), first_search_done=("g1",))
    checked = CheckerProgress(mail_cursor=None, drive_versions=(old,), first_search_done=("g2",))
    merged = merged_progress(stored, checked)
    assert merged.drive_versions == (new,)
    assert merged.mail_cursor == "b"
    assert merged.first_search_done == ("g1", "g2")
