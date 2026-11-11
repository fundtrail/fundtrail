"""Label lines, citation checks, line narrowing (answer 2), and re-deriving money and dates."""

from datetime import date
from pathlib import Path
from typing import Any

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
    standing_occurrences,
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


def highlighted(c: dict[str, Any]) -> list[str]:
    ranges: list[dict[str, int]] = c.get("highlight") or []
    return [INVOICE[r["start_char_index"] : r["end_char_index"]] for r in ranges]


def test_a_text_citation_keeps_the_line_with_its_value_not_the_apis_whole_chunk():
    c = resolve_citation("INV-1001", [char(HEAD)], [DOC])
    assert c["passage"] == "Invoice Number: INV-1001"
    loc = c["location"]
    assert INVOICE[loc["start_char_index"] : loc["end_char_index"]] == c["passage"]
    assert highlighted(c) == ["Invoice Number: INV-1001"]
    assert c["match"] == "exact"


def test_a_value_stated_on_several_lines_covers_those_lines():
    chunk = "Sediment core liners, 50 count: $1,240.00\n\nTotal Due: $1,240.00"
    c = resolve_citation("$1,240.00", [char(chunk)], [DOC])
    assert c["passage"] == chunk


AWARD = load_sample_grant().document("file-award-letter")


def _narrowed(chunk: str, value: str) -> str:
    start = AWARD.find(chunk)
    s, e = narrow_to_lines(AWARD, start, start + len(chunk), value)
    return AWARD[s:e]


def test_a_value_only_counts_where_it_stands_on_its_own():
    """The main coordinator's ruling: "000" never matches inside "$120,000" or "00000"."""
    head = AWARD[: AWARD.find("AWARD INFORMATION")]
    assert "00000" in head and "000" in head.replace("Amendment Number: 000", "")
    assert _narrowed(head, "000") == "Amendment Number: 000"


def test_a_repeated_value_covers_the_lines_from_the_first_to_the_last_that_state_it():
    funding = AWARD[AWARD.find("FUNDING INFORMATION") : AWARD.find("PROJECT PERSONNEL")]
    assert _narrowed(funding, "$120,000") == (
        "Amount Obligated by this Amendment: $120,000\n"
        "Total Intended Award Amount: $120,000\n"
        "Cost Share: $0\n"
        "Total Amount Obligated to Date: $120,000"
    )


def test_a_value_that_stands_on_its_own_nowhere_keeps_the_whole_passage():
    t = "Paid $12,450.00 in full.\nThanks."
    assert narrow_to_lines(t, 0, len(t), "450.00") == (0, len(t))
    assert standing_occurrences(t, 0, len(t), "$12,450.00") == [5]


@pytest.mark.parametrize(
    ("text", "value", "alone"),
    [
        ("Total: $120,000", "000", False),
        ("EX 00000", "000", False),
        ("Number: 000.", "000", True),
        ("Paid -$450.00", "$450.00", False),
        ("Paid ($450.00)", "$450.00", False),
        ("Refund -$450.00", "-$450.00", True),
        ("SYN-2300117", "2300117", True),
    ],
)
def test_standing_on_its_own(text: str, value: str, alone: bool):
    assert bool(standing_occurrences(text, 0, len(text), value)) is alone


def test_narrowing_stays_inside_the_passage():
    """A label line holds one line of text, so a value never spans lines; its line is clipped
    to the passage when the passage starts partway along it."""
    t = "Note: the order\nwas placed\non time.\nNext."
    start = t.find("the order")
    s, e = narrow_to_lines(t, start, t.find("Next."), "order")
    assert t[s:e] == "the order"


def test_the_citation_whose_passage_holds_the_text_is_picked():
    other = char("Total Due: $1,240.00")
    c = resolve_citation("INV-1001", [other, char(HEAD)], [DOC])
    assert c["passage"] == "Invoice Number: INV-1001"
    assert highlighted(c) == ["Invoice Number: INV-1001"]
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


def test_a_pdf_citation_is_found_on_its_page_with_a_highlight():
    """The quote finder's own test PDF, a synthetic invoice."""
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
    # A box running off the image is cut to it; one with nothing on the image is no box.
    cut = image_box(SentImage("file-photo", 1, 1000, 500), 900, 50, 1300, 150)
    assert cut is not None and cut["left"] == 0.9 and abs(cut["width"] - 0.1) < 1e-9
    assert image_box(SentImage("file-photo", 1, 1000, 500), 1100, 50, 1300, 150) is None
    assert image_box(SentImage("file-photo", 1, 1000, 500), 100, 50, 100, 150) is None


@pytest.mark.parametrize(
    ("written", "cents"),
    [
        ("$1,240.00", 124000),
        ("$120,000", 12000000),
        ("12.5", 1250),
        ("USD 75.00", 7500),
        ("-$400.00", -40000),
        ("($400.00)", -40000),
        ("–$450.00", -45000),
        ("−$450.00", -45000),
        ("- $450.00", -45000),
        ("$-450.00", -45000),
        ("$450.00-", -45000),
        ("$450.00 –", -45000),
        ("(-$450.00)", -45000),
    ],
)
def test_money_is_read_from_its_text(written: str, cents: int):
    """A credit's sign is read however a document writes it (the main coordinator's ruling)."""
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
