"""How the report writes money, dates, buckets and places in files."""

from datetime import date, datetime

from app.contracts.api import ReadingView
from app.contracts.checks import Bucket
from app.contracts.evidence import EvidenceFile
from app.contracts.records import (
    CharLocation,
    Citation,
    ContentBlockLocation,
    ImageBox,
    PageLocation,
)

BUCKET_LABELS = {
    Bucket.EVIDENCE_COMPLETE: "Evidence complete",
    Bucket.POSSIBLE_CONFLICT: "Possible conflict",
    Bucket.MISSING_EVIDENCE: "Missing evidence",
    Bucket.NEEDS_HUMAN: "Needs a human",
}

SOURCE_LABELS = {"upload": "Upload", "gmail": "Gmail", "drive": "Google Drive"}

FUNDER_NAMES = {"NSF": "National Science Foundation (NSF)"}


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    dollars, rest = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{rest:02d}"


def day(d: date | datetime | None) -> str:
    """A date without a time, for example "Feb 20, 2026"."""
    if d is None:
        return ""
    return f"{d:%b} {d.day}, {d.year}"


def moment(t: datetime) -> str:
    """A time where one is needed, in UTC and labeled, for example "Apr 10, 2026, 17:00 UTC"."""
    return f"{day(t)}, {t:%H:%M} UTC"


def bucket(b: Bucket) -> str:
    return BUCKET_LABELS[b]


def line_number(text: str, char_index: int) -> int:
    return text.count("\n", 0, char_index) + 1


def reading_position(reading: ReadingView, stored_at: int) -> int:
    """Where a stored character position sits in the text the agent reads (ruling 50).

    Inside a kept span it moves with the span. Inside a gap (a header replaced or
    dropped) it lands where the gap starts in the reading text: the replaced Date
    line, or the next kept line when the header was only dropped.
    """
    gap_at = 0
    for s in reading.segments:
        if s.stored_start <= stored_at < s.stored_start + s.length:
            return s.reading_start + (stored_at - s.stored_start)
        if s.stored_start + s.length <= stored_at:
            gap_at = s.reading_start + s.length
    return gap_at


def place(
    citation: Citation,
    files: dict[str, EvidenceFile],
    file_texts: dict[str, str],
    value_text: str | None = None,
    reading: ReadingView | None = None,
) -> str:
    """Where a citation points: the file's name and the place inside it.

    Text and email give the line number when the file's text is at hand. For an
    email on a grant with a stored clock, `reading` is the text the agent read, and
    the line is counted there (ruling 50), so dropped headers don't count. A photo
    or a scan gives the page and the value as read (decision 0022's agreed answers).
    """
    f = files.get(citation.file_id)
    name = f.name if f else citation.file_id
    loc = citation.location
    if isinstance(loc, PageLocation):
        last = loc.end_page_number - 1
        pages = (
            f"page {loc.start_page_number}"
            if last == loc.start_page_number
            else f"pages {loc.start_page_number} to {last}"
        )
        return f"{name}, {pages}"
    if isinstance(loc, CharLocation):
        text = file_texts.get(citation.file_id)
        if text is not None and loc.start_char_index <= len(text):
            if reading is not None:
                at = reading_position(reading, loc.start_char_index)
                return f"{name}, line {line_number(reading.text, at)}"
            return f"{name}, line {line_number(text, loc.start_char_index)}"
        return name
    if isinstance(loc, ContentBlockLocation):
        return f"{name}, block {loc.start_block_index + 1}"
    assert isinstance(loc, ImageBox)
    read = f", value as read: {value_text}" if value_text else ""
    return f"{name}, page {loc.page}{read}"
