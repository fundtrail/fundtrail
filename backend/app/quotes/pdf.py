"""Find a cited passage in a PDF with pypdfium2, and say where its highlight goes.

The Anthropic API (application programming interface) cites a PDF by the quoted passage and a
page range, nothing finer (docs/architecture.md, "Quotes and highlights"). This module reads the
text of the pages in that range, joined in order, finds the passage by exact match first and then
a close one (see `text_match`), and returns the highlight boxes for every place it was found. A
passage that runs across a page break gets boxes on both pages.

pdfium, the library under pypdfium2, isn't safe to call from several threads at once. Every
pypdfium2 call in the backend has to run while holding `PDFIUM_LOCK`, whichever module makes it.
In this module that holds by construction: the only place that touches pypdfium2 is
`_read_and_match`, which opens the file, does all its work and closes every pdfium object before
it lets the lock go, so no pdfium object outlives the lock or is closed later by the garbage
collector on another thread.
"""

import ctypes
import threading
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from app.quotes.text_match import (
    LINE_DASH,
    LINE_HYPHEN,
    CleanText,
    clean,
    close_span_ok,
    find_exact,
    find_letters_and_digits,
    find_within_edits,
    span_stands_alone,
    value_in_span,
)
from app.quotes.types import HighlightRect, MatchMethod, PdfQuoteMatch, QuoteOccurrence

PDFIUM_LOCK = threading.Lock()
"""Held around every pypdfium2 call in the process, by every module that uses pypdfium2.

Not reentrant: code that holds it must not call `find_pdf_quote`, or it waits forever.
"""

_DEVICE_SIZE = 1_000_000
"""Size of the virtual device pdfium maps page points onto, so a box comes back as fractions."""

_PAGE_BREAK = "\n"
"""Put between pages when their text is joined, so the clean-up treats it as a line break."""


class UnreadablePdfError(Exception):
    """The file couldn't be opened as a PDF (damaged, password protected, or not a PDF)."""


@dataclass(frozen=True)
class _Pages:
    """The text of the pages in the range, joined, and where each page starts in it."""

    numbers: tuple[int, ...]
    """Page numbers, counted from 1."""
    starts: tuple[int, ...]
    """Where each page's first character sits in the joined characters."""
    lengths: tuple[int, ...]
    """How many characters pdfium reports on each page."""
    text: CleanText


def find_pdf_quote(
    pdf: bytes | Path,
    passage: str,
    *,
    start_page_number: int,
    end_page_number: int,
    value_text: str | None = None,
) -> PdfQuoteMatch:
    """Find a cited passage in a PDF's page range and return where its highlights go.

    The page range uses the Anthropic API's `page_location` names and counting: pages count from
    1, and `end_page_number` is exclusive. Pages past the end of the file are ignored. The pages
    in the range are searched as one text, so a passage across a page break is found; a citation
    that names one page is searched on that page alone.

    Every place the passage appears is returned. An exact match wins; otherwise the close steps
    run, and a close match counts only when it passes `close_span_ok` (its numbers and the value
    appear exactly). A match that starts or ends in the middle of a word or number on the page
    isn't a match, and one that can't be placed on the page (no boxes) counts as not found.
    `value_text` is the cited value exactly as the document writes it; it's checked against the
    whole page, so it can't be the tail or head of a longer number there.

    Raises FileNotFoundError for a path that doesn't exist, UnreadablePdfError when the file
    can't be opened as a PDF, and ValueError for a bad range.
    """
    if start_page_number < 1 or end_page_number <= start_page_number:
        raise ValueError(f"bad page range: {start_page_number} to {end_page_number}")
    with PDFIUM_LOCK:
        return _read_and_match(pdf, passage, start_page_number - 1, end_page_number - 1, value_text)


def _read_and_match(
    pdf: bytes | Path, passage: str, first: int, stop: int, value_text: str | None
) -> PdfQuoteMatch:
    """Do the whole job while the caller holds PDFIUM_LOCK. Closes every pdfium object it opens."""
    try:
        doc = pdfium.PdfDocument(pdf)
    except pdfium.PdfiumError as error:
        raise UnreadablePdfError(str(error)) from error
    method: MatchMethod | None = None
    occurrences: list[QuoteOccurrence] = []
    try:
        pages = _read_pages(doc, range(first, min(stop, len(doc))))
        found = _find(passage, pages.text, value_text)
        if found is not None:
            method, spans = found
            rects = _rects_for_spans(doc, pages, spans)
            for (start, end), boxes in zip(spans, rects, strict=True):
                if not boxes:
                    continue
                matched = pages.text.text[start:end]
                occurrences.append(
                    QuoteOccurrence(
                        rects=boxes,
                        matched_text=matched.replace(LINE_HYPHEN, "-").replace(LINE_DASH, "-"),
                        value_found=(
                            value_in_span(value_text, pages.text.text, start, end)
                            if value_text
                            else None
                        ),
                    )
                )
    finally:
        doc.close()

    if method is None or not occurrences:
        return PdfQuoteMatch("not_found", None, (), False if value_text else None)
    return PdfQuoteMatch(
        match="exact" if method == "exact" else "close",
        method=method,
        occurrences=tuple(occurrences),
        value_found=any(o.value_found for o in occurrences) if value_text else None,
    )


def _read_pages(doc: pdfium.PdfDocument, indexes: range) -> _Pages:
    chars: list[str] = []
    starts: list[int] = []
    lengths: list[int] = []
    for index in indexes:
        page = doc[index]
        try:
            textpage = page.get_textpage()
            try:
                page_chars = _page_chars(textpage)
            finally:
                textpage.close()
        finally:
            page.close()
        starts.append(len(chars))
        lengths.append(len(page_chars))
        chars.extend(page_chars)
        chars.append(_PAGE_BREAK)
    numbers = tuple(index + 1 for index in indexes)
    return _Pages(numbers, tuple(starts), tuple(lengths), clean(chars))


def _find(
    passage: str, text: CleanText, value_text: str | None
) -> tuple[MatchMethod, list[tuple[int, int]]] | None:
    """Exact first, then letters and digits, then within a few edits.

    Every span has to stand on its own on the page (it can't start or end in the middle of a word
    or number), and every close span has to pass `close_span_ok`. Each step returns all its
    spans that pass; a step with none falls through to the next.
    """
    page = text.text
    spans = [s for s in find_exact(passage, text) if span_stands_alone(page, *s)]
    if spans:
        return "exact", spans
    spans = [
        s
        for s in find_letters_and_digits(passage, text)
        if span_stands_alone(page, *s) and close_span_ok(passage, value_text, page, *s)
    ]
    if spans:
        return "letters_and_digits", spans
    spans = [
        s
        for s, _edits in find_within_edits(passage, text)
        if span_stands_alone(page, *s) and close_span_ok(passage, value_text, page, *s)
    ]
    if spans:
        return "edit_distance", spans
    return None


def _rects_for_spans(
    doc: pdfium.PdfDocument, pages: _Pages, spans: Sequence[tuple[int, int]]
) -> list[tuple[HighlightRect, ...]]:
    """The boxes for each span, on every page the span touches, opening each page once."""
    # For each span, the character range it covers on each page: {page position: (first, last)}.
    wanted: list[dict[int, tuple[int, int]]] = []
    for start, end in spans:
        first_char = pages.text.origin[start]
        last_char = pages.text.origin[end - 1]
        per_page: dict[int, tuple[int, int]] = {}
        for pos in range(_page_at(pages, first_char), _page_at(pages, last_char) + 1):
            page_start = pages.starts[pos]
            local_first = max(first_char, page_start) - page_start
            local_last = min(last_char, page_start + pages.lengths[pos] - 1) - page_start
            if local_first <= local_last:
                per_page[pos] = (local_first, local_last)
        wanted.append(per_page)

    boxes: list[list[HighlightRect]] = [[] for _ in spans]
    for pos in sorted({pos for per_page in wanted for pos in per_page}):
        page = doc[pages.numbers[pos] - 1]
        try:
            textpage = page.get_textpage()
            try:
                for i, per_page in enumerate(wanted):
                    if pos in per_page:
                        local_first, local_last = per_page[pos]
                        boxes[i].extend(
                            _rects(page, textpage, pages.numbers[pos], local_first, local_last)
                        )
            finally:
                textpage.close()
        finally:
            page.close()
    return [tuple(b) for b in boxes]


def _page_at(pages: _Pages, char_index: int) -> int:
    """The position in the range of the page a joined-character index falls on."""
    return max(bisect_right(pages.starts, char_index) - 1, 0)


def _page_chars(textpage: pdfium.PdfTextPage) -> list[str]:
    """The page's characters, one per pdfium character index, including generated line breaks."""
    raw = textpage.raw
    return [chr(pdfium_c.FPDFText_GetUnicode(raw, i)) for i in range(textpage.count_chars())]


def _rects(
    page: pdfium.PdfPage,
    textpage: pdfium.PdfTextPage,
    page_number: int,
    first_char: int,
    last_char: int,
) -> tuple[HighlightRect, ...]:
    """One box per line for a character span, as fractions of the page a viewer shows.

    pdfium gives a box per run of text, and some producers (Chrome, for one) write each word as
    its own run. Boxes in a row that sit on the same line are joined first, in PDF page space,
    where the text runs left to right even on a rotated page.
    """
    count = pdfium_c.FPDFText_CountRects(textpage.raw, first_char, last_char - first_char + 1)
    lines: list[tuple[float, float, float, float]] = []
    left, top, right, bottom = (ctypes.c_double() for _ in range(4))
    for i in range(max(count, 0)):
        if not pdfium_c.FPDFText_GetRect(
            textpage.raw,
            i,
            ctypes.byref(left),
            ctypes.byref(top),
            ctypes.byref(right),
            ctypes.byref(bottom),
        ):
            continue
        box = (left.value, top.value, right.value, bottom.value)
        if lines and _same_line(lines[-1], box):
            last = lines[-1]
            box = (
                min(last[0], box[0]),
                max(last[1], box[1]),
                max(last[2], box[2]),
                min(last[3], box[3]),
            )
            lines[-1] = box
        else:
            lines.append(box)

    rects: list[HighlightRect] = []
    for x_left, y_top, x_right, y_bottom in lines:
        x1, y1 = _to_fraction(page, x_left, y_top)
        x2, y2 = _to_fraction(page, x_right, y_bottom)
        rect = HighlightRect(page_number, min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        if rect.right > rect.left and rect.bottom > rect.top:
            rects.append(rect)
    return tuple(rects)


def _same_line(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    """Whether two boxes in PDF page space (top above bottom) overlap by half a line or more."""
    overlap = min(a[1], b[1]) - max(a[3], b[3])
    return overlap >= 0.5 * min(a[1] - a[3], b[1] - b[3])


def _to_fraction(page: pdfium.PdfPage, x: float, y: float) -> tuple[float, float]:
    """Map a point in PDF page space to fractions of the shown page, from its top left corner.

    pdfium's own mapping applies the crop box and the page's rotation.
    """
    dx, dy = ctypes.c_int(), ctypes.c_int()
    pdfium_c.FPDF_PageToDevice(
        page.raw, 0, 0, _DEVICE_SIZE, _DEVICE_SIZE, 0, x, y, ctypes.byref(dx), ctypes.byref(dy)
    )
    return _clamp(dx.value / _DEVICE_SIZE), _clamp(dy.value / _DEVICE_SIZE)


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)
