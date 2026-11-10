"""A sample grant's live email is read with its Date header as the grant's now (issue 165, point 4).

The agent reads `reading_text`: the top-level headers cut down to From, To, Cc, Subject and the
MIME headers, and Date as the grant's now when the email arrived. A citation into it
keeps that text as its passage, so a value is checked against what the agent saw, and its
location and highlight map back to the stored .eml with `stored_range` (ruling 50). The stored
file is never changed. A grant on the real date reads the email as stored.
"""

from datetime import datetime

from anthropic.types import CitationCharLocation

from app.agent.citations import LabelLine, resolve_citation
from app.agent.context import RunContext
from app.agent.files import open_file, reading_now
from app.agent.inputs import RunInputs
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool
from app.contracts.fixtures import DOCUMENTS_DIR, load_sample_grant
from app.contracts.records import Approval, CharLocation
from app.contracts.runs import Trigger, TriggerKind

from .fakes import sample_inputs

SAMPLE = load_sample_grant()
EMAIL = next(f for f in SAMPLE.files if f.id == "file-sequencing-statement")
STORED = (DOCUMENTS_DIR / EMAIL.name).read_text(encoding="utf-8")
GRANT_NOW = datetime.fromisoformat("2026-03-01T12:00:00+00:00")
SAMPLE_EMAIL = EMAIL.model_copy(update={"arrived_at": GRANT_NOW})


def _inputs(sample: bool) -> RunInputs:
    from dataclasses import replace

    base = sample_inputs(now=GRANT_NOW, trigger=Trigger(kind=TriggerKind.CLOCK), records=[])
    return replace(base, channel_times_from_grant_now=sample)


def _cite(sent: str, chunk: str) -> CitationCharLocation:
    start = sent.index(chunk)
    return CitationCharLocation(
        type="char_location",
        cited_text=chunk,
        document_index=0,
        start_char_index=start,
        end_char_index=start + len(chunk),
    )


def _sent(opened) -> str:  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
    block = next(b for b in opened.blocks if b["type"] == "document")
    return block["source"]["data"]


def test_a_sample_grant_reads_the_date_header_as_its_now():
    opened = open_file(SAMPLE_EMAIL, STORED.encode(), reading_now(_inputs(True), SAMPLE_EMAIL))
    sent = _sent(opened)
    assert "Date: Sun, 01 Mar 2026 12:00:00 +0000" in sent
    assert "Sat, 21 Feb 2026 09:30:00 -0800" not in sent
    assert opened.document is not None and opened.document.text == STORED  # the stored file


def test_a_date_line_quote_keeps_what_the_agent_read_and_points_at_the_stored_header():
    opened = open_file(SAMPLE_EMAIL, STORED.encode(), reading_now(_inputs(True), SAMPLE_EMAIL))
    assert opened.document is not None
    sent = _sent(opened)
    date_line = "Date: Sun, 01 Mar 2026 12:00:00 +0000"
    c = resolve_citation("Sun, 01 Mar 2026", [_cite(sent, date_line)], [opened.document])
    assert c["passage"] == date_line and c["match"] == "exact"
    # The location is the stored Date header, up to its line ending as the quote was.
    loc = c["location"]
    assert STORED[loc["start_char_index"] : loc["end_char_index"]] == (
        "Date: Sat, 21 Feb 2026 09:30:00 -0800"
    )
    assert [(r["start_char_index"], r["end_char_index"]) for r in c["highlight"]] == [
        (loc["start_char_index"], loc["end_char_index"])
    ]


def test_a_quote_after_the_date_line_lands_on_the_right_stored_bytes():
    # A Date header longer than the one put in its place, so every later position shifts.
    stored = STORED.replace(
        "Date: Sat, 21 Feb 2026 09:30:00 -0800", "Date: Sat, 21 Feb 2026 09:30:00 -0800 (PST)"
    )
    opened = open_file(SAMPLE_EMAIL, stored.encode(), reading_now(_inputs(True), SAMPLE_EMAIL))
    assert opened.document is not None
    sent = _sent(opened)
    assert "Message-ID" not in sent  # dropped from the reading text, still in the stored file
    assert len(sent) < len(stored)
    date_line = "Date: Sun, 01 Mar 2026 12:00:00 +0000"
    c = resolve_citation("Sun, 01 Mar 2026", [_cite(sent, date_line)], [opened.document])
    loc = c["location"]
    assert stored[loc["start_char_index"] : loc["end_char_index"]] == (
        "Date: Sat, 21 Feb 2026 09:30:00 -0800 (PST)"
    )
    for chunk, value in [
        ("Total: $2,180.00", "$2,180.00"),
        # A kept header after the replaced Date and the dropped Message-ID line.
        ("Content-Type: text/plain; charset=utf-8", "text/plain"),
    ]:
        c = resolve_citation(value, [_cite(sent, chunk)], [opened.document])
        loc = c["location"]
        assert stored[loc["start_char_index"] : loc["end_char_index"]] == chunk
        assert c["passage"] == chunk and c["match"] == "exact"
        ranges = c.get("highlight") or []
        assert ranges and all(
            value in stored[r["start_char_index"] : r["end_char_index"]] for r in ranges
        )


def test_an_ordinary_grant_reads_the_email_as_stored():
    assert reading_now(_inputs(False), SAMPLE_EMAIL) is None
    opened = open_file(EMAIL, STORED.encode(), reading_now(_inputs(False), EMAIL))
    assert opened.document is not None and opened.document.reading is None
    sent = _sent(opened)
    assert sent == STORED
    c = resolve_citation("$2,180.00", [_cite(sent, "Total: $2,180.00")], [opened.document])
    assert (
        STORED[c["location"]["start_char_index"] : c["location"]["end_char_index"]]
        == "Total: $2,180.00"
    )
    date_line = "Date: Sat, 21 Feb 2026 09:30:00 -0800"
    c = resolve_citation("21 Feb 2026", [_cite(sent, date_line)], [opened.document])
    loc = c["location"]
    assert c["passage"] == date_line == STORED[loc["start_char_index"] : loc["end_char_index"]]


def test_only_an_email_is_read_with_the_grants_now():
    invoice = next(f for f in SAMPLE.files if f.id == "file-invoice-1001")
    stored = (DOCUMENTS_DIR / invoice.name).read_bytes()
    opened = open_file(invoice, stored, GRANT_NOW)
    assert opened.document is not None and opened.document.reading is None
    assert _sent(opened) == stored.decode()


def test_a_quote_that_ends_at_a_kept_line_doesnt_take_in_the_dropped_header_after_it():
    """stored_range maps the end from the last character covered: a range ending right after
    the Date line ends there in the stored file, not after the dropped Message-ID line."""
    opened = open_file(SAMPLE_EMAIL, STORED.encode(), reading_now(_inputs(True), SAMPLE_EMAIL))
    assert opened.document is not None and opened.document.reading is not None
    sent = _sent(opened)
    start = sent.index("Subject:")
    end = sent.index("Date:") + len("Date: Sun, 01 Mar 2026 12:00:00 +0000\n")
    stored_start, stored_end = opened.document.reading.stored_range(start, end)
    assert "Message-ID" not in STORED[stored_start:stored_end]
    assert STORED[stored_start:stored_end].endswith("Date: Sat, 21 Feb 2026 09:30:00 -0800\n")


def test_a_quote_across_a_dropped_header_stores_none_of_its_text():
    """A dropped header between two kept lines (say X-Received, with the real delivery time)
    is in neither the passage nor the highlight."""
    stored = STORED.replace(
        "Subject:", "X-Received: by 10.0.0.1; Tue, 14 Oct 2025 09:01:03 -0700\nSubject:"
    )
    opened = open_file(SAMPLE_EMAIL, stored.encode(), reading_now(_inputs(True), SAMPLE_EMAIL))
    assert opened.document is not None
    sent = _sent(opened)
    span = sent[sent.index("From:") : sent.index("\n", sent.index("Subject:"))]
    assert "X-Received" not in span
    c = resolve_citation("Sequencing core usage statement", [_cite(sent, span)], [opened.document])
    assert c["passage"] == span and c["match"] == "exact"
    assert "X-Received" not in c["passage"] and "2025" not in c["passage"]
    assert c["highlight"]
    for r in c["highlight"]:
        lit = stored[r["start_char_index"] : r["end_char_index"]]
        assert lit.startswith("Subject:") and "X-Received" not in lit


def _approval_context() -> tuple[RunContext, str]:
    """A run on the sample grant at the email's arrival, with the email open as the agent reads
    it."""
    inputs = sample_inputs(
        now=EMAIL.arrived_at,
        trigger=Trigger(kind=TriggerKind.FILE, id=EMAIL.id),
        records=[],
        channel_times_from_grant_now=True,
    )
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook())
    result, error = run_tool(ctx, "open_file", {"file_id": EMAIL.id})
    assert not error, result
    opened = open_file(EMAIL, STORED.encode(), reading_now(inputs, EMAIL))
    return ctx, _sent(opened)


def _label(ctx: RunContext, sent: str, name: str, value: str, chunk: str) -> None:
    ctx.labels[name] = LabelLine(name, value, [_cite(sent, chunk)])


def test_an_approval_date_read_from_the_date_line_saves():
    ctx, sent = _approval_context()
    date_line = next(line for line in sent.splitlines() if line.startswith("Date:"))
    assert date_line == "Date: Sat, 21 Feb 2026 17:30:00 +0000"  # the grant's now, in UTC
    _label(ctx, sent, "who", "robin.example@university.example", sent.splitlines()[0])
    service = "Service: Sediment DNA sequencing, run 7, 48 samples"
    _label(ctx, sent, "what", "Sediment DNA sequencing, run 7", service)
    _label(ctx, sent, "when", "Sat, 21 Feb 2026 17:30:00 +0000", date_line)
    values = [
        {"field": "approver_email", "label": "who"},
        {"field": "covers", "label": "what"},
        {"field": "approved_on", "label": "when"},
    ]
    result, error = run_tool(ctx, "write_fact", {"kind": "approval", "values": values})
    assert not error, result
    data = ctx.staged[-1].record.data
    assert isinstance(data, Approval) and data.approved_on is not None
    citation = data.approved_on.citation
    assert citation is not None and citation.passage == date_line
    loc = citation.location
    assert isinstance(loc, CharLocation)
    assert STORED[loc.start_char_index : loc.end_char_index] == (
        "Date: Sat, 21 Feb 2026 09:30:00 -0800"
    )
