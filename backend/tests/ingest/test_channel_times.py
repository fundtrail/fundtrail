"""Channel times on a sample grant: the grant's "now" replaces an email's sent date."""

from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.agent.files import describe
from app.contracts.api import ReadingView, TextSegment
from app.ingest import channel_times
from app.ingest.channel_times import check_segments, reading_text, reading_view, sample_sent_date
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
    # A kept header maps to itself, past the dropped Authentication-Results above it.
    from_at = reading.text.index("From: ")
    assert stored[reading.stored_index(from_at) :].startswith("From: ")


# A message as Gmail delivers it: trace headers carrying the real delivery time in 2026,
# and an original Date in 2019.
GMAIL_STYLE = (
    "Delivered-To: fundtrail-demo+abc23def@mail.example\r\n"
    "Received: by 2002:a05:6a10:1234 with SMTP id abc;\r\n"
    "        Wed, 11 Nov 2026 08:14:03 -0800 (PST)\r\n"
    "X-Received: by 2002:a17:90a:5678 with SMTP id def;\r\n"
    "        Wed, 11 Nov 2026 08:14:02 -0800 (PST)\r\n"
    "ARC-Seal: i=1; a=rsa-sha256; t=1794413643; cv=none;\r\n"
    "        d=google.com; s=arc-20240605; b=AbCdEf\r\n"
    "DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed; d=university.example;\r\n"
    "        s=s1; t=1794413642; h=from:to:subject:date; bh=xyz; b=uvw\r\n"
    "Authentication-Results: mx.google.com; dmarc=pass header.from=university.example\r\n"
    "Return-Path: <pat.rivera@university.example>\r\n"
    "Date : Tue, 12 Mar 2019 10:00:00 -0800\r\n"
    "From: Pat <pat.rivera@university.example>\r\n"
    "To: fundtrail-demo+abc23def@mail.example\r\n"
    "Cc: Lab <lab@university.example>\r\n"
    "Subject: Approval for sequencing, award SYN-2401\r\n"
    "Message-ID: <synthetic-1@university.example>\r\n"
    "MIME-Version: 1.0\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "Content-Transfer-Encoding: 8bit\r\n"
    "\r\n"
    "Approved for SYN-2401. Pat\r\n"
)


def test_no_real_time_survives_in_a_gmail_style_message() -> None:
    reading = reading_text(GMAIL_STYLE, SAMPLE_NOW)
    text = reading.text
    for real in ("2026 08:14", "Nov 2026", "1794413643", "1794413642", "2019"):
        assert real not in text
    head = text.split("\r\n\r\n", 1)[0].split("\r\n")
    assert head == [
        "Date: Tue, 02 Jun 2026 15:30:00 +0000",  # `Date :` with a space is caught too
        "From: Pat <pat.rivera@university.example>",
        "To: fundtrail-demo+abc23def@mail.example",
        "Cc: Lab <lab@university.example>",
        "Subject: Approval for sequencing, award SYN-2401",
        # The MIME headers carry no time and say how to read the body (ruling 42 amended).
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "Content-Transfer-Encoding: 8bit",
    ]
    # Citations map exactly back into the stored file, for every kept character.
    for quote in ("Approval for sequencing", "Cc: Lab", "Approved for SYN-2401. Pat"):
        at = text.index(quote)
        start = reading.stored_index(at)
        assert GMAIL_STYLE[start : start + len(quote)] == quote
        end = reading.stored_index(at + len(quote) - 1) + 1
        assert GMAIL_STYLE[start:end] == quote
    body_at = text.index("Approved")
    assert reading.stored_index(len(text)) - reading.stored_index(body_at) == len(
        "Approved for SYN-2401. Pat\r\n"
    )


def test_a_forwarded_messages_own_date_is_what_the_sender_wrote() -> None:
    inner = email(sender="vendor@vendor.example", subject="Invoice", sent=SENT_2019)
    outer = forwarding(inner)
    stored = outer.as_bytes().decode()
    reading = reading_text(stored, SAMPLE_NOW)
    assert reading.text.count("Date: Tue, 02 Jun 2026") == 1  # only the outer header
    assert "12 Mar 2019" in reading.text  # the forwarded message's header, in the body


def test_a_multipart_message_keeps_its_mime_headers_and_boundary() -> None:
    msg = with_attachments(email(sent=SENT_2019))
    stored = msg.as_bytes().decode()
    reading = reading_text(stored, SAMPLE_NOW)
    boundary = msg.get_boundary()
    assert boundary is not None
    head = reading.text.split("\n\n", 1)[0]
    assert "MIME-Version: 1.0" in head
    assert "Content-Type: multipart/mixed" in head and f'boundary="{boundary}"' in head
    # The parts are still delimited by that boundary in the body the agent reads.
    assert reading.text.count(f"--{boundary}") == stored.count(f"--{boundary}")
    assert "Authentication-Results" not in head and "2019" not in head


def test_the_grants_now_is_read_in_utc_and_must_be_aware() -> None:
    late_pacific = datetime(2026, 6, 2, 20, 0, tzinfo=timezone(timedelta(hours=-7)))
    assert sample_sent_date(late_pacific) == date(2026, 6, 3)
    with pytest.raises(ValueError):
        sample_sent_date(datetime(2026, 6, 2, 20, 0))


# The viewer's segments (ruling 45)

# Non-ASCII text and an invalid UTF-8 byte, so positions are characters of the text
# decoded as open_file decodes it.
GMAIL_STYLE_BYTES = GMAIL_STYLE.replace("Pat\r\n", "Pat, café\r\n").encode() + b"\xff end\r\n"


def test_every_stored_position_in_a_kept_span_maps_forward_and_back_exactly() -> None:
    view = reading_view(GMAIL_STYLE_BYTES, SAMPLE_NOW)
    decoded = GMAIL_STYLE_BYTES.decode("utf-8", errors="replace")
    reading = reading_text(decoded, SAMPLE_NOW)
    assert view.text == reading.text
    previous_stored = previous_reading = 0
    covered = 0
    for segment in view.segments:
        # In order, and not overlapping, in both texts.
        assert segment.stored_start >= previous_stored
        assert segment.reading_start >= previous_reading
        assert segment.length > 0
        for offset in range(segment.length):
            stored_at = segment.stored_start + offset
            reading_at = segment.reading_start + offset
            assert view.text[reading_at] == decoded[stored_at]  # forward
            assert reading.stored_index(reading_at) == stored_at  # back
        previous_stored = segment.stored_start + segment.length
        previous_reading = segment.reading_start + segment.length
        covered += segment.length
    # What no segment covers in the reading text is the grant's now in the Date header.
    assert len(view.text) - covered == len("Date: Tue, 02 Jun 2026 15:30:00 +0000\r\n")
    assert "café" in view.text and "� end" in view.text


def test_a_grant_on_the_real_date_is_one_segment() -> None:
    view = reading_view(GMAIL_STYLE_BYTES, None)
    decoded = GMAIL_STYLE_BYTES.decode("utf-8", errors="replace")
    assert view.text == decoded
    assert [(s.stored_start, s.reading_start, s.length) for s in view.segments] == [
        (0, 0, len(decoded))
    ]


def test_the_view_is_the_contracts() -> None:
    view = reading_view(GMAIL_STYLE_BYTES, SAMPLE_NOW)
    assert isinstance(view, ReadingView)
    assert all(isinstance(s, TextSegment) for s in view.segments)


@pytest.mark.parametrize(
    "spans",
    [
        [(0, 0, 5), (3, 10, 2)],  # overlapping in the stored text
        [(0, 6, 5), (8, 2, 2)],  # out of order in the reading text
        [(0, 0, 11)],  # past the end of the stored text
        [(0, 5, 6)],  # past the end of the reading text
        [(0, 0, 0)],  # empty
    ],
)
def test_bad_segments_are_refused(spans) -> None:
    with pytest.raises(ValueError):
        check_segments(spans, stored_length=10, reading_length=10)


# A citation's end, and mail with bare CR line endings (recheck of PR 168)

SUBJECT_THEN_RECEIVED = (
    "From: Pat <pat.rivera@university.example>\r\n"
    "Subject: Approval for SYN-2401\r\n"
    "Received: by 2002:a05:6a10:1234 with SMTP id abc;\r\n"
    "        Wed, 11 Nov 2026 08:14:03 -0800 (PST)\r\n"
    "Date: Tue, 12 Mar 2019 10:00:00 -0800\r\n"
    "\r\n"
    "Approved. Pat\r\n"
)


def test_a_citation_ending_at_a_kept_line_doesnt_pull_in_the_dropped_header_after_it() -> None:
    reading = reading_text(SUBJECT_THEN_RECEIVED, SAMPLE_NOW)
    quote = "Subject: Approval for SYN-2401\r\n"
    start = reading.text.index(quote)
    end = start + len(quote)
    # Mapping the end position itself lands after the dropped Received line.
    assert "2026" in SUBJECT_THEN_RECEIVED[reading.stored_index(start) : reading.stored_index(end)]
    stored_start, stored_end = reading.stored_range(start, end)
    assert SUBJECT_THEN_RECEIVED[stored_start:stored_end] == quote


def test_stored_range_handles_empty_ranges_and_the_replaced_date() -> None:
    reading = reading_text(SUBJECT_THEN_RECEIVED, SAMPLE_NOW)
    at = reading.text.index("Approved")
    assert reading.stored_range(at, at) == (reading.stored_index(at),) * 2
    date_at = reading.text.index("Date: ")
    date_end = reading.text.index("\r\n", date_at) + 2
    stored_start, stored_end = reading.stored_range(date_at, date_end)
    assert SUBJECT_THEN_RECEIVED[stored_start:stored_end] == (
        "Date: Tue, 12 Mar 2019 10:00:00 -0800\r\n"
    )
    body = "Approved. Pat"
    stored_start, stored_end = reading.stored_range(at, at + len(body))
    assert SUBJECT_THEN_RECEIVED[stored_start:stored_end] == body


def test_bare_cr_line_endings_are_read_and_map_exactly() -> None:
    stored = SUBJECT_THEN_RECEIVED.replace("\r\n", "\r")
    reading = reading_text(stored, SAMPLE_NOW)
    assert "2026 08:14" not in reading.text and "2019" not in reading.text
    assert reading.text.startswith("From: Pat")
    assert "Date: Tue, 02 Jun 2026 15:30:00 +0000\r" in reading.text
    body = "Approved. Pat"
    at = reading.text.index(body)
    stored_start, stored_end = reading.stored_range(at, at + len(body))
    assert stored[stored_start:stored_end] == body


def test_a_lone_cr_inside_a_header_doesnt_raise() -> None:
    stored = SUBJECT_THEN_RECEIVED.replace("Approval for", "Approval\rfor", 1)
    reading = reading_text(stored, SAMPLE_NOW)  # no AssertionError
    assert "Approved. Pat" in reading.text
    assert "2026 08:14" not in reading.text


def test_an_unreadable_header_block_falls_back_to_the_stored_text(monkeypatch) -> None:
    def unreadable(stored: str, header_end: int):
        raise channel_times._Unreadable  # pyright: ignore[reportPrivateUsage]

    monkeypatch.setattr(channel_times, "_fields", unreadable)
    assert reading_text(SUBJECT_THEN_RECEIVED, SAMPLE_NOW).text == SUBJECT_THEN_RECEIVED
