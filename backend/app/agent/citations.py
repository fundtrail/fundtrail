"""Turning the API's citations into the contract's citations.

Citations come back only on the model's text blocks, never inside a tool call. So the model writes
one line per value as text, `@label: value`, in a message of its own with no tool call (on
claude-opus-5-5, text written just before a tool call comes back as an empty thinking block). Code
parses those lines into the run's label table, and a write tool names labels instead of values.

For each label code picks the citation whose passage contains the value's text, maps the API's
document index to the file, and checks the passage against the file:

- Plain text and email (char_location): the text at the cited characters has to be the passage.
  The API cites by sentence chunks that can span many lines, so code narrows the citation to the
  line or lines inside the passage that hold the value's text. If the text appears more than once
  in the passage, the whole passage stays.
- PDF (page_location): the quote finder (app.quotes) finds the passage on its pages, exact first
  and then close, and gives the highlight boxes. The value has to appear exactly in the matched
  text, or the citation is not found.
- Photo or scan: no citation. The model gives a pixel box on the image we sent, and code scales
  it to fractions of the page (see `image_box`).
"""

import email.utils
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.agent.adapter import char_citation
from app.quotes import UnreadablePdfError, find_pdf_quote
from app.quotes.text_match import clean, value_in_span

LABEL_LINE = re.compile(r"^\s*[-*]?\s*@([A-Za-z0-9_.\-]+)\s*:\s?(.*?)\s*$")


@dataclass
class LabelLine:
    """One `@label: value` line the model wrote, with the API's citations on it."""

    label: str
    text: str  # the value exactly as written after the colon
    citations: list[Any] = field(default_factory=list[Any])  # the SDK's citation objects


def _get(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def parse_label_lines(content: Iterable[Any]) -> list[LabelLine]:
    """The `@label: value` lines in one assistant turn's text blocks, with their citations.

    The API splits text into several blocks around cited spans, so the blocks are joined and
    each line takes the citations of every block that overlaps it.
    """
    text = ""
    spans: list[tuple[int, int, list[Any]]] = []
    for block in content:
        if _get(block, "type") != "text":
            continue
        start = len(text)
        text += _get(block, "text") or ""
        spans.append((start, len(text), list(_get(block, "citations") or [])))
    lines: list[LabelLine] = []
    pos = 0
    for line in text.split("\n"):
        end = pos + len(line)
        m = LABEL_LINE.match(line)
        if m:
            value = m.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'`":
                value = value[1:-1]
            cites = [c for (s, e, cs) in spans if s < end and e > pos for c in cs]
            lines.append(LabelLine(label=m.group(1), text=value, citations=cites))
        pos = end + 1
    return lines


# Documents sent to the model, by the API's document_index.


@dataclass(frozen=True)
class SentDocument:
    """One document block sent in the run. document_index counts every document in the request."""

    file_id: str
    kind: str  # "text" or "pdf"
    text: str | None = None  # the exact text sent, for "text"
    pdf: bytes | None = None  # the bytes sent, for "pdf"


@dataclass(frozen=True)
class SentImage:
    """A photo or scanned page sent as an image, at a size we control."""

    file_id: str
    page: int
    width: int  # pixels on the image we sent
    height: int


class CitationProblem(Exception):
    """A citation that can't be used, as a plain sentence for the model."""


def standing_occurrences(text: str, start: int, end: int, value_text: str) -> list[int]:
    """Where the value stands on its own inside text[start:end], as a whole value.

    "000" doesn't stand on its own inside "$120,000" or "00000", and "450.00" doesn't inside
    "$12,450.00". The rule is the quote finder's own (`value_in_span`), checked on the whole text.
    """
    found: list[int] = []
    if not value_text:
        return found
    pos = text.find(value_text, start)
    while 0 <= pos and pos + len(value_text) <= end:
        if value_in_span(value_text, text, pos, pos + len(value_text)):
            found.append(pos)
        pos = text.find(value_text, pos + 1)
    return found


def value_lines(text: str, start: int, end: int, value_text: str) -> list[tuple[int, int]]:
    """One character range per line inside text[start:end] where the value stands on its own.

    Each range is the line clipped to the span, with surrounding spaces trimmed. "$120,000"
    gives each line that states $120,000, and "Cost Share: $0" between them isn't one.
    """
    ranges: list[tuple[int, int]] = []
    for pos in standing_occurrences(text, start, end, value_text):
        line_start = max(start, text.rfind("\n", 0, pos) + 1)
        nl = text.find("\n", pos + len(value_text))
        line_end = min(end, nl if nl >= 0 else len(text))
        while line_start < line_end and text[line_start].isspace():
            line_start += 1
        while line_end > line_start and text[line_end - 1].isspace():
            line_end -= 1
        if (line_start, line_end) not in ranges:
            ranges.append((line_start, line_end))
    return ranges


def narrow_to_lines(text: str, start: int, end: int, value_text: str) -> tuple[int, int]:
    """The one range a text citation can hold today: from the first line where the value stands
    on its own to the last, or the whole span when it stands on its own nowhere."""
    lines = value_lines(text, start, end, value_text)
    return (lines[0][0], lines[-1][1]) if lines else (start, end)


def _char_citation(doc: SentDocument, raw: Any, value_text: str) -> dict[str, Any]:
    assert doc.text is not None
    passage = _get(raw, "cited_text") or ""
    start, end = int(_get(raw, "start_char_index")), int(_get(raw, "end_char_index"))
    match = "exact"
    if doc.text[start:end] != passage:
        # Look for the passage once in the file; a passage found nowhere is not found.
        found = doc.text.find(passage) if passage else -1
        if found >= 0 and doc.text.find(passage, found + 1) < 0:
            start, end = found, found + len(passage)
        else:
            match = "not_found"
    lines = value_lines(doc.text, start, end, value_text) if match == "exact" else []
    return char_citation(doc.file_id, passage, start, end, match, lines)


def _page_citation(doc: SentDocument, raw: Any, value_text: str) -> dict[str, Any]:
    assert doc.pdf is not None
    passage = _get(raw, "cited_text") or ""
    first, last = int(_get(raw, "start_page_number")), int(_get(raw, "end_page_number"))
    try:
        found = find_pdf_quote(
            doc.pdf, passage, start_page_number=first, end_page_number=last, value_text=value_text
        )
    except (UnreadablePdfError, ValueError):
        found = None
    match = "not_found"
    highlight: list[dict[str, Any]] | None = None
    if found is not None and found.match != "not_found" and found.value_found is not False:
        match = found.match
        # Every place the passage was found that holds the value; each box carries its page.
        occurrences = [o for o in found.occurrences if o.value_found is not False]
        highlight = [
            {
                "page": r.page_number,
                "left": r.left,
                "top": r.top,
                "width": max(r.right - r.left, 1e-6),
                "height": max(r.bottom - r.top, 1e-6),
            }
            for o in occurrences
            for r in o.rects
        ] or None
    citation: dict[str, Any] = {
        "file_id": doc.file_id,
        "passage": passage,
        "location": {"type": "page_location", "start_page_number": first, "end_page_number": last},
        "match": match,
    }
    if highlight:
        citation["highlight"] = highlight
    return citation


def resolve_citation(
    line_text: str, raw_citations: Sequence[Any], documents: Sequence[SentDocument]
) -> dict[str, Any]:
    """The contract citation for one value: the API citation whose passage contains its text."""
    usable = [c for c in raw_citations if value_in(line_text, _get(c, "cited_text") or "")]
    if not usable:
        raise CitationProblem(f"none of the passages cited for '{line_text}' contains it")
    raw = usable[0]
    index = _get(raw, "document_index")
    if index is None or not 0 <= int(index) < len(documents):
        raise CitationProblem(
            f"the citation for '{line_text}' points at no document sent in this run"
        )
    doc = documents[int(index)]
    kind = _get(raw, "type")
    if kind == "char_location" and doc.kind == "text":
        return _char_citation(doc, raw, line_text)
    if kind == "page_location" and doc.kind == "pdf":
        return _page_citation(doc, raw, line_text)
    raise CitationProblem(
        f"the citation for '{line_text}' is a {kind}, which FundTrail doesn't read"
    )


def value_in(text: str, passage: str) -> bool:
    """Whether the value stands on its own in the passage, as a whole value (the quote finder's
    rule): "$1,24" isn't in "Total Due: $1,240.00", and "000" isn't in "$120,000"."""
    if not text:
        return False
    cleaned = clean(passage).text
    return value_in_span(text, cleaned, 0, len(cleaned))


def image_box(
    image: SentImage, left: float, top: float, right: float, bottom: float
) -> dict[str, Any]:
    """A pixel box on the image we sent, as fractions of the page.

    The image was resized without cropping, so fractions of the sent image are fractions of the
    original page.
    """
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise CitationProblem(
            f"the box has to lie inside the image, which is {image.width} by {image.height} pixels"
        )
    return {
        "type": "image_box",
        "page": image.page,
        "left": left / image.width,
        "top": top / image.height,
        "width": (right - left) / image.width,
        "height": (bottom - top) / image.height,
    }


# Second look on a photo or scan: reads only the boxed area and has to see the same value.
# Not built yet; with none, a boxed value is unconfirmed.
SecondLook = Callable[[str, dict[str, Any], str], bool]


# Re-deriving money, dates and numbers from the text as written (trust rule 3).

# A minus sign as documents write it: a hyphen, an en dash, or the minus sign itself.
_MINUS = "-\u2013\u2212"
_AMOUNT = re.compile(r"^[\d,]*\d(?:\.\d{1,2})?$")


def parse_money(text: str) -> int | None:
    """Cents from money as a document writes it, negative for a credit.

    A credit is written with a leading minus ("-$400", "–$450.00", "- $450.00", "$-450.00"), a
    trailing minus ("$450.00-") or accounting parentheses ("($400.00)"). A missed sign would turn
    a credit into a charge, so each of these counts.
    """
    t = text.strip()
    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative, t = True, t[1:-1].strip()
    if t[:1] and t[0] in _MINUS:
        negative, t = True, t[1:].strip()
    if t[-1:] and t[-1] in _MINUS:
        negative, t = True, t[:-1].strip()
    if t[:3].upper() == "USD":
        t = t[3:].strip()
    t = t.removeprefix("$").strip()
    if t[:1] and t[0] in _MINUS:
        negative, t = True, t[1:].strip()
    if not _AMOUNT.match(t):
        return None
    try:
        cents = int((Decimal(t.replace(",", "")) * 100).to_integral_value())
    except InvalidOperation:
        return None
    return -cents if negative else cents


_DATE_FORMATS = (
    "%B %d, %Y",
    "%b %d, %Y",
    "%b. %d, %Y",
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d %B %Y",
    "%B %d %Y",
)


def parse_date(text: str) -> date | None:
    """A calendar date from a date as a document writes it."""
    t = " ".join(text.strip().split())
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    try:
        parsed = email.utils.parsedate_to_datetime(t)
    except (TypeError, ValueError, IndexError):
        return None
    return parsed.date() if parsed else None


def parse_decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text.strip().replace(",", ""))
    except InvalidOperation:
        return None


_QUANTITY = re.compile(r"^([\d,]*\d(?:\.\d+)?)(?:\s+[A-Za-z][A-Za-z .]*)?$")
_PERCENT = re.compile(r"^([\d,]*\d(?:\.\d+)?)\s*%$")
_PER_UNIT = re.compile(r"^(\$\s*[\d,]*\d(?:\.\d{1,2})?)(?:\s*(?:/|per|a|an|each)\b.*)?$", re.I)


def parse_quantity(text: str) -> Decimal | None:
    """A quantity as a document writes it: "50", "5 days", "1,200 samples"."""
    m = _QUANTITY.match(text.strip())
    return parse_decimal(m.group(1)) if m else None


def parse_rate(text: str) -> Decimal | None:
    """A rate in the contract's units: a percent as a fraction ("36.6%" is 0.366), a dollar rate
    in cents per unit ("$100 a day" is 10000), or a plain number as written."""
    t = text.strip()
    if m := _PERCENT.match(t):
        number = parse_decimal(m.group(1))
        return None if number is None else number / 100
    if m := _PER_UNIT.match(t):
        cents = parse_money(m.group(1))
        return None if cents is None else Decimal(cents)
    return parse_decimal(t)
