"""Typeset PDFs for the samples' documents, drawn with reportlab.

`render(name, text)` picks a layout from the file's name and draws the rows of
`text` (what `Doc.text` holds) as a page that looks like ordinary paperwork: an
award notice laid out like a National Science Foundation (NSF) notice, a vendor's
invoice, a hotel folio, a report printed from an administrative system, a letter,
a filled form. Every row is drawn in the same words and in the same order, so the
page's text layer reads as `text` does. A layout adds only furniture that states
no fact: a page number, a column heading, a remit-to line repeating the vendor's
own address, small print that restates the invoice's own terms. A page laid out
like an agency's or a university's own notice also says at its foot that it's a
synthetic sample and wasn't issued by that body.

The pages are sober, as real paperwork is: black on white, small type, thin ruled
tables, a vendor's name in type with at most one muted color. On a vendor's form
and a system's report, what was filled in is set in Courier.

Nothing about a document is written into a layout. Names, addresses, rows and
totals all come from `text`, so the content can change without touching this
file: a table takes as many rows as it's given, a long description wraps, and a
long name shrinks or wraps before it reaches the block beside it.

`locate()` reads the PDF back with pdfium and says which pages each row is on.
It fails if a row isn't in the file, in order, so a layout can't drop a fact.

Only the 14 standard PDF fonts are used, and nothing is compressed or dated, so
the bytes are the same on every machine with the same reportlab. Needs reportlab
and pypdfium2, which the backend's environment has.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

W, H = letter
PRODUCER = "FundTrail sample generator"

SANS = ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique")
SERIF = ("Times-Roman", "Times-Bold", "Times-Italic")
MONO = ("Courier", "Courier-Bold", "Courier-Oblique")
# The mark on a page laid out like an agency's or a university's own notice.
SYNTHETIC = "Synthetic sample document for a software demonstration."

INK = HexColor("#111111")
MUTE = HexColor("#5F6368")
HAIR = HexColor("#B9BDC1")
STRIP = HexColor("#E8E9EB")
NAVY = HexColor("#1F4E6B")
BAND = HexColor("#EEF1F3")

# A row that is a label and its value: "Invoice date: May 12, 2025", "Account No.: 077103".
LABEL = re.compile(r"^\s*[A-Z][A-Za-z ()]{1,40}(?: No\.)?: \S")
MONEY = r"-?\$[\d,]+(?:\.\d\d)?"
# The foot of the page: a row drawn below it means the document didn't fit.
FLOOR = 30.0
# The page's side margin: a string drawn past it would be cut off.
EDGE = 36.0
# The room a letter leaves between its closing and the signer's printed name.
SIGNATURE_ROOM = 34.0


class Pen:
    """A canvas with a cursor, the document's type family, and page furniture."""

    def __init__(self, title: str, family: tuple[str, str, str], total: int | None) -> None:
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=letter, invariant=1, pageCompression=0)
        self.c.setTitle(title)
        self.c.setCreator(PRODUCER)
        self.c.setProducer(PRODUCER)
        self.family = family
        # A form's own words are set in `family`. With `typed`, what was filled into it
        # (the values, the rows) is set in Courier, as a billing system prints them.
        self.typed = False
        self.total = total  # how many pages the document has, known on the second pass
        self.page = 1
        self.top = H - 72
        self.bottom = 72.0
        self.y = self.top
        # Drawn on every page as it closes: the footer.
        self.furniture: Callable[[Pen], None] | None = None

    def font(self, bold: bool = False, italic: bool = False, data: bool = False) -> str:
        family = MONO if data and self.typed else self.family
        return family[1] if bold else family[2] if italic else family[0]

    def width(
        self, s: str, size: float, bold: bool = False, italic: bool = False, data: bool = False
    ) -> float:
        return stringWidth(s, self.font(bold, italic, data), size)

    def text(
        self,
        x: float,
        y: float,
        s: str,
        size: float = 9,
        *,
        bold: bool = False,
        italic: bool = False,
        color: Color = INK,
        align: str = "left",
        data: bool = False,
    ) -> float:
        """One string on one baseline. `data` marks a filled-in value (see `typed`).
        Returns its width."""
        s.encode("ascii")
        if y < FLOOR:
            raise ValueError(f"ran off the page at {s!r}")
        if data and self.typed:
            size -= 0.5
        wide = self.width(s, size, bold, italic, data)
        left = x - wide if align == "right" else x - wide / 2 if align == "center" else x
        if left < EDGE or left + wide > W - EDGE:
            raise ValueError(f"ran past the page's edge at {s!r}")
        self.c.setFillColor(color)
        self.c.setFont(self.font(bold, italic, data), size)
        if align == "right":
            self.c.drawRightString(x, y, s)
        elif align == "center":
            self.c.drawCentredString(x, y, s)
        else:
            self.c.drawString(x, y, s)
        return wide

    def field(
        self,
        x: float,
        y: float,
        row: str,
        size: float = 9,
        *,
        label_size: float | None = None,
        label_color: Color | None = None,
        bold_label: bool = True,
        align: str = "left",
        value_x: float | None = None,
    ) -> None:
        """A "Label: value" row on one baseline, the label set apart from the value.

        `value_x` starts every value at one place, so a block's values line up."""
        label, sep, value = row.strip().partition(": ")
        label_size = label_size or size
        if not sep:
            self.text(x, y, label, label_size, bold=bold_label, color=label_color or INK)
            return
        label += ":"
        lw = self.width(label, label_size, bold=bold_label) + self.width(" ", size)
        if align == "right":
            x -= lw + self.width(value, size - (0.5 if self.typed else 0), data=True)
        self.text(x, y, label, label_size, bold=bold_label, color=label_color or INK)
        at = x + lw if value_x is None else max(value_x, x + lw)
        self.text(at, y, value, size, data=True)

    def wrap(self, s: str, width: float, size: float, **style: bool) -> list[str]:
        if style.get("data") and self.typed:
            size -= 0.5
        out: list[str] = []
        line = ""
        for word in s.split():
            trial = f"{line} {word}".strip()
            if line and self.width(trial, size, **style) > width:
                out.append(line)
                line = word
            else:
                line = trial
        if line:
            out.append(line)
        return out

    def para(
        self,
        x: float,
        width: float,
        s: str,
        size: float = 9,
        leading: float | None = None,
        *,
        color: Color = INK,
        bold: bool = False,
        italic: bool = False,
        align: str = "left",
    ) -> None:
        """A paragraph from the cursor down, wrapped to `width`. It's kept on one page:
        a page's footer would otherwise fall inside a passage a record cites."""
        leading = leading or size * 1.36
        at = x + width if align == "right" else x + width / 2 if align == "center" else x
        lines = self.wrap(s, width, size, bold=bold, italic=italic)
        self.need(leading * len(lines))
        for line in lines:
            self.text(at, self.y, line, size, bold=bold, italic=italic, color=color, align=align)
            self.y -= leading

    def stack(
        self,
        x: float,
        y: float,
        rows: list[str],
        width: float,
        size: float = 9,
        leading: float | None = None,
        *,
        color: Color = INK,
        align: str = "left",
        fields: bool = False,
        data: bool = False,
        **field_style,
    ) -> float:
        """Rows one under another from `y`, a long one wrapped to `width`.

        With `fields`, a "Label: value" row that fits is drawn as a field. Returns
        the height under the last row."""
        leading = leading or size * 1.36
        at = x + width if align == "right" else x + width / 2 if align == "center" else x
        for row in rows:
            row = row.strip()
            label, _, value = row.partition(": ")
            fits = self.width(label + ": ", size, bold=True) + self.width(value, size, data=True)
            if fields and LABEL.match(row) and fits <= width:
                self.field(at, y, row, size, align=align, **field_style)
                y -= leading
                continue
            for line in self.wrap(row, width, size, data=data):
                self.text(at, y, line, size, color=color, align=align, data=data)
                y -= leading
        return y

    def wordmark(
        self,
        x: float,
        y: float,
        name: str,
        size: float,
        width: float,
        *,
        color: Color = INK,
        align: str = "left",
    ) -> float:
        """An organization's name in bold type: shrunk a little to fit `width`, then
        wrapped. Returns the height under it."""
        fitted = size
        while fitted > size * 0.8 and self.width(name, fitted, bold=True) > width:
            fitted -= 0.5
        at = x + width if align == "right" else x + width / 2 if align == "center" else x
        for line in self.wrap(name, width, fitted, bold=True):
            self.text(at, y, line, fitted, bold=True, color=color, align=align)
            y -= fitted * 1.18
        return y

    def rule(self, x0: float, x1: float, y: float, color: Color = HAIR, width: float = 0.5) -> None:
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        self.c.line(x0, y, x1, y)

    def upright(self, x: float, y0: float, y1: float, color: Color = HAIR, width: float = 0.5):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        self.c.line(x, y0, x, y1)

    def box(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: Color | None = None,
        stroke: Color | None = None,
        line: float = 0.5,
    ) -> None:
        """A rectangle whose lower left corner is (x, y)."""
        if fill is not None:
            self.c.setFillColor(fill)
        if stroke is not None:
            self.c.setStrokeColor(stroke)
            self.c.setLineWidth(line)
        self.c.rect(x, y, w, h, stroke=int(stroke is not None), fill=int(fill is not None))

    def page_number(self, x: float, y: float, align: str = "right", size: float = 7.5) -> None:
        self.text(x, y, f"Page {self.page} of {self.total or 1}", size, color=MUTE, align=align)

    def need(self, height: float) -> None:
        """Starts a new page if `height` doesn't fit above the bottom margin."""
        if self.y - height < self.bottom:
            if self.furniture:
                self.furniture(self)
            self.c.showPage()
            self.page += 1
            self.y = self.top

    def done(self) -> bytes:
        if self.furniture:
            self.furniture(self)
        self.c.save()
        return self.buf.getvalue()


def blocks(rows: list[str]) -> list[list[str]]:
    """The rows in runs, split at the blank rows."""
    out: list[list[str]] = [[]]
    for row in rows:
        if row.strip():
            out[-1].append(row)
        elif out[-1]:
            out.append([])
    return [b for b in out if b]


def cells(row: str) -> list[str]:
    """A table row's cells: the text renderers pad them at least two spaces apart."""
    return re.split(r"\s{2,}", row.strip())


def amount_row(row: str) -> tuple[list[str], str]:
    """A row that ends in an amount: its other cells, and the amount."""
    m = re.match(rf"^(.*?)\s+({MONEY})\s*$", row.strip())
    if not m:
        raise ValueError(f"no amount at the end of {row!r}")
    return cells(m.group(1)), m.group(2)


def value_of(rows: list[str], label: str) -> str:
    return next(r.split(": ", 1)[1] for r in rows if r.strip().startswith(label + ": "))


def is_prose(block: list[str]) -> bool:
    """Whether a block is a paragraph the text renderer wrapped, not a list of rows."""
    return block[-1].endswith(".") and not LABEL.match(block[0]) and not block[0].endswith(":")


def across(
    p: Pen, rows: list[str], width: float, size: float, gap: float = 12
) -> list[list[tuple[str, float, float]]]:
    """Fields laid side by side, as many to a line as fit in `width`.

    Each line is (row, how far along it starts, how wide its place is). A line's
    places take its spare room between them, so they fill the width."""
    lines: list[list[tuple[str, float]]] = [[]]
    for row in rows:
        need = min(p.width(row, size, bold=True) * 1.08 + gap, width)
        if lines[-1] and sum(w for _, w in lines[-1]) + need > width:
            lines.append([])
        lines[-1].append((row, need))
    out = []
    for line in lines:
        spare = (width - sum(w for _, w in line)) / len(line)
        at, placed = 0.0, []
        for row, need in line:
            placed.append((row, at, need + spare))
            at += need + spare
        out.append(placed)
    return out


def page_footer(x1: float, y: float = 40) -> Callable[[Pen], None]:
    return lambda p: p.page_number(x1, y)


def marked_footer(not_issued_by: str, y: float = 46) -> Callable[[Pen], None]:
    """The foot of a page laid out like an agency's or a university's own notice: the
    page number, and under it the mark that the page is a synthetic sample."""

    def draw(p: Pen) -> None:
        p.page_number(W / 2, y, "center", 8)
        mark = f"{SYNTHETIC} Not issued by {not_issued_by}."
        p.text(W / 2, y - 12, mark, 7, color=MUTE, align="center")

    return draw


# ------------------------------------------------------------------ NSF award notices


def notice(rows: list[str], total: int | None, look: str | None = None) -> Pen:
    """An award notice laid out like NSF's: a centered title, grey section bands, bold labels."""
    title = (
        f"NSF Award Notice for Award ID {value_of(rows, 'Award Number (FAIN)')}"
        f" - Amendment ID {value_of(rows, 'Amendment Number')}"
    )
    p = Pen(title, SANS, total)
    left, right = 78.0, W - 78
    size, lead = 10.5, 14.5
    p.top, p.bottom = H - 84, 80
    p.furniture = marked_footer("the National Science Foundation", 50)
    p.y = H - 96
    p.text(W / 2, p.y, rows[0], 13, color=NAVY, align="center")
    p.y -= 22
    p.text(W / 2, p.y, rows[1], 9.5, italic=True, color=NAVY, align="center")
    p.y -= 18

    def band(text: str, keep: float) -> None:
        p.need(34 + keep)
        p.y -= 8
        p.box(left - 8, p.y - 9, right - left + 16, 26, fill=BAND)
        p.text(left, p.y, text, size, bold=True)
        p.y -= 30

    section = ""
    budget_rows = 0
    i = 2
    while i < len(rows):
        row = rows[i]
        i += 1
        if not row.strip():
            continue
        if row.isupper() and ":" not in row and not row.startswith(" "):
            section = row
            keep = {"PROJECT PERSONNEL": 48, "BUDGET": 26 + 5 * 17}.get(section, 3 * lead)
            band(row, keep)
        elif section == "BUDGET" and re.search(rf"{MONEY}\s*$", row):
            (label,), amount = amount_row(row)
            sub = row.startswith(" ")
            budget_rows += 1
            p.need(18)
            p.text(left + (22 if sub else 0), p.y, label, size, bold=not sub)
            p.text(right - 20, p.y, amount, size, align="right")
            p.rule(left, right, p.y - 4.5, HexColor("#D5DADD"), 0.4)
            p.y -= 17
        elif row.startswith("Amendment Description: ") or not LABEL.match(row):
            # A paragraph the text renderer wrapped: every row up to the next blank or
            # indented one. A wrapped row can itself look like a label ("costs: funds
            # budgeted for"), so inside the description and the terms every row is taken.
            wrapped = row.startswith("Amendment Description: ") or section.startswith("TERMS")
            body = [row]
            while i < len(rows) and rows[i].strip() and not rows[i].startswith(" "):
                if LABEL.match(rows[i]) and not wrapped:
                    break
                body.append(rows[i])
                i += 1
            text = " ".join(body)
            if text.startswith("Amendment Description: "):
                p.need(3 * lead)
                p.text(left, p.y, "Amendment Description:", size, bold=True)
                p.y -= lead
                text = text.removeprefix("Amendment Description: ")
            elif section == "BUDGET" or section == "NSF CONTACT INFORMATION":
                # The line over the budget's rows, or the closing sentence under them.
                p.y -= 10 if budget_rows or section != "BUDGET" else 2
            p.para(left, right - left, text, size, lead)
            if section == "BUDGET":
                p.y -= 6
        else:
            p.need(lead)
            p.field(left + (14 if row.startswith(" ") else 0), p.y, row, size)
            p.y -= lead
            if row.strip().startswith("Organization: "):
                p.y -= 4
    return p


# ------------------------------------------------------------------ vendor invoices


class Bill:
    """An invoice's parts, read from its rows (render.invoice writes them in this order):
    the vendor, the invoice's own numbers, who it bills, the items, the totals, the terms."""

    def __init__(self, rows: list[str]) -> None:
        b = blocks(rows)
        if len(b) != 7 or len(b[0]) < 2 or len(b[3]) < 3:
            raise ValueError("these aren't an invoice's rows")
        self.vendor, *self.contact = (r.strip() for r in b[0])
        self.heading = b[1][0].strip()
        self.details = [r.strip() for r in b[2]]
        self.bill_to = b[3][0].strip()
        self.bill_lines = [r.strip() for r in b[3][1:] if r.startswith(" ")]
        self.after_bill = [r.strip() for r in b[3][1:] if not r.startswith(" ")]
        self.head = cells(b[4][0])
        # An item row: its number, its description, the quantity and the two amounts,
        # and, with seven columns, its catalog number and its unit of measure.
        shapes = {
            5: rf"^(\S+)\s+(.+?)\s+(\S+)\s+({MONEY})\s+({MONEY})$",
            7: rf"^(\S+)\s+(\S+)\s+(.+?)\s+(\S+)\s+(\S+)\s+({MONEY})\s+({MONEY})$",
        }
        if len(self.head) not in shapes:
            raise ValueError(f"an item table has five or seven columns, not {self.head}")
        self.items: list[list[str]] = []
        for row in b[4][1:]:
            m = re.match(shapes[len(self.head)], row.strip())
            if not m:
                raise ValueError(f"not an item row: {row!r}")
            self.items.append(list(m.groups()))
        self.totals = [amount_row(r) for r in b[5]]
        self.terms = [r.strip() for r in b[6]]
        self.number = value_of(rows, "Invoice number")

    def remit(self) -> str:
        return "Remit to: " + ", ".join([self.vendor.title(), *self.contact[:1]])

    def small_print(self) -> list[str]:
        """The foot's boilerplate. The payment sentence restates the invoice's own terms,
        so it's there only where they say net 30."""
        net30 = any(re.search(r"\bnet 30\b", row) for row in self.terms)
        return [
            *(["Payment is due within 30 days of the invoice date."] if net30 else []),
            "Show our invoice number on your remittance. A late charge may be added to past "
            "due balances.",
            "Report shortages or freight damage when the goods are received. Returns need "
            "our authorization.",
        ]

    def monogram(self) -> str:
        return "".join(word[0] for word in self.vendor.split() if word[0].isalpha())[:3]


def item_table(
    p: Pen,
    b: Bill,
    y: float,
    x0: float,
    x1: float,
    look: str,
    accent: Color,
    size: float = 9,
    depth: float = 230,
) -> float:
    """The item table: thin rules, a wrapped description, any number of rows.

    It takes the header's five columns or its seven. `look` is "rules" (a rule over
    and under the header), "accent" (a colored rule under it), "box" (a printed
    form's box with column rules) or "grid" (the same, with a rule under every row).
    Like a printed form, the table runs on down the page under its last row, to
    `depth` below the header. Returns the height of the table's foot."""
    pad, lead = 5.0, size * 1.3
    if len(b.head) == 7:
        columns = [("left", 28), ("left", 68), ("left", 0), ("right", 30), ("left", 28)]
    else:
        columns = [("left", 34), ("left", 0), ("right", 42)]
    columns += [("right", 64), ("right", 70)]
    room = x1 - x0 - sum(width for _, width in columns)
    edges = [x0]
    for _, width in columns:
        edges.append(edges[-1] + (width or room))
    described = next(i for i, (_, width) in enumerate(columns) if not width)

    def cell(i: int, y: float, text: str, **style) -> None:
        if columns[i][0] == "left":
            p.text(edges[i] + pad, y, text, align="left", **style)
        else:
            p.text(edges[i + 1] - pad, y, text, align="right", **style)

    top = y + size + 5
    if look == "grid":
        p.box(x0, y - 6, x1 - x0, size + 11, fill=STRIP)
    for i, text in enumerate(b.head):
        cell(i, y, text, size=size - 1, bold=True, color=accent if look == "accent" else INK)
    if look == "rules":
        p.rule(x0, x1, top, INK, 0.8)
    p.rule(x0, x1, y - 6, accent if look == "accent" else INK, 1.1 if look == "accent" else 0.8)
    y -= 6
    for item in b.items:
        lines = p.wrap(
            item[described], edges[described + 1] - edges[described] - 2 * pad, size, data=True
        )
        y -= lead + 3
        for i, text in enumerate(item):
            if i == described:
                for n, line in enumerate(lines):
                    cell(i, y - n * lead, line, size=size, data=True)
            else:
                cell(i, y, text, size=size, data=True)
        y -= (len(lines) - 1) * lead + 6
        if look != "box":
            p.rule(x0, x1, y)
    y = min(y - 10, top - depth)
    if look in ("box", "grid"):
        p.box(x0, y, x1 - x0, top - y, stroke=INK, line=0.7)
        for x in edges[1:-1]:
            p.upright(x, y, top, INK if look == "box" else HAIR, 0.5)
    else:
        p.rule(x0, x1, y, INK, 0.8)
    return y


def total_rows(
    p: Pen, b: Bill, y: float, x: float, x1: float, look: str, accent: Color, size: float = 9
) -> float:
    """The totals, label and amount on one baseline, the last one set apart.

    Returns the height under them."""
    lead = size * 1.75
    for n, (label, amount) in enumerate(b.totals):
        last = n == len(b.totals) - 1
        y -= lead
        if look == "grid":
            p.box(x, y - 5, x1 - x, lead, stroke=INK if last else HAIR, line=0.7 if last else 0.5)
        elif last and look == "double":
            p.rule(x, x1, y + size + 3.5, INK, 0.6)
            p.rule(x, x1, y + size + 1.5, INK, 0.6)
        elif last:
            p.rule(x, x1, y + size + 2.5, accent, 1)
        p.text(x + 6, y, " ".join(label), size, bold=last)
        p.text(x1 - 6, y, amount, size, bold=last, align="right", data=True)
    return y - 5


def invoice_foot(p: Pen, b: Bill, x0: float, x1: float, *, center: bool = False) -> None:
    """The foot of an invoice: the remit-to line, the small print, the page number."""
    small = b.small_print()
    # A long remit-to line wraps, clear of the page number beside it.
    remit = p.wrap(b.remit(), x1 - x0 - (0 if center else 70), 7.5)
    top = 46.0 + 8 * len(small) + 9 * (len(remit) - 1)
    p.rule(x0, x1, top + 11)
    at, align = ((x0 + x1) / 2, "center") if center else (x0, "left")
    y = top
    for line in remit:
        p.text(at, y, line, 7.5, color=MUTE, align=align)
        y -= 9
    y += 1
    for line in small:
        p.text(at, y, line, 6.5, color=MUTE, align=align)
        y -= 8
    if center:
        p.page_number((x0 + x1) / 2, y - 2, "center")
    else:
        p.page_number(x1, top)


def invoice_ledger(b: Bill, total: int | None) -> Pen:
    """Sans serif: the vendor's name at the left, the invoice's numbers right-aligned
    opposite the bill-to block, a ruled table."""
    accent = HexColor("#2E5A60")
    p = Pen(f"Invoice {b.number}", SANS, total)
    p.typed = True
    x0, x1 = 54.0, W - 54
    y = p.wordmark(x0, H - 58, b.vendor, 14, x1 - x0 - 130, color=accent)
    y = p.stack(x0, y + 3, b.contact, x1 - x0 - 130, 8, color=MUTE)
    p.text(x1, H - 58, b.heading, 15, bold=True, align="right")
    y = min(y, H - 84) - 2
    p.rule(x0, x1, y, accent, 1)
    y -= 22
    right = p.stack(
        x1 - 190,
        y,
        b.details,
        190,
        9,
        13,
        align="right",
        fields=True,
        label_color=MUTE,
        bold_label=False,
    )
    p.text(x0, y, b.bill_to, 7.5, bold=True, color=MUTE)
    left = p.stack(x0, y - 13, b.bill_lines, x1 - x0 - 210, 9, 12.5, data=True)
    y = min(left, right) - 6
    y = p.stack(x0, y, b.after_bill, x1 - x0, 9, 12.5, fields=True)
    y = item_table(p, b, y - 20, x0, x1, "rules", accent)
    y = total_rows(p, b, y - 2, x1 - 190, x1, "rule", INK)
    p.stack(x0, y + 18, b.terms, x1 - x0 - 210, 9, 12.5, fields=True)
    invoice_foot(p, b, x0, x1)
    return p


def invoice_paper(b: Bill, total: int | None) -> Pen:
    """Serif, on a printed form: a double rule under the head and a boxed table."""
    p = Pen(f"Invoice {b.number}", SERIF, total)
    x0, x1 = 66.0, W - 66
    y = p.wordmark(x0, H - 66, b.vendor, 16, x1 - x0 - 120)
    y = p.stack(x0, y + 4, b.contact, x1 - x0 - 120, 9.5)
    p.text(x1, H - 66, b.heading, 18, bold=True, align="right")
    y = min(y, H - 96)
    p.rule(x0, x1, y, INK, 1.6)
    p.rule(x0, x1, y - 3, INK, 0.5)
    y -= 26
    right = p.stack(x1 - 170, y, b.details, 170, 10, 14)
    p.text(x0, y, b.bill_to, 10, bold=True)
    left = p.stack(x0, y - 14, b.bill_lines, x1 - x0 - 190, 10, 14)
    y = min(left, right) - 8
    y = p.stack(x0, y, b.after_bill, x1 - x0, 10, 14)
    y = item_table(p, b, y - 22, x0, x1, "box", INK, 10)
    y = total_rows(p, b, y - 4, x1 - 190, x1, "double", INK, 10)
    p.stack(x0, y + 20, b.terms, x1 - x0 - 210, 10, 14)
    p.text(W / 2, 84, "Thank you for your order.", 9, italic=True, align="center")
    invoice_foot(p, b, x0, x1, center=True)
    return p


def invoice_grid(b: Bill, total: int | None) -> Pen:
    """Sans serif: the title at the left and the vendor at the right, the invoice's
    numbers and the bill-to in ruled cells, a table with every cell ruled."""
    accent = HexColor("#2F4F3A")
    p = Pen(f"Invoice {b.number}", SANS, total)
    p.typed = True
    x0, x1 = 54.0, W - 54
    y = p.wordmark(x0 + 150, H - 56, b.vendor, 13, x1 - x0 - 150, color=accent, align="right")
    y = p.stack(x0 + 150, y + 3, b.contact, x1 - x0 - 150, 8, color=MUTE, align="right")
    p.text(x0, H - 60, b.heading, 20, bold=True)
    y = min(y, H - 86) - 4
    # The invoice's own numbers, one ruled cell each.
    for line in across(p, b.details, x1 - x0, 9):
        for row, at, width in line:
            p.box(x0 + at, y - 22, width, 22, stroke=INK)
            p.field(
                x0 + at + 6, y - 14.5, row, 9, label_size=7.5, label_color=MUTE, bold_label=False
            )
        y -= 22
    lines = [w for row in b.bill_lines for w in p.wrap(row, x1 - x0 - 12, 9, data=True)]
    extra = [w for row in b.after_bill for w in p.wrap(row, x1 - x0 - 12, 9)]
    height = 20 + 12 * (len(lines) + len(extra)) + (5 if extra else 0)
    p.box(x0, y - height, x1 - x0, height, stroke=INK)
    p.text(x0 + 6, y - 12, b.bill_to, 7.5, color=MUTE)
    at = p.stack(x0 + 6, y - 25, b.bill_lines, x1 - x0 - 12, 9, 12, data=True)
    p.stack(x0 + 6, at - 5, b.after_bill, x1 - x0 - 12, 9, 12, fields=True)
    y = item_table(p, b, y - height - 28, x0, x1, "grid", accent)
    y = total_rows(p, b, y, x1 - 190, x1, "grid", INK)
    p.stack(x0, y + 18, b.terms, x1 - x0 - 210, 9, 12.5, fields=True)
    invoice_foot(p, b, x0, x1)
    return p


def invoice_centered(b: Bill, total: int | None) -> Pen:
    """Serif: a centered letterhead between thin rules, the invoice's numbers in one strip."""
    accent = HexColor("#6B1F2A")
    p = Pen(f"Invoice {b.number}", SERIF, total)
    x0, x1 = 72.0, W - 72
    p.rule(x0, x1, H - 50, accent, 1.2)
    y = p.wordmark(x0, H - 70, b.vendor, 17, x1 - x0, color=accent, align="center")
    y = p.stack(x0, y + 4, b.contact, x1 - x0, 9, color=MUTE, align="center")
    p.rule(x0, x1, y + 4, accent, 0.5)
    y -= 18
    p.text(W / 2, y, b.heading, 12, bold=True, align="center")
    y -= 20
    p.rule(x0, x1, y + 12)
    for line in across(p, b.details, x1 - x0 - 8, 9.5):
        for row, at, _ in line:
            p.field(x0 + 4 + at, y, row, 9.5)
        y -= 14
    p.rule(x0, x1, y + 7)
    y -= 14
    p.text(x0, y, b.bill_to, 9.5, bold=True)
    y = p.stack(x0 + 12, y - 13.5, b.bill_lines, x1 - x0 - 12, 9.5, 13.5)
    y = p.stack(x0, y - 5, b.after_bill, x1 - x0, 9.5, 13.5, fields=True)
    y = item_table(p, b, y - 22, x0, x1, "accent", accent, 9.5)
    y = total_rows(p, b, y - 2, x1 - 190, x1, "rule", accent, 9.5)
    p.stack(x0, y + 19, b.terms, x1 - x0 - 210, 9.5, 13.5, fields=True)
    invoice_foot(p, b, x0, x1, center=True)
    return p


def invoice_strip(b: Bill, total: int | None) -> Pen:
    """Sans serif: a heavy rule across the top, a small monogram beside the vendor's
    name, the invoice's numbers in two aligned columns."""
    accent = HexColor("#1F2F4A")
    p = Pen(f"Invoice {b.number}", SANS, total)
    p.typed = True
    x0, x1 = 50.0, W - 50
    p.rule(x0, x1, H - 44, accent, 3)
    p.box(x0, H - 84, 26, 26, stroke=accent, line=1)
    p.text(x0 + 13, H - 74.5, b.monogram(), 9, bold=True, color=accent, align="center")
    y = p.wordmark(x0 + 36, H - 68, b.vendor, 13, x1 - x0 - 150)
    # The address and the email share a line, when both fit on it.
    contact = "   ".join(b.contact)
    if p.width(contact, 8) <= x1 - x0 - 36:
        for n, part in enumerate(b.contact):
            p.text(
                x0 + 36 + p.width("   ".join(b.contact[:n] + [""]), 8), y + 3, part, 8, color=MUTE
            )
        y -= 8
    else:
        y = p.stack(x0 + 36, y + 3, b.contact, x1 - x0 - 36, 8, color=MUTE)
    p.text(x1, H - 68, b.heading, 11, bold=True, color=accent, align="right")
    y = min(y, H - 88) - 4
    p.rule(x0, x1, y)
    y -= 20
    tab = max(p.width(r.partition(": ")[0] + ":", 9) for r in b.details) + 10
    right = y
    for row in b.details:
        p.field(x1 - 200, right, row, 9, label_color=MUTE, bold_label=False, value_x=x1 - 200 + tab)
        right -= 13
    p.text(x0, y, b.bill_to, 9, bold=True)
    left = p.stack(x0, y - 13, b.bill_lines, x1 - x0 - 220, 9, 12.5, data=True)
    y = min(left, right) - 6
    y = p.stack(x0, y, b.after_bill, x1 - x0, 9, 12.5, fields=True)
    y = item_table(p, b, y - 20, x0, x1, "accent", accent)
    y = total_rows(p, b, y - 2, x1 - 190, x1, "rule", accent)
    p.stack(x0, y + 18, b.terms, x1 - x0 - 210, 9, 12.5, fields=True)
    invoice_foot(p, b, x0, x1)
    return p


INVOICE_LOOKS: dict[str, Callable[[Bill, int | None], Pen]] = {
    "ledger": invoice_ledger,
    "paper": invoice_paper,
    "grid": invoice_grid,
    "centered": invoice_centered,
    "strip": invoice_strip,
}


def invoice(rows: list[str], total: int | None, look: str | None = None) -> Pen:
    """A vendor's invoice. `look` is the vendor's own, the same on every invoice it sends."""
    if look is not None and look not in INVOICE_LOOKS:
        raise ValueError(f"no invoice look named {look!r}")
    return INVOICE_LOOKS[look or "ledger"](Bill(rows), total)


# ------------------------------------------------------------------ reports from a system


def report_head(p: Pen, x0: float, x1: float, owner: str, title: str) -> float:
    """A system report's header strip, with whose report it is at the left. The
    report's name goes at the right (`report_title`), drawn when the text reaches it.
    Returns the height under the strip."""
    p.box(x0, H - 64, x1 - x0, 24, fill=STRIP)
    room = x1 - x0 - 24 - p.width(title, 11, bold=True)
    p.wordmark(x0 + 8, H - 55.5, owner, 8.5, room)
    p.rule(x0, x1, H - 64, INK, 0.8)
    return H - 64


def report_title(p: Pen, x1: float, title: str) -> None:
    p.text(x1 - 8, H - 56, title, 11, bold=True, align="right")


def grid_cell(
    p: Pen, x: float, top: float, width: float, rows: list[str], *, lead: float = 13
) -> float:
    """One ruled cell holding fields with small grey labels, a long value wrapped.

    Returns the height of the cell's foot."""
    drawn: list[tuple[str, bool]] = []
    for row in rows:
        if p.width(row.strip(), 9, data=True) + 6 <= width - 12:
            drawn.append((row.strip(), True))
        else:
            drawn += [(line, False) for line in p.wrap(row.strip(), width - 12, 9, data=True)]
    height = lead * len(drawn) + 8
    p.box(x, top - height, width, height, stroke=HAIR)
    for n, (line, whole) in enumerate(drawn):
        y = top - 13.5 - n * lead
        if whole and LABEL.match(line):
            p.field(x + 6, y, line, 9, label_size=7.5, label_color=MUTE, bold_label=False)
        else:
            p.text(x + 6, y, line, 9, data=True)
    return top - height


def field_grid(p: Pen, x0: float, x1: float, top: float, rows: list[str]) -> float:
    """Fields in a ruled grid, two to a row; a field too long for half the width takes
    a row of its own. Returns the height of the grid's foot."""
    half = (x1 - x0) / 2
    i = 0
    while i < len(rows):
        fits = [p.width(r.strip(), 9, data=True) + 6 <= half - 12 for r in rows[i : i + 2]]
        pair = len(fits) == 2 and all(fits)
        if pair:
            grid_cell(p, x0, top, half, [rows[i]])
            top = grid_cell(p, x0 + half, top, half, [rows[i + 1]])
            i += 2
        else:
            top = grid_cell(p, x0, top, x1 - x0, [rows[i]])
            i += 1
    return top


def section_strip(p: Pen, x0: float, x1: float, y: float, text: str) -> float:
    """A section's name on a thin grey strip. Returns the height under it."""
    lines = p.wrap(text, x1 - x0 - 12, 8.5, bold=True)
    height = 11 * len(lines) + 6
    p.box(x0, y - height, x1 - x0, height, fill=STRIP)
    for n, line in enumerate(lines):
        p.text(x0 + 6, y - 12 - n * 11, line, 8.5, bold=True)
    return y - height


def amount_table(
    p: Pen,
    x0: float,
    x1: float,
    y: float,
    head: list[str] | None,
    rows: list[str],
    *,
    furniture: tuple[str, ...] = (),
    total_last: bool = True,
    bold: bool = False,
) -> float:
    """A ruled table whose rows end in an amount, the last one a total.

    `head` is the header row's cells from the text; `furniture` is a header the
    text doesn't have, drawn in grey. `bold` sets every row as a total. Returns the
    height of the table's foot."""
    parsed = [amount_row(r) for r in rows]
    n_left = max(len(left) for left, _ in parsed)
    # The first column takes what the others leave; the rest are right-aligned.
    rights = [x1 - 6 - 78 * k for k in range(n_left - 1, -1, -1)]
    first_width = rights[0] - (78 if n_left > 1 else 0) - x0 - 20
    top = y
    labels = head or list(furniture)
    if labels:
        y -= 16
        color = INK if head else MUTE
        p.text(x0 + 6, y + 4.5, labels[0], 8, bold=bool(head), color=color)
        for x, text in zip(reversed(rights), reversed(labels[1:]), strict=False):
            p.text(x, y + 4.5, text, 8, bold=bool(head), color=color, align="right")
        p.rule(x0, x1, y, INK, 0.6)
    for n, (left, amount) in enumerate(parsed):
        last = bold or (total_last and n == len(parsed) - 1 and len(parsed) > 1)
        lines = p.wrap(left[0], first_width, 9, bold=last, data=True)
        y -= 14
        for k, line in enumerate(lines):
            p.text(x0 + 6, y - k * 11.5, line, 9, bold=last, data=True)
        for x, text in zip(rights[len(rights) - len(left) :], left[1:], strict=False):
            p.text(x, y, text, 9, bold=last, align="right", data=True)
        p.text(rights[-1], y, amount, 9, bold=last, align="right", data=True)
        y -= (len(lines) - 1) * 11.5 + 5
        p.rule(x0, x1, y, INK if last else HAIR, 0.6 if last else 0.5)
    p.box(x0, y, x1 - x0, top - y, stroke=HAIR)
    return y


def usage_statement(rows: list[str], total: int | None, look: str | None = None) -> Pen:
    """A campus facility's recharge statement, as its billing system prints it."""
    b = blocks(rows)
    p = Pen(f"Usage statement {value_of(rows, 'Statement number')}", SANS, total)
    p.typed = True
    x0, x1 = 42.0, W - 42
    p.furniture = page_footer(x1)
    owner, *unit = b[0]
    y = report_head(p, x0, x1, owner, b[1][0]) - 18
    for n, row in enumerate(unit):
        p.text(x0, y, row.strip(), 11 if n == 0 else 9, bold=n == 0, color=INK if n == 0 else MUTE)
        y -= 13
    report_title(p, x1, b[1][0])
    y = field_grid(p, x0, x1, y - 2, b[2])
    y = amount_table(p, x0, x1, y - 14, cells(b[3][0]), b[3][1:], total_last=False)
    y = amount_table(p, x0, x1, y, None, b[4], bold=True)
    for row in b[5:]:
        y = p.stack(x0, y - 16, row, x1 - x0, 7.5, color=MUTE)
    return p


def expense_report(rows: list[str], total: int | None, look: str | None = None) -> Pen:
    """A travel expense report, as the expense system prints it: fields in a grid, a
    table of expenses, the dates it was submitted and approved."""
    b = blocks(rows)
    p = Pen(f"Expense report {value_of(rows, 'Report number')}", SANS, total)
    p.typed = True
    x0, x1 = 42.0, W - 42
    p.furniture = page_footer(x1)
    y = report_head(p, x0, x1, b[0][0], b[0][1]) - 12
    report_title(p, x1, b[0][1])
    y = field_grid(p, x0, x1, y, b[1])
    y = field_grid(p, x0, x1, y - 8, b[2])
    y = section_strip(p, x0, x1, y - 14, b[3][0])
    y = amount_table(p, x0, x1, y, None, b[3][1:], furniture=("Description", "Amount"))
    for group in b[4:-1]:
        y = p.stack(x0, y - 16, group, x1 - x0, 8.5)
    field_grid(p, x0, x1, y - 6, b[-1])
    return p


def effort_report(rows: list[str], total: int | None, look: str | None = None) -> Pen:
    """A certified effort report, as the payroll system prints it: the employee, the
    effort by award, the salary charged, the certification."""
    b = blocks(rows)
    p = Pen(f"Certified effort report, {value_of(rows, 'Employee')}", SANS, total)
    p.typed = True
    x0, x1 = 42.0, W - 42
    p.furniture = page_footer(x1)
    y = report_head(p, x0, x1, b[0][0], b[0][1]) - 12
    report_title(p, x1, b[0][1])
    y = field_grid(p, x0, x1, y, b[1])
    y = section_strip(p, x0, x1, y - 14, b[2][0])
    # The effort table. An award and its share are two rows of the text, because the
    # award's name is long; they're drawn on one baseline, the share in its column.
    head, *body = b[3]
    share_x = x1 - 110
    top = y
    y -= 16
    for x, text in zip((x0 + 6, share_x), cells(head), strict=True):
        p.text(x, y + 4.5, text, 8, bold=True)
    p.rule(x0, x1, y, INK, 0.6)
    first = y  # the baseline of the award's name, where its share goes too
    for n, row in enumerate(body):
        parts = cells(row)
        if row.startswith(" ") and len(parts) == 1:
            p.text(share_x, first, parts[0], 9)
            continue
        if n:
            y -= 5
            p.rule(x0, x1, y)
        y -= 14
        first = y
        if len(parts) == 2:
            p.text(x0 + 6, y, parts[0], 9, bold=True)
            p.text(share_x, y, parts[1], 9, bold=True)
        else:
            lines = p.wrap(row.strip(), share_x - x0 - 18, 9)
            for k, line in enumerate(lines):
                p.text(x0 + 6, y - k * 11.5, line, 9)
            y -= (len(lines) - 1) * 11.5
    y -= 5
    p.box(x0, y, x1 - x0, top - y, stroke=HAIR)
    y = section_strip(p, x0, x1, y - 14, b[4][0])
    y = amount_table(p, x0, x0 + 300, y, None, b[4][1:], furniture=("Month", "Salary"))
    y = section_strip(p, x0, x1, y - 14, b[5][0])
    p.y = y - 14
    p.para(x0 + 6, x1 - x0 - 12, " ".join(r.strip() for r in b[5][1:]), 9, 12)
    for group in b[6:]:
        p.y = field_grid(p, x0, x1, p.y - 2, group) - 8
    return p


# ------------------------------------------------------------------ a hotel folio


def folio(rows: list[str], total: int | None, look: str | None = None) -> Pen:
    """A hotel's guest folio: the hotel's name centered, a dated table of charges, the balance."""
    b = blocks(rows)
    p = Pen(f"Folio {value_of(rows, 'Folio number')}", SERIF, total)
    x0, x1 = 72.0, W - 72
    cx = W / 2
    hotel, *where = b[0]
    y = p.wordmark(x0, H - 64, hotel, 15, x1 - x0, align="center")
    y = p.stack(x0, y + 3, where, x1 - x0, 9, color=MUTE, align="center")
    p.rule(x0, x1, y + 2, INK, 0.8)
    y -= 18
    p.text(x0, y, b[1][0], 11, bold=True)
    p.page_number(x1, y)
    y -= 20
    # The stay's fields, two to a column.
    per = (len(b[2]) + 1) // 2
    for i, row in enumerate(b[2]):
        col, line = divmod(i, per)
        p.field(x0 + col * 250, y - line * 14, row, 9.5)
    y -= per * 14 + 12
    # The charges: a date, what it was, and the amount.
    widest = max(len(cells(r)) for r in b[3])
    cols = (x0 + 6, x0 + 150)
    p.rule(x0, x1, y + 12, INK, 0.8)
    furniture = ("Date", "Description", "Amount") if widest == 3 else ("Description", "Amount")
    for x, text in zip(cols, furniture[:-1], strict=False):
        p.text(x, y, text, 8.5, bold=True, color=MUTE)
    p.text(x1 - 6, y, furniture[-1], 8.5, bold=True, color=MUTE, align="right")
    p.rule(x0, x1, y - 5, INK, 0.5)
    y -= 4
    for row in b[3]:
        left, amount = amount_row(row)
        y -= 15
        for x, text in zip(cols, left, strict=False):
            p.text(x, y, text, 9.5)
        p.text(x1 - 6, y, amount, 9.5, align="right")
        p.rule(x0, x1, y - 4.5)
    y -= 12
    for n, row in enumerate(b[4]):
        left, amount = amount_row(row)
        last = n == len(b[4]) - 1
        y -= 15
        if last:
            p.rule(x1 - 250, x1, y + 11, INK, 0.8)
        p.text(x1 - 244, y, " ".join(left), 9.5, bold=last)
        p.text(x1 - 6, y, amount, 9.5, bold=last, align="right")
    for group in b[5:]:
        y = p.stack(x0 + 6, y - 22, group, x1 - x0, 9.5, fields=True)
    p.rule(x0, x1, 70)
    p.text(cx, 58, "Thank you for staying with us.", 8.5, italic=True, color=MUTE, align="center")
    return p


# ------------------------------------------------------------------ letters and memos


def letterhead(p: Pen, x0: float, x1: float, rows: list[str]) -> float:
    """An organization's name in type, its unit and address under it, over a thin rule.

    Returns the rule's height on the page."""
    y = p.wordmark(x0, H - 66, rows[0].strip(), 13, x1 - x0)
    y = p.stack(x0, y + 2, rows[1:], x1 - x0, 9, 11.5, color=MUTE)
    p.rule(x0, x1, y + 3, INK, 0.6)
    return y + 3


def letter_blocks(p: Pen, x0: float, x1: float, groups: list[list[str]], size: float) -> None:
    """A letter's body from the cursor down: paragraphs wrapped, every other row on its own line."""
    lead = size * 1.36
    # The closing ("Sincerely,") is the last row that stands alone and ends in a comma.
    # A letter leaves room under it for the signature.
    alone = [n for n, group in enumerate(groups) if len(group) == 1 and group[0].endswith(",")]
    closing = alone[-1] if len(alone) > 1 else None
    for n, group in enumerate(groups):
        if is_prose(group):
            p.para(x0, x1 - x0, " ".join(r.strip() for r in group), size, lead)
        else:
            for row in group:
                # A row too long for the measure wraps, as a long project title does.
                indent = 16 if row.startswith(" ") else 0
                p.y = p.stack(x0 + indent, p.y, [row], x1 - x0 - indent, size, lead, fields=True)
        p.y -= lead * 0.72 + (SIGNATURE_ROOM if n == closing else 0)


def appointment_letter(rows: list[str], total: int | None, look: str | None = None) -> Pen:
    """A letter on the department's letterhead."""
    b = blocks(rows)
    subject = next((r for r in rows if r.startswith("Re: ")), "Re: Letter")
    p = Pen(subject.removeprefix("Re: "), SERIF, total)
    x0, x1 = 90.0, W - 90
    p.y = letterhead(p, x0, x1, b[0]) - 36
    letter_blocks(p, x0, x1, b[1:], 10.5)
    return p


def expiration_notice(rows: list[str], total: int | None, look: str | None = None) -> Pen:
    """The accounting office's memo: its letterhead, a title, the award's fields, a paragraph."""
    b = blocks(rows)
    p = Pen(b[1][0].title(), SERIF, total)
    x0, x1 = 90.0, W - 90
    p.furniture = marked_footer("any university", 50)
    y = letterhead(p, x0, x1, b[0]) - 40
    p.text(x0, y, b[1][0], 13, bold=True)
    y -= 26
    tab = max(p.width(r.partition(": ")[0] + ":", 10.5, bold=True) for r in b[2]) + 12
    for row in b[2]:
        # The label, then its value in one column, wrapped where it's long.
        label, _, value = row.strip().partition(": ")
        p.text(x0, y, label + ":", 10.5, bold=True)
        for line in p.wrap(value, x1 - x0 - tab, 10.5):
            p.text(x0 + tab, y, line, 10.5)
            y -= 15
    p.rule(x0, x1, y + 4, INK, 0.6)
    p.y = y - 18
    letter_blocks(p, x0, x1, b[3:], 10.5)
    return p


# ------------------------------------------------------------------ a cost transfer form


def cost_transfer(rows: list[str], total: int | None, look: str | None = None) -> Pen:
    """A filled form: the office's name, the form's title, boxed fields, and each
    question over its boxed answer."""
    b = blocks(rows)
    p = Pen(f"Cost transfer justification {value_of(rows, 'Transfer number')}", SANS, total)
    x0, x1 = 54.0, W - 54
    p.furniture = page_footer(x1)
    owner, *title = b[0]
    y = p.wordmark(x0, H - 58, owner, 9, x1 - x0)
    for row in title:
        y -= 8
        p.text(x0, y, row.strip(), 14, bold=True)
    p.rule(x0, x1, y - 8, INK, 1.2)
    y -= 20
    # Short fields side by side where they fit, a long one across the form.
    short = [r for r in b[1] if p.width(r.strip(), 9) + 6 <= (x1 - x0) / 3 - 12]
    step = (x1 - x0) / max(len(short), 1)
    for i, row in enumerate(short):
        grid_cell(p, x0 + i * step, y, step, [row], lead=14)
    y -= 22 if short else 0
    for row in b[1]:
        if row not in short:
            y = grid_cell(p, x0, y, x1 - x0, [row], lead=14)
    y -= 20
    # Each question starts a row of the text; its answer runs on to the next question.
    answers: list[list[str]] = []
    for row in b[2]:
        if not answers or re.match(r"^[A-Z][^:.,]{8,60}: ", row):
            answers.append([row])
        else:
            answers[-1].append(row)
    for item in answers:
        question, sep, first = item[0].partition(": ")
        answer = " ".join([first, *item[1:]])
        lines = p.wrap(answer, x1 - x0 - 16, 9.5)
        p.text(x0, y, question + (":" if sep else ""), 8, color=MUTE)
        height = 13 * len(lines) + 12
        p.box(x0, y - 6 - height, x1 - x0, height, stroke=HAIR)
        p.y = y - 21
        p.para(x0 + 8, x1 - x0 - 16, answer, 9.5, 13)
        y -= height + 26
    for group in b[3:]:
        y = field_grid(p, x0, x1, y + 4, group) - 12
    return p


# ------------------------------------------------------------------ a federal rate agreement


def rate_agreement(rows: list[str], total: int | None, look: str | None = None) -> Pen:
    """A rate agreement laid out like a federal one: a serif page, an underlined rate table."""
    b = blocks(rows)
    p = Pen(b[1][0].title(), SERIF, total)
    x0, x1 = 72.0, W - 72
    size, lead = 10.0, 13.0
    p.top, p.bottom = H - 72, 84
    p.furniture = marked_footer("any federal agency", 50)
    # The organization on the left; the agreement's date and filing reference on the right.
    left = [r for r in b[0] if not re.match(r"^(Date|FILING REF\.): ", r)]
    right = [r for r in b[0] if r not in left]
    y = H - 72
    under = p.stack(x0, y, left, 190, size, lead)
    y = min(under, p.stack(x1 - 270, y, right, 270, size, lead, align="right")) - 22
    p.rule(x0, x1, y + 16, INK, 1.1)
    p.text(W / 2, y, b[1][0], 12, bold=True, align="center")
    p.rule(x0, x1, y - 8, INK, 1.1)
    p.y = y - 30
    cols = (x0, x0 + 58, x0 + 132, x0 + 206, x0 + 272, x0 + 336)
    for group in b[2:-1]:
        first = group[0]
        if first.startswith("TYPE "):
            for x, text in zip(cols, cells(first), strict=True):
                p.text(x, p.y, text, 9, bold=True)
            p.rule(x0, x1, p.y - 4, INK, 0.7)
            p.y -= lead + 4
            for row in group[1:]:
                parts = cells(row)
                p.need(lead)
                if row.startswith(" "):
                    # A row that runs on from the one above, under its last cell.
                    p.text(cols[3], p.y, " ".join(parts), size)
                else:
                    for x, text in zip(cols, parts, strict=False):
                        p.text(x, p.y, text, size)
                p.y -= lead + 1
        elif first.startswith("SECTION "):
            p.need(5 * lead)
            p.text(x0, p.y, first, 10.5, bold=True)
            p.y -= lead
        elif (first.endswith(":") and first.isupper()) or first.startswith("** "):
            p.need(3 * lead)
            p.text(x0, p.y, first, size, bold=True)
            p.y -= lead
            p.para(x0, x1 - x0, " ".join(group[1:]), size, lead)
        elif is_prose(group):
            p.para(x0, x1 - x0, " ".join(group), size, lead)
        else:
            p.need(len(group) * (lead + 3) + 12)
            p.rule(x0, x1, p.y + lead, INK, 0.5)
            p.y -= 6
            for row in group:
                p.y = p.stack(x0, p.y, [row], x1 - x0, size, lead + 3, fields=True)
        p.y -= lead * 0.7
    # The agreement names itself again at its foot, as each page of a real one does.
    p.need(2 * lead)
    p.rule(x0, x1, p.y + lead, INK, 0.5)
    step = (x1 - x0) / len(b[-1])
    for i, row in enumerate(b[-1]):
        p.text(x0 + i * step, p.y - 2, row.strip(), 9)
    return p


# ------------------------------------------------------------------ rendering and reading back

Layout = Callable[[list[str], int | None, str | None], Pen]
LAYOUTS: list[tuple[str, Layout]] = [
    ("award_letter", notice),
    ("notice_0", notice),
    ("extension_notice", notice),
    ("notice_of_expiration", expiration_notice),
    ("invoice_", invoice),
    ("scan_invoice_", invoice),
    ("usage_statement_", usage_statement),
    ("hotel_folio_", folio),
    ("expense_report_", expense_report),
    ("effort_report_", effort_report),
    ("appointment_letter_", appointment_letter),
    ("cost_transfer_justification_", cost_transfer),
    ("rate_agreement_", rate_agreement),
]


def render(
    name: str, text: str, look: str | None = None
) -> tuple[bytes, list[tuple[int, int] | None]]:
    """The file's typeset PDF, and the pages each row of `text` is on (see `locate`).

    `look` picks among a kind's looks: a vendor's own invoice look."""
    layout = next((fn for prefix, fn in LAYOUTS if name.startswith(prefix)), None)
    if layout is None:
        raise ValueError(f"{name}: no layout draws this kind of document")
    rows = text.rstrip("\n").split("\n")
    try:
        # Once to count the pages, then again with the count for "Page 1 of 2".
        pages = layout(rows, None, look).page
        data = layout(rows, pages, look).done()
        return data, locate(data, text)
    except ValueError as error:
        raise ValueError(f"{name}: {error}") from error


def page_texts(data: bytes) -> list[str]:
    """Each page's text as pdfium reads it, the reader the app's quote finder uses."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(data)
    try:
        out = []
        for i in range(len(doc)):
            page = doc[i]
            textpage = page.get_textpage()
            out.append(textpage.get_text_range())
            textpage.close()
            page.close()
        return out
    finally:
        doc.close()


Word = tuple[int, str, tuple[float, float, float, float]]


def page_words(data: bytes) -> list[Word]:
    """Every word in the PDF, in reading order: its page (from 1), the word, and its box
    as (left, top, right, bottom) in fractions of the page, from the page's top left.

    A word is a run of characters with no whitespace, as pdfium reads the page."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    out: list[Word] = []
    doc = pdfium.PdfDocument(data)
    try:
        for number in range(1, len(doc) + 1):
            page = doc[number - 1]
            width, height = page.get_size()
            textpage = page.get_textpage()
            word, box = "", None
            for i in range(textpage.count_chars() + 1):
                ch = (
                    chr(pdfium_c.FPDFText_GetUnicode(textpage.raw, i))
                    if i < textpage.count_chars()
                    else " "
                )
                if ch.isspace() or ch == "\x00":
                    if word and box is not None:
                        left, bottom, right, top = box
                        frac = (left / width, 1 - top / height, right / width, 1 - bottom / height)
                        out.append((number, word, frac))
                    word, box = "", None
                    continue
                left, bottom, right, top = textpage.get_charbox(i, loose=False)
                word += ch
                box = (
                    (left, bottom, right, top)
                    if box is None
                    else (
                        min(box[0], left),
                        min(box[1], bottom),
                        max(box[2], right),
                        max(box[3], top),
                    )
                )
            textpage.close()
            page.close()
        return out
    finally:
        doc.close()


def row_words(words: list[Word], text: str) -> list[tuple[int, int] | None]:
    """For each row of `text`, the first and last of `words` that make it up.

    A blank row gets None. A row's words are the page's words, one for one, and each
    row is looked for after the one before it, so the page has to give the rows in the
    text's own order. A row missing from the page raises ValueError.
    """
    printed = [word for _, word, _ in words]
    out: list[tuple[int, int] | None] = []
    cursor = 0
    for row in text.split("\n"):
        want = row.split()
        if not want:
            out.append(None)
            continue
        found = next(
            (
                i
                for i in range(cursor, len(printed) - len(want) + 1)
                if printed[i : i + len(want)] == want
            ),
            None,
        )
        if found is None:
            raise ValueError(f"the PDF doesn't give this row, in order: {' '.join(want)!r}")
        cursor = found + len(want)
        out.append((found, cursor - 1))
    return out


def locate(data: bytes, text: str) -> list[tuple[int, int] | None]:
    """For each row of `text`, the first and last page it's on, counted from 1.

    A blank row gets None. Rows are compared word by word, with runs of whitespace as
    one space, as the quote finder compares them (see `row_words`). A row missing from
    the page raises ValueError.
    """
    words = page_words(data)
    return [
        None if found is None else (words[found[0]][0], words[found[1]][0])
        for found in row_words(words, text)
    ]
