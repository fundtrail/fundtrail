"""Smoke test against the real Gmail and Drive. Skipped unless the app's Google account is set up.

Run it with:
    GOOGLE_TOKEN_FILE=~/.config/fundtrail/google-token.json \\
    FUNDTRAIL_SMOKE_DRIVE_FOLDER=<folder link> uv run pytest tests/ingest/test_google_smoke.py

It only reads. It checks that both clients connect, that Gmail gives a starting cursor,
and that the shared folder lists.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GOOGLE_TOKEN_FILE"), reason="needs the app's Google account"
)


def test_gmail_connects() -> None:
    from app.ingest.google_clients import GmailMailbox, load_credentials

    mailbox = GmailMailbox(load_credentials())
    messages, cursor = mailbox.fetch_new(None)
    assert messages == [] and cursor
    _, again = mailbox.fetch_new(cursor)
    assert again


def test_drive_folder_lists() -> None:
    link = os.environ.get("FUNDTRAIL_SMOKE_DRIVE_FOLDER")
    if not link:
        pytest.skip("FUNDTRAIL_SMOKE_DRIVE_FOLDER is not set")
    from app.ingest.drive_files import folder_id_from_link
    from app.ingest.google_clients import GoogleDrive, load_credentials

    entries = GoogleDrive(load_credentials()).list_tree(folder_id_from_link(link))
    assert all(e.id and e.name for e in entries)
