"""Channel times on a sample grant: the grant's "now" replaces an email's sent date."""

from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.agent.files import describe
from app.ingest.channel_times import reading_text, sample_sent_date
from app.ingest.checker import CheckState, check_mail
from app.ingest.incoming import GrantRoute, IncomingFile, to_evidence_file
from app.ingest.sources import DiskMailbox

from .mail_factory import MAILBOX, PI, email, forwarding, with_attachments

SENT_2019 = "Tue, 12 Mar 2019 10:00:00 -0800"
SAMPLE_NOW = datetime(2026, 6, 2, 15, 30, tzinfo=UTC)


class Sink:
    def __init__(self) -> None:
        self.stored: list[IncomingFile] = []

    def store(self, files, skipped=()) -> None:
        self.stored.extend(files)

    def hold(self, held) -> None:
        raise AssertionError("not held")

    def skip(self, skipped) -> None:
        raise AssertionError("not skipped")


def take(tmp_path: Path, msg, *, sample: bool) -> list[IncomingFile]:
    folder = tmp_path / "mail"
    folder.mkdir()
    (folder / "001.eml").write_bytes(msg.as_bytes())
    route = GrantRoute(
        "w1", "g1", "abc23def", known_senders=frozenset({PI}), channel_times_from_grant_now=sample
    )
    sink = Sink()
    check_mail(
        DiskMailbox(folder),
        mailbox=MAILBOX,
        routes=[route],
        state=CheckState(),
        now=lambda _grant_id: SAMPLE_NOW,
        sink=sink,
    )
    return sink.stored


def test_a_2019_email_on_a_sample_grant_takes_the_grants_now(tmp_path: Path) -> None:
    msg = with_attachments(email(sent=SENT_2019))
    stored = take(tmp_path, msg, sample=True)
    message = stored[0]
    assert message.arrived_at == SAMPLE_NOW
    assert message.document_date == date(2026, 6, 2)
    # The stored original is unchanged: it still says 2019.
    assert message.data == msg.as_bytes() and b"2019" in message.data
    # An attachment carries no sent date of its own, as on any grant.
    assert stored[1].document_date is None

    # What the agent is given: the file line shows the grant's now, and so does the text.
    evidence = to_evidence_file(message, file_id="f1", parent_id=None)
    assert "dated 2026-06-02" in describe(evidence) and "2019" not in describe(evidence)
    reading = reading_text(message.data.decode(), SAMPLE_NOW)
    assert "Date: Tue, 02 Jun 2026 15:30:00 +0000" in reading.text
    assert "2019" not in reading.text


def test_an_ordinary_grant_keeps_the_header_date(tmp_path: Path) -> None:
    msg = email(sent=SENT_2019)
    (message,) = take(tmp_path, msg, sample=False)
    assert message.document_date == date(2019, 3, 12)
    evidence = to_evidence_file(message, file_id="f1", parent_id=None)
    assert "dated 2019-03-12" in describe(evidence)
    stored_text = message.data.decode()
    assert reading_text(stored_text, None).text == stored_text


def test_reading_text_maps_back_to_the_stored_file() -> None:
    stored = email(sent=SENT_2019, body="Approved for SYN-2401. Pat").as_bytes().decode()
    reading = reading_text(stored, SAMPLE_NOW)
    quote = "Approved for SYN-2401"
    at = reading.text.index(quote)
    assert stored[reading.stored_index(at) :].startswith(quote)
    # A position inside the replaced header maps to the start of the original header.
    header_at = reading.text.index("Date: ")
    assert stored[reading.stored_index(header_at + 10) :].startswith("Date: Tue, 12 Mar 2019")
    # Before the header, positions are the same.
    assert reading.stored_index(0) == 0


def test_a_forwarded_messages_own_date_is_what_the_sender_wrote() -> None:
    inner = email(sender="vendor@vendor.example", subject="Invoice", sent=SENT_2019)
    outer = forwarding(inner)
    stored = outer.as_bytes().decode()
    reading = reading_text(stored, SAMPLE_NOW)
    assert reading.text.count("Date: Tue, 02 Jun 2026") == 1  # only the outer header
    assert "12 Mar 2019" in reading.text  # the forwarded message's header, in the body


def test_the_grants_now_is_read_in_utc_and_must_be_aware() -> None:
    late_pacific = datetime(2026, 6, 2, 20, 0, tzinfo=timezone(timedelta(hours=-7)))
    assert sample_sent_date(late_pacific) == date(2026, 6, 3)
    with pytest.raises(ValueError):
        sample_sent_date(datetime(2026, 6, 2, 20, 0))
