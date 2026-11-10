"""Draws the report's blocks as a PDF (Portable Document Format) file with ReportLab.

US Letter. Every page has a header with the award number, "DRAFT" or "Signed"
and the "as of" moment, and a footer with "Page x of y". The PDF's creation
date is the workspace's "now" and ReportLab's invariant mode is on, so the same
inputs give the same bytes.

The font is DejaVu Sans, regular and bold, shipped in app/packet/fonts/ with
its license (LICENSE: the Bitstream Vera Fonts license, with DejaVu's changes in
the public domain, a permissive license that allows embedding). The files are
DejaVu 2.37 as bundled in the matplotlib 3.11.2 wheel, matching its recorded
checksums. It's embedded as a subset, and it covers what quoted passages hold
beyond the PDF's built-in fonts: curly quotes, dashes, Greek letters such as
"μ", arrows, accented Latin letters, non-breaking hyphens and zero-width
spaces. Checksums use the built-in Courier, which only ever prints hex digits.

Table rows may split across pages (splitInRow), so a cell longer than a page,
such as a long note, never stops the report from being built.
"""

import re
from collections.abc import Callable
from datetime import datetime
from functools import cache
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)
from reportlab.platypus import Table as RLTable

from .view import Block, Heading, Para, Quote, ReportView, SignLines, Table

FONT_DIR = Path(__file__).parent / "fonts"
SANS = "ReportSans"
SANS_BOLD = "ReportSans-Bold"
MONO = "Courier"

PAGE_W, PAGE_H = LETTER
MARGIN = 0.75 * inch
TEXT_W = PAGE_W - 2 * MARGIN

INK = colors.HexColor("#1f2328")
MUTED = colors.HexColor("#5b636e")
RULE = colors.HexColor("#c9ced6")
SHADE = colors.HexColor("#f1f3f5")
DRAFT_INK = colors.HexColor("#a4262c")


@cache
def _fonts() -> None:
    pdfmetrics.registerFont(TTFont(SANS, str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(SANS_BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(
        SANS, normal=SANS, bold=SANS_BOLD, italic=SANS, boldItalic=SANS_BOLD
    )


def _style(name: str, **kw: Any) -> ParagraphStyle:
    base: dict[str, Any] = {"fontName": SANS, "fontSize": 9, "leading": 12, "textColor": INK}
    return ParagraphStyle(name, **(base | kw))


STYLES = {
    "title": _style("title", fontName=SANS_BOLD, fontSize=20, leading=24, spaceAfter=6),
    "subtitle": _style("subtitle", fontSize=11, leading=15),
    "state": _style("state", fontName=SANS_BOLD, fontSize=11, leading=15, textColor=DRAFT_INK),
    "h1": _style("h1", fontName=SANS_BOLD, fontSize=14, leading=18, spaceBefore=14, spaceAfter=6),
    "h3": _style("h3", fontName=SANS_BOLD, fontSize=10.5, leading=14, spaceBefore=10, spaceAfter=4),
    "body": _style("body", spaceAfter=4),
    "small": _style("small", fontSize=8, leading=10.5, textColor=MUTED, spaceAfter=4),
    "label": _style("label", fontName=SANS_BOLD, spaceBefore=6, spaceAfter=3),
    "quote": _style(
        "quote",
        fontName=SANS,
        fontSize=8.5,
        leading=11.5,
        leftIndent=14,
        borderPadding=(3, 4, 3, 4),
        backColor=SHADE,
        spaceBefore=2,
    ),
    "quote_source": _style(
        "quote_source", fontSize=7.5, leading=10, leftIndent=14, textColor=MUTED, spaceAfter=6
    ),
    "cell": _style("cell", fontSize=8, leading=10.5),
    "cell_head": _style("cell_head", fontName=SANS_BOLD, fontSize=8, leading=10.5),
    "cell_mono": _style("cell_mono", fontName=MONO, fontSize=6.5, leading=9),
    "sign": _style("sign", fontSize=9, leading=12),
}


def _markup(text: str, keep_spaces: bool = False) -> str:
    """Text for a ReportLab paragraph: markup characters escaped, line breaks kept."""
    out = escape(text)
    if keep_spaces:
        out = re.sub(r" {2,}", lambda m: " " + "&nbsp;" * (len(m.group()) - 1), out)
    return out.replace("\r\n", "\n").replace("\n", "<br/>")


def _para(text: str, style: str, keep_spaces: bool = False) -> Paragraph:
    return Paragraph(_markup(text, keep_spaces), STYLES[style])


def _table(t: Table) -> RLTable:
    has_head = any(t.headers)
    data: list[list[Flowable]] = []
    if has_head:
        data.append([_para(h, "cell_head") for h in t.headers])
    for row in t.rows:
        data.append(
            [
                _para(cell, "cell_mono" if i == t.mono_column else "cell")
                for i, cell in enumerate(row)
            ]
        )
    table = RLTable(
        data,
        colWidths=[w * TEXT_W for w in t.widths],
        repeatRows=1 if has_head else 0,
        hAlign="LEFT",
        splitInRow=1,
    )
    style: list[tuple[Any, ...]] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if has_head:
        style.append(("BACKGROUND", (0, 0), (-1, 0), SHADE))
    offset = 1 if has_head else 0
    for i in sorted(t.sub_rows):
        style.append(("LEFTPADDING", (0, i + offset), (0, i + offset), 14))
        style.append(("BACKGROUND", (0, i + offset), (-1, i + offset), colors.HexColor("#fafbfc")))
    table.setStyle(TableStyle(style))
    return table


def _sign_lines(s: SignLines) -> Flowable:
    rows = [[_para(label, "sign"), ""] for label in s.labels]
    table = RLTable(
        rows, colWidths=[1.1 * inch, 4 * inch], rowHeights=[30] * len(rows), hAlign="LEFT"
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LINEBELOW", (1, 0), (1, -1), 0.6, INK),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return KeepTogether([_para(s.title, "h3"), table])


def _flowables(block: Block) -> list[Flowable]:
    if isinstance(block, Heading):
        return [CondPageBreak(1.2 * inch), _para(block.text, "h3")]
    if isinstance(block, Para):
        return [_para(block.text, block.style)]
    if isinstance(block, Quote):
        return [
            KeepTogether(
                [
                    _para(f"“{block.passage}”", "quote", keep_spaces=True),
                    Spacer(1, 3),
                    _para(f"Source: {block.source}", "quote_source"),
                ]
            )
        ]
    if isinstance(block, Table):
        return [_table(block), Spacer(1, 6)]
    return [Spacer(1, 6), _sign_lines(block)]


def _canvas_class(view: ReportView, now: datetime, author: str) -> type[Canvas]:
    created = f"D:{now:%Y%m%d%H%M%S}+00'00'"
    state = "Signed" if view.signed else "DRAFT"

    class ReportCanvas(Canvas):
        """Holds every page until the end, so each footer can say "Page x of y"."""

        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, **kwargs)
            self._held: list[dict[str, Any]] = []
            date_formatter: Callable[..., str] = lambda *_: created  # noqa: E731
            self.setDateFormatter(date_formatter)
            self.setTitle(f"Evidence report {view.award_number}")
            self.setAuthor(author)
            self.setCreator("FundTrail")
            self.setSubject(f"{view.project_title}, as of {view.as_of}")

        def showPage(self) -> None:
            self._held.append(dict(self.__dict__))
            self._startPage()  # pyright: ignore[reportAttributeAccessIssue]

        def save(self) -> None:
            total = len(self._held)
            for page in self._held:
                self.__dict__.update(page)
                self._decorate(total)
                Canvas.showPage(self)
            Canvas.save(self)

        def _decorate(self, total: int) -> None:
            top = PAGE_H - 0.5 * inch
            self.setFont(SANS, 8)
            self.setFillColor(MUTED)
            self.drawString(MARGIN, top, f"Evidence report · {view.award_number}")
            right = f" · as of {view.as_of}"
            self.drawRightString(PAGE_W - MARGIN, top, right)
            self.setFont(SANS_BOLD, 8)
            self.setFillColor(DRAFT_INK if not view.signed else INK)
            self.drawRightString(
                PAGE_W - MARGIN - pdfmetrics.stringWidth(right, SANS, 8), top, state
            )
            self.setStrokeColor(RULE)
            self.setLineWidth(0.5)
            self.line(MARGIN, top - 5, PAGE_W - MARGIN, top - 5)
            self.setFont(SANS, 8)
            self.setFillColor(MUTED)
            page = f"Page {self.getPageNumber()} of {total}"
            self.drawCentredString(PAGE_W / 2, 0.45 * inch, page)

    return ReportCanvas


def render(view: ReportView, now: datetime, author: str) -> bytes:
    _fonts()
    story: list[Flowable] = [
        _para("Evidence report", "title"),
        _para(view.award_number, "subtitle"),
        _para(view.project_title, "subtitle"),
        _para(f"As of {view.as_of} (Coordinated Universal Time)", "subtitle"),
        _para("Signed" if view.signed else "DRAFT: not signed", "state"),
        Spacer(1, 6),
    ]
    for section in view.sections:
        story += [CondPageBreak(1.5 * inch), _para(section.title, "h1")]
        for block in section.blocks:
            story += _flowables(block)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        invariant=1,
        title=f"Evidence report {view.award_number}",
        author=author,
        creator="FundTrail",
    )
    doc.build(story, canvasmaker=_canvas_class(view, now, author))
    return buffer.getvalue()
