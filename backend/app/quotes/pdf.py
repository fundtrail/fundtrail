"""Find a cited passage on a PDF page with pypdfium2, and say where its highlight goes.

The API's citation for a PDF gives the quoted passage and a page range, nothing finer
(docs/architecture.md, "Quotes and highlights"). This module reads those pages' text, finds the
passage by exact match first and then a close one (see `text_match`), and returns the highlight
boxes on the page.

pdfium, the library under pypdfium2, isn't safe to call from several threads at once. Every
pypdfium2 call in the backend has to run while holding `PDFIUM_LOCK`. In this module that holds
by construction: the only place that touches pypdfium2 is `_read_and_match`, which opens the file,
does all its work and closes every pdfium object before it lets the lock go, so no pdfium object
outlives the lock or is closed later by the garbage collector on another thread.
"""

import ctypes
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from app.quotes.text_match import (
    LINE_HYPHEN,
    CleanText,
    clean,
    contains_exactly,
    find_exact,
    find_letters_and_digits,
    find_within_edits,
)
from app.quotes.types import HighlightRect, MatchMethod, PdfQuoteMatch

PDFIUM_LOCK = threading.Lock()
"""Held around every pypdfium2 call in the process. Other modules that use pypdfium2 take it too."""

_DEVICE_SIZE = 1_000_000
"""Size of the virtual device pdfium maps page points onto, so a box comes back as fractions."""


class UnreadablePdfError(Exception):
    """The file couldn't be opened as a PDF (damaged, password protected, or not a PDF)."""


@dataclass(frozen=True)
class _Found:
    page_index: int
    span: tuple[int, int]
    method: MatchMethod
    edits: int = 0


def find_pdf_quote(
    pdf: bytes | Path,
    passage: str,
    *,
    start_page_number: int,
    end_page_number: int,
    value_text: str | None = None,
) -> PdfQuoteMatch:
    """Find a cited passage in a PDF's page range and return where the highlight goes.

    The page range uses the Anthropic API's `page_location` names and counting: pages count from
    1, and `end_page_number` is exclusive. Pages past the end of the file are ignored.

    Tries an exact match on every page in the range first, then the close steps. A passage that
    runs across a page break isn't joined up, so it's found only if a close match on one page
    covers it. `value_text` is the cited value exactly as the document writes it; the result says
    whether it appears exactly in the matched text.

    Raises UnreadablePdfError when the file can't be opened, and ValueError for a bad range.
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
    try:
        pages: list[CleanText] = []
        for index in range(first, min(stop, len(doc))):
            page = doc[index]
            try:
                textpage = page.get_textpage()
                try:
                    pages.append(clean(_page_chars(textpage)))
                finally:
                    textpage.close()
            finally:
                page.close()

        found = _find(passage, pages)
        if found is None:
            return PdfQuoteMatch("not_found", None, None, (), None, False if value_text else None)

        page_text = pages[found.page_index]
        start, end = found.span
        matched = page_text.text[start:end]
        page = doc[first + found.page_index]
        try:
            textpage = page.get_textpage()
            try:
                first_char = page_text.origin[start]
                last_char = page_text.origin[end - 1]
                rects = _rects(page, textpage, first_char, last_char)
            finally:
                textpage.close()
        finally:
            page.close()
    finally:
        doc.close()

    return PdfQuoteMatch(
        match="exact" if found.method == "exact" else "close",
        method=found.method,
        page_number=first + found.page_index + 1,
        rects=rects,
        matched_text=matched.replace(LINE_HYPHEN, "-"),
        value_found=contains_exactly(value_text, matched) if value_text else None,
    )


def _find(passage: str, pages: list[CleanText]) -> _Found | None:
    """Exact on any page wins, then letters and digits, then the fewest edits on any page."""
    steps: list[tuple[MatchMethod, Callable[[str, CleanText], tuple[int, int] | None]]] = [
        ("exact", find_exact),
        ("letters_and_digits", find_letters_and_digits),
    ]
    for method, step in steps:
        for index, page in enumerate(pages):
            span = step(passage, page)
            if span is not None:
                return _Found(index, span, method)
    best: _Found | None = None
    for index, page in enumerate(pages):
        result = find_within_edits(passage, page)
        if result is not None and (best is None or result[1] < best.edits):
            best = _Found(index, result[0], "edit_distance", result[1])
    return best


def _page_chars(textpage: pdfium.PdfTextPage) -> list[str]:
    """The page's characters, one per pdfium character index, including generated line breaks."""
    raw = textpage.raw
    return [chr(pdfium_c.FPDFText_GetUnicode(raw, i)) for i in range(textpage.count_chars())]


def _rects(
    page: pdfium.PdfPage, textpage: pdfium.PdfTextPage, first_char: int, last_char: int
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
        rect = HighlightRect(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
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
