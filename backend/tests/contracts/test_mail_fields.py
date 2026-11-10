"""The two fields issue 43 adds to the mail contract: a held message's skipped files, and
the grants whose first search has finished."""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts.mail import CheckerProgress, HeldFile, HeldMail, SkippedFile

NOW = datetime(2026, 2, 21, 12, tzinfo=UTC)


def skip(**values: Any) -> SkippedFile:
    row: dict[str, Any] = {
        "workspace_id": "ws-1",
        "grant_id": "grant-1",
        "name": "scan.tiff",
        "source": "gmail",
        "source_ref": "msg-1",
        "reason": "too_large",
        "skipped_at": NOW,
    }
    row.update(values)
    return SkippedFile.model_validate(row)


def held(**values: Any) -> HeldMail:
    row: dict[str, Any] = {
        "id": "held-1",
        "workspace_id": "ws-1",
        "grant_id": "grant-1",
        "sender": "someone@vendor.example",
        "reason": "unknown_sender",
        "source_ref": "msg-1",
        "held_at": NOW,
        "files": (
            HeldFile(
                name="message.eml",
                media_type="message/rfc822",
                storage_path="ws-1/grant-1/held-1/message.eml",
                sha256="0" * 64,
            ),
        ),
    }
    row.update(values)
    return HeldMail.model_validate(row)


def test_a_held_message_has_no_skipped_files_by_default() -> None:
    assert held().skipped == ()


def test_a_held_message_keeps_the_skipped_files_found_when_it_was_read() -> None:
    message = held(skipped=(skip(), skip(name="slides.key", reason="not_exportable")))
    assert [s.name for s in message.skipped] == ["scan.tiff", "slides.key"]
    # It round-trips, as the held mail row stores it.
    assert HeldMail.model_validate(message.model_dump(mode="json")) == message


@pytest.mark.parametrize(
    "other",
    [
        {"grant_id": "grant-2"},
        {"workspace_id": "ws-2"},
        {"source_ref": "msg-2"},
        {"source": "drive"},
    ],
)
def test_a_held_message_skipped_files_are_its_own(other: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="its own Gmail attachments"):
        held(skipped=(skip(**other),))


def test_checker_progress_starts_with_no_first_search_done() -> None:
    assert CheckerProgress().first_search_done == ()


def test_checker_progress_lists_the_grants_whose_first_search_finished() -> None:
    progress = CheckerProgress(mail_cursor="cursor-9", first_search_done=("grant-1", "grant-2"))
    assert CheckerProgress.model_validate(progress.model_dump(mode="json")) == progress
    assert "grant-3" not in progress.first_search_done
