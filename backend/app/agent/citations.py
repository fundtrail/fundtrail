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

try:  # the quote finder (#19) isn't merged yet; until it is, a PDF citation is not found
    from app.quotes import (  # pyright: ignore[reportAttributeAccessIssue]
        UnreadablePdfError,  # pyright: ignore[reportAttributeAccessIssue]
        find_pdf_quote,  # pyright: ignore[reportAttributeAccessIssue]
    )
except ImportError:  # pragma: no cover - depends on what's merged
    find_pdf_quote = None

    class UnreadablePdfError(Exception):  # noqa: N818
        pass


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


def narrow_to_lines(text: str, start: int, end: int, value_text: str) -> tuple[int, int]:
    """Narrow a cited span to the line or lines inside it that hold the value's text.

    If the value's text appears more than once in the span, or not at all, the span stays whole.
    Surrounding spaces and line breaks are trimmed.
    """
    passage = text[start:end]
    first = passage.find(value_text) if value_text else -1
    if first < 0 or passage.find(value_text, first + 1) >= 0:
        return start, end
    occ_start = start + first
    occ_end = occ_start + len(value_text)
    line_start = max(start, text.rfind("\n", 0, occ_start) + 1)
    nl = text.find("\n", occ_end)
    line_end = min(end, nl if nl >= 0 else len(text))
    while line_start < line_end and text[line_start].isspace():
        line_start += 1
    while line_end > line_start and text[line_end - 1].isspace():
        line_end -= 1
    return line_start, line_end


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
    if match == "exact":
        start, end = narrow_to_lines(doc.text, start, end, value_text)
        passage = doc.text[start:end]
    return {
        "file_id": doc.file_id,
        "passage": passage,
        "location": {"type": "char_location", "start_char_index": start, "end_char_index": end},
        "match": match,
    }


def _page_citation(doc: SentDocument, raw: Any, value_text: str) -> dict[str, Any]:
    assert doc.pdf is not None
    passage = _get(raw, "cited_text") or ""
    first, last = int(_get(raw, "start_page_number")), int(_get(raw, "end_page_number"))
    found: Any = None
    if find_pdf_quote is not None:
        try:
            found = find_pdf_quote(
                doc.pdf,
                passage,
                start_page_number=first,
                end_page_number=last,
                value_text=value_text,
            )
        except (UnreadablePdfError, ValueError):
            found = None
    match = "not_found"
    highlight: list[dict[str, Any]] | None = None
    if found is not None and found.match != "not_found" and found.value_found is not False:
        match = found.match
        if found.page_number is not None:
            highlight = [
                {
                    "page": found.page_number,
                    "left": r.left,
                    "top": r.top,
                    "width": max(r.right - r.left, 1e-6),
                    "height": max(r.bottom - r.top, 1e-6),
                }
                for r in found.rects
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
    return bool(text) and text in passage


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

_MONEY = re.compile(r"^\(?\s*(-)?\s*(?:USD\s*)?\$?\s*(-)?\s*([\d,]*\d(?:\.\d{1,2})?)\s*\)?$", re.I)


def parse_money(text: str) -> int | None:
    """Cents from money as a document writes it: "$1,240.00", "-$400", "($400.00)"."""
    t = text.strip()
    m = _MONEY.match(t)
    if not m:
        return None
    digits = m.group(3).replace(",", "")
    try:
        cents = int((Decimal(digits) * 100).to_integral_value())
    except InvalidOperation:
        return None
    negative = bool(m.group(1) or m.group(2)) or (t.startswith("(") and t.endswith(")"))
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
        return Decimal(text.strip())
    except InvalidOperation:
        return None
