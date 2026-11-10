"""Held mail (decision 0025): it's a problem-list row and in the report while
rules.still_held says it's held; once it isn't, its files arrive at the grant's "now"."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.api.report import report_inputs
from app.api.views import load_snapshot, problem_rows
from app.contracts.api import HeldMailRow
from app.contracts.mail import HoldReason, SkippedFile, SkipReason
from app.contracts.rules import RecordState
from app.contracts.runs import TriggerKind
from app.contracts.workspaces import Grant, User
from app.db import actions, store
from app.db.held_mail import known_senders
from app.db.mail_sink import DbSink
from app.db.platform import Platform
from app.db.pool import transaction
from app.ingest.incoming import IncomingFile, PendingHold
from tests.db.platform_fixtures import (  # noqa: F401 - fixtures
    new_auth_user,
    platform,
    platform_database_url,
)

STRANGER = "billing@vendor.example"
CLOCK = datetime(2026, 4, 10, 17, tzinfo=UTC)
HELD_AT = datetime(2026, 4, 2, 9, tzinfo=UTC)
SENT = date(2026, 3, 30)


def _grant(p: Platform) -> tuple[Grant, str]:
    user_id = new_auth_user(p)
    with transaction(p.pool) as conn:
        store.upsert_user(conn, User(id=user_id, email="pat@university.example"))
        workspace = store.create_workspace(conn, user_id, "Lab")
        # A grant on a stored clock, with its award letter arriving at that clock's now.
        grant = store.create_grant(conn, workspace.id)
        store.set_grant_clock(conn, grant.id, CLOCK)
    actions.add_evidence(p, grant, actions.Upload("letter.txt", "text/plain", b"NSF"))
    return grant, user_id


def _hold(p: Platform, grant: Grant, message_id: str = "m1") -> str:
    def part(key: str, name: str, data: bytes, parent: str | None = None) -> IncomingFile:
        return IncomingFile(
            key=key,
            grant_id=grant.id,
            workspace_id=grant.workspace_id,
            source="gmail",
            name=name,
            media_type="text/plain",
            data=data,
            # The message carries its Date header's date; an attachment carries none.
            document_date=None if parent else SENT,
            sender=STRANGER,
            source_ref=message_id,
            parent_key=parent,
        )

    skip = SkippedFile(
        workspace_id=grant.workspace_id,
        grant_id=grant.id,
        name="scan.tiff",
        source="gmail",
        source_ref=message_id,
        reason=SkipReason.TOO_LARGE,
        skipped_at=HELD_AT,
    )
    DbSink(p).hold(
        PendingHold(
            workspace_id=grant.workspace_id,
            grant_id=grant.id,
            sender=STRANGER,
            from_header=f"Billing <{STRANGER}>",
            gmail_message_id=message_id,
            subject="Invoice INV-1001",
            files=(
                part(message_id, "message.txt", b"Invoice attached."),
                part(f"{message_id}:1", "invoice.txt", b"Total: $1.00", parent=message_id),
            ),
            held_at=HELD_AT,
            reason=HoldReason.UNKNOWN_SENDER,
            skipped=(skip,),
        )
    )
    with transaction(p.pool) as conn:
        [held] = [h for h in store.list_held_mail(conn, grant.workspace_id, CLOCK)]
    return held.id


def _held_rows(p: Platform, grant: Grant) -> list[str]:
    with transaction(p.pool) as conn:
        snap = load_snapshot(p, conn, grant)
    return [row.held.id for row in problem_rows(snap) if isinstance(row, HeldMailRow)]


def _mail(p: Platform, grant: Grant) -> list[tuple[str, datetime, str | None]]:
    with transaction(p.pool) as conn:
        files = store.list_files(conn, grant.id, CLOCK)
    return [(f.name, f.arrived_at, f.parent_id) for f in files if f.source == "gmail"]


def test_held_mail_is_a_row_and_in_the_report_until_let_in(
    platform: Platform,  # noqa: F811
) -> None:
    grant, user_id = _grant(platform)
    held_id = _hold(platform, grant)
    assert _held_rows(platform, grant) == [held_id]
    with transaction(platform.pool) as conn:
        inputs = report_inputs(platform, conn, grant, CLOCK, user_id, None)
    assert [h.id for h in inputs.held_mail] == [held_id]
    assert _mail(platform, grant) == []

    actions.add_record(
        platform,
        grant,
        user_id,
        {"kind": "mail_action", "held_mail_id": held_id, "action": "let_in"},
        None,
    )
    assert _held_rows(platform, grant) == []
    names = [(name, at) for name, at, _ in _mail(platform, grant)]
    assert sorted(names) == [("invoice.txt", CLOCK), ("message.txt", CLOCK)]
    [attachment, message] = sorted(_mail(platform, grant))
    assert message[2] is None and attachment[2] is not None
    with transaction(platform.pool) as conn:
        skipped = store.list_skipped(conn, grant.id, CLOCK)
        runs = store.list_runs(conn, grant.id)
        files = store.list_files(conn, grant.id, CLOCK)
    assert [(s.name, s.skipped_at) for s in skipped] == [("scan.tiff", CLOCK)]
    arrived = {f.id for f in files if f.source == "gmail"}
    assert {r.trigger.id for r in runs if r.trigger.kind == TriggerKind.FILE} >= arrived
    # The stored bytes are the held file's.
    stored = {f.name: platform.storage.get(f.storage_path) for f in files if f.source == "gmail"}
    assert stored == {"message.txt": b"Invoice attached.", "invoice.txt": b"Total: $1.00"}


def test_a_dismissed_message_never_arrives(platform: Platform) -> None:  # noqa: F811
    grant, user_id = _grant(platform)
    held_id = _hold(platform, grant)
    actions.add_record(
        platform,
        grant,
        user_id,
        {"kind": "mail_action", "held_mail_id": held_id, "action": "dismiss"},
        None,
    )
    assert _held_rows(platform, grant) == []
    assert _mail(platform, grant) == []
    with transaction(platform.pool) as conn:
        assert store.list_skipped(conn, grant.id, CLOCK) == []


def test_making_the_sender_known_lets_their_mail_in(platform: Platform) -> None:  # noqa: F811
    grant, user_id = _grant(platform)
    _hold(platform, grant)
    actions.add_record(
        platform,
        grant,
        user_id,
        {
            "kind": "person",
            "name": {"value": "Vendor billing"},
            "email": {"value": STRANGER},
            "role": {"value": "Vendor"},
        },
        None,
    )
    assert _held_rows(platform, grant) == []
    assert sorted(name for name, _, _ in _mail(platform, grant)) == ["invoice.txt", "message.txt"]
    # Another record later doesn't bring the message a second time.
    actions.add_record(
        platform,
        grant,
        user_id,
        {"kind": "other_term", "label": "Note", "statement": {"value": "Look."}},
        None,
    )
    assert len(_mail(platform, grant)) == 2


def test_dismissed_beats_a_sender_becoming_known(platform: Platform) -> None:  # noqa: F811
    grant, user_id = _grant(platform)
    held_id = _hold(platform, grant)
    actions.add_record(
        platform,
        grant,
        user_id,
        {"kind": "mail_action", "held_mail_id": held_id, "action": "dismiss"},
        None,
    )
    actions.add_record(
        platform,
        grant,
        user_id,
        {
            "kind": "person",
            "name": {"value": "Vendor billing"},
            "email": {"value": STRANGER},
            "role": {"value": "Vendor"},
        },
        None,
    )
    assert _mail(platform, grant) == []


def test_on_a_sample_grant_a_let_in_message_takes_the_samples_sent_date(
    platform: Platform,  # noqa: F811
) -> None:
    """The workspace's clock is stored (a sample grant): the message's Date header said
    March 30, but at let-in it takes the sample's sent date, the held time's UTC date."""
    grant, user_id = _grant(platform)
    assert SENT != HELD_AT.date()
    held_id = _hold(platform, grant)
    actions.add_record(
        platform,
        grant,
        user_id,
        {"kind": "mail_action", "held_mail_id": held_id, "action": "let_in"},
        None,
    )
    with transaction(platform.pool) as conn:
        files = store.list_files(conn, grant.id, CLOCK)
    dates = {f.name: f.document_date for f in files if f.source == "gmail"}
    assert dates == {"message.txt": HELD_AT.date(), "invoice.txt": None}


def test_on_a_real_date_grant_a_let_in_message_keeps_its_header_date(
    platform: Platform,  # noqa: F811
) -> None:
    grant, user_id = _grant(platform)
    with transaction(platform.pool) as conn:
        conn.execute("update public.grants set clock_now = null where id = %s", (grant.id,))
    held_id = _hold(platform, grant)
    actions.add_record(
        platform,
        grant,
        user_id,
        {"kind": "mail_action", "held_mail_id": held_id, "action": "let_in"},
        None,
    )
    with transaction(platform.pool) as conn:
        files = store.list_files(conn, grant.id, datetime.max.replace(tzinfo=UTC))
    dates = {f.name: f.document_date for f in files if f.source == "gmail"}
    assert dates == {"message.txt": SENT, "invoice.txt": None}


def test_known_senders_are_the_terms_people_and_the_members_who_can_act(
    platform: Platform,  # noqa: F811
) -> None:
    grant, _ = _grant(platform)
    with transaction(platform.pool) as conn:
        state = RecordState(store.list_records(conn, grant.id))
        known = known_senders(conn, grant, state)
        sample = store.get_user(conn, store.sample_accountant_id(conn, grant.workspace_id))
    assert "pat@university.example" in known
    assert sample is not None and sample.email not in known
