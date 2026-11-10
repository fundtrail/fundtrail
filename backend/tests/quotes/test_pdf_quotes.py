"""find_pdf_quote on real PDFs from three producers (see make_fixtures.py and cases.py)."""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from app.quotes import PDFIUM_LOCK, UnreadablePdfError, find_pdf_quote
from app.quotes.types import HighlightRect
from tests.quotes.cases import CASES, HYPHENATED, INVOICE, Case

FIXTURES = Path(__file__).parent / "fixtures"


def _run(case: Case):
    return find_pdf_quote(
        FIXTURES / case.fixture,
        case.passage,
        start_page_number=case.start_page,
        end_page_number=case.end_page,
        value_text=case.value,
    )


@pytest.mark.parametrize("case", CASES, ids=[f"{c.fixture}:{c.passage[:40]}" for c in CASES])
def test_case(case: Case) -> None:
    result = _run(case)
    assert result.match == case.expect, result
    assert result.page_number == case.page
    assert result.value_found == case.value_found
    if case.expect == "not_found":
        assert result.rects == ()
        assert result.matched_text is None
    else:
        assert result.rects
        assert result.matched_text
        for rect in result.rects:
            assert 0 <= rect.left < rect.right <= 1
            assert 0 <= rect.top < rect.bottom <= 1


def _ink(path: Path, page_number: int, rect: HighlightRect) -> float:
    """Share of dark pixels inside a box on the rendered page (rotation and crop applied)."""
    with PDFIUM_LOCK:
        doc = pdfium.PdfDocument(path)
        try:
            page = doc[page_number - 1]
            bitmap = page.render(scale=2, grayscale=True)
            width, height, stride = bitmap.width, bitmap.height, bitmap.stride
            pixels = bytes(bitmap.buffer)
            bitmap.close()
            page.close()
        finally:
            doc.close()
    x0, x1 = int(rect.left * width), int(rect.right * width)
    y0, y1 = int(rect.top * height), int(rect.bottom * height)
    dark = total = 0
    for y in range(y0, y1):
        row = pixels[y * stride + x0 : y * stride + x1]
        dark += sum(1 for p in row if p < 128)
        total += len(row)
    return dark / total if total else 0.0


@pytest.mark.parametrize(
    ("fixture", "passage", "start"),
    [
        (INVOICE, "Total due: $12,450.00", 1),
        (HYPHENATED, "an internal recharge rate approved by the university", 1),
        (HYPHENATED, "the approved carryover amount is $4,200.00.", 2),
    ],
)
def test_highlight_covers_ink(fixture: str, passage: str, start: int) -> None:
    """Each highlight box lands on printed text in the rendered page, including a rotated one."""
    result = find_pdf_quote(
        FIXTURES / fixture, passage, start_page_number=start, end_page_number=start + 1
    )
    assert result.page_number == start
    for rect in result.rects:
        assert _ink(FIXTURES / fixture, start, rect) > 0.03, rect


def test_hyphenated_passage_gets_a_box_per_line() -> None:
    result = find_pdf_quote(
        FIXTURES / HYPHENATED,
        "an internal recharge rate approved by the university",
        start_page_number=1,
        end_page_number=2,
    )
    assert len(result.rects) == 2
    first, second = result.rects
    assert first.bottom <= second.top + 0.001


def test_rotated_page_box_is_in_the_shown_frame() -> None:
    """Page 2 is turned 90 degrees, so a line of text runs down the shown page, not across."""
    result = find_pdf_quote(
        FIXTURES / HYPHENATED,
        "the approved carryover amount is $4,200.00.",
        start_page_number=2,
        end_page_number=3,
    )
    (rect,) = result.rects
    assert rect.bottom - rect.top > rect.right - rect.left


def test_matched_text_shows_line_hyphens() -> None:
    result = find_pdf_quote(
        FIXTURES / HYPHENATED,
        "Travel funds support two trips",
        start_page_number=1,
        end_page_number=2,
    )
    assert result.matched_text == "Travel funds sup-port two trips"


def test_bytes_and_path_agree() -> None:
    path = FIXTURES / INVOICE
    by_path = find_pdf_quote(path, "Total due: $12,450.00", start_page_number=1, end_page_number=2)
    by_bytes = find_pdf_quote(
        path.read_bytes(), "Total due: $12,450.00", start_page_number=1, end_page_number=2
    )
    assert by_path == by_bytes


def test_unreadable_file() -> None:
    with pytest.raises(UnreadablePdfError):
        find_pdf_quote(b"not a pdf", "anything", start_page_number=1, end_page_number=2)


@pytest.mark.parametrize(("start", "end"), [(0, 1), (2, 2), (3, 1)])
def test_bad_page_range(start: int, end: int) -> None:
    with pytest.raises(ValueError):
        find_pdf_quote(FIXTURES / INVOICE, "x", start_page_number=start, end_page_number=end)


def test_many_threads_get_the_same_answers() -> None:
    """Calls from many threads at once are serialized by PDFIUM_LOCK and stay correct."""
    expected = [_run(case) for case in CASES]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_run, CASES * 3))
    assert results == expected * 3


def test_calls_wait_for_the_lock() -> None:
    """While something else holds PDFIUM_LOCK, a call doesn't touch pdfium; it waits."""
    done = threading.Event()

    def call() -> None:
        find_pdf_quote(FIXTURES / INVOICE, "Total due", start_page_number=1, end_page_number=2)
        done.set()

    with PDFIUM_LOCK:
        worker = threading.Thread(target=call)
        worker.start()
        assert not done.wait(0.3)
    assert done.wait(10)
    worker.join()
