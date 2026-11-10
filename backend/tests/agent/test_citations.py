"""Label lines, citation checks, line narrowing (answer 2), and re-deriving money and dates."""

from datetime import date
from pathlib import Path

import pytest
from anthropic.types import CitationCharLocation, CitationPageLocation

from app.agent.citations import (
    CitationProblem,
    SentDocument,
    SentImage,
    image_box,
    narrow_to_lines,
    parse_date,
    parse_label_lines,
    parse_money,
    resolve_citation,
)
from app.contracts.fixtures import load_sample_grant

from .fakes import text

INVOICE = load_sample_grant().document("file-invoice-1001")
DOC = SentDocument("file-invoice-1001", "text", text=INVOICE)


def char(chunk: str, index: int = 0, at: int | None = None) -> CitationCharLocation:
    start = INVOICE.find(chunk) if at is None else at
    return CitationCharLocation(
        type="char_location",
        cited_text=chunk,
        document_index=index,
        start_char_index=start,
        end_char_index=start + len(chunk),
    )


HEAD = "Example Lab Supply Co.\nINVOICE\nInvoice Number: INV-1001\nInvoice Date: November 12, 2025"


def test_label_lines_join_split_blocks_and_keep_their_citations():
    blocks = [
        text("Here are the values.\n@inv_number: "),
        text("INV-1001", [char(HEAD)]),
        text("\n@inv_date: "),
        text("November 12, 2025", [char(HEAD)]),
        text("\n@vendor: `Example Lab Supply Co.`\n- @total: $1,240.00\nDone."),
    ]
    lines = {ln.label: ln for ln in parse_label_lines(blocks)}
    assert set(lines) == {"inv_number", "inv_date", "vendor", "total"}
    assert lines["inv_number"].text == "INV-1001" and len(lines["inv_number"].citations) == 1
    assert lines["inv_date"].citations[0].cited_text == HEAD
    assert lines["vendor"].text == "Example Lab Supply Co." and lines["vendor"].citations == []
    assert lines["total"].text == "$1,240.00"


def test_a_text_citation_is_narrowed_to_the_line_that_holds_the_value():
    c = resolve_citation("INV-1001", [char(HEAD)], [DOC])
    assert c["passage"] == "Invoice Number: INV-1001"
    loc = c["location"]
    assert INVOICE[loc["start_char_index"] : loc["end_char_index"]] == "Invoice Number: INV-1001"
    assert c["match"] == "exact"


def test_a_value_that_appears_twice_in_the_passage_keeps_the_whole_passage():
    chunk = "Sediment core liners, 50 count: $1,240.00\n\nTotal Due: $1,240.00"
    c = resolve_citation("$1,240.00", [char(chunk)], [DOC])
    assert c["passage"] == chunk


def test_narrowing_covers_every_line_a_value_spans_and_stays_inside_the_passage():
    t = "Note: the order\nwas placed\non time.\nNext."
    start = t.find("the order")
    s, e = narrow_to_lines(t, start, t.find("Next."), "order\nwas placed")
    assert t[s:e] == "the order\nwas placed"


def test_the_citation_whose_passage_holds_the_text_is_picked():
    other = char("Total Due: $1,240.00")
    c = resolve_citation("INV-1001", [other, char(HEAD)], [DOC])
    assert c["passage"] == "Invoice Number: INV-1001"
    with pytest.raises(CitationProblem):
        resolve_citation("INV-9999", [other, char(HEAD)], [DOC])


def test_a_passage_not_at_its_characters_is_found_elsewhere_or_not_found():
    moved = char("Total Due: $1,240.00", at=0)
    assert resolve_citation("$1,240.00", [moved], [DOC])["match"] == "exact"
    bogus = CitationCharLocation(
        type="char_location",
        cited_text="Total Due: $9.00",
        document_index=0,
        start_char_index=0,
        end_char_index=16,
    )
    c = resolve_citation("$9.00", [bogus], [DOC])
    assert c["match"] == "not_found" and c["passage"] == "Total Due: $9.00"


def test_a_citation_to_a_document_not_sent_is_refused():
    with pytest.raises(CitationProblem):
        resolve_citation("INV-1001", [char(HEAD, index=3)], [DOC])


QUOTES_PDF = Path(__file__).parents[1] / "quotes" / "fixtures" / "invoice_reportlab.pdf"


@pytest.mark.skipif(
    not QUOTES_PDF.exists(), reason="the quote finder's test PDFs (#19) aren't here"
)
def test_a_pdf_citation_is_found_on_its_page_with_a_highlight():
    pdf = SentDocument("file-pdf", "pdf", pdf=QUOTES_PDF.read_bytes())
    raw = CitationPageLocation(
        type="page_location",
        cited_text="Invoice number: INV-SYN-0042",
        document_index=0,
        start_page_number=1,
        end_page_number=2,
    )
    c = resolve_citation("INV-SYN-0042", [raw], [pdf])
    assert c["match"] in ("exact", "close") and c["highlight"]
    assert resolve_citation(
        "INV-SYN-0042",
        [raw.model_copy(update={"cited_text": "Invoice number: INV-SYN-0042 nowhere"})],
        [pdf],
    )["match"] in ("not_found", "close")


def test_a_pixel_box_becomes_fractions_of_the_page():
    box = image_box(SentImage("file-photo", 1, 1000, 500), 100, 50, 300, 150)
    assert box == {
        "type": "image_box",
        "page": 1,
        "left": 0.1,
        "top": 0.1,
        "width": 0.2,
        "height": 0.2,
    }
    with pytest.raises(CitationProblem):
        image_box(SentImage("file-photo", 1, 1000, 500), 100, 50, 1300, 150)


@pytest.mark.parametrize(
    ("written", "cents"),
    [
        ("$1,240.00", 124000),
        ("$120,000", 12000000),
        ("-$400.00", -40000),
        ("($400.00)", -40000),
        ("12.5", 1250),
    ],
)
def test_money_is_read_from_its_text(written: str, cents: int):
    assert parse_money(written) == cents


def test_text_that_isnt_money_gives_nothing():
    assert parse_money("twelve dollars") is None


@pytest.mark.parametrize(
    ("written", "day"),
    [
        ("November 12, 2025", date(2025, 11, 12)),
        ("Nov 12, 2025", date(2025, 11, 12)),
        ("2025-11-12", date(2025, 11, 12)),
        ("11/12/2025", date(2025, 11, 12)),
        ("Sat, 21 Feb 2026 09:30:00 -0800", date(2026, 2, 21)),
    ],
)
def test_dates_are_read_from_their_text(written: str, day: date):
    assert parse_date(written) == day
