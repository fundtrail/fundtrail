"""The samples' pictures of paper, drawn by realphoto.py.

Two kinds:

- A receipt printed line by line and photographed with a phone (`receipt`). Its
  `Doc.text` is the strings printed on it, one per row.
- A typeset PDF page as paper (`picture`): scanned, as a JPEG or as a one-page PDF
  with no text layer, or photographed with a phone. Any document typeset.py draws
  can arrive this way. Its `Doc.text` stays the document's text.

Either way `Doc.words` holds, for each row of the text, the row's words and each
one's box on the picture. The stand-in agent's records cite a value by the box
around its own words, so the box holds the value and nothing else.

A picture's bytes depend on the machine's fonts, so a build keeps the pictures
already on disk and draws them again only when build.py is run with `--photos`
(which needs Pillow). The boxes are kept beside the generator, in
`image_boxes.json`, and a build that keeps a picture reads its boxes from there.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from model import Doc, Grant
from render import PACIFIC

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parent / "samples"
BOXES_FILE = HERE / "image_boxes.json"
Box = tuple[float, float, float, float]
# For each row of a picture's text, its words and their boxes, and None for a blank row.
Words = list[list[tuple[str, Box]] | None]

# build.py turns this on when it's run with --photos.
REDRAW = False
# The word boxes of every picture drawn in this run, by file name, for build.py to save.
DRAWN: dict[str, Words] = {}
# A scan is 150 dots per inch: a US Letter page is 1275 by 1650 pixels.
SCAN_DPI = 150


@dataclass
class Row:
    """One printed line of a receipt. `right` puts a second string at the right edge (a
    label and its amount). `style`: "big", "normal" or "small"; `align`: "center" or
    "left"; `rule` draws a dotted rule in place of text."""

    left: str = ""
    right: str = ""
    style: str = "normal"
    align: str = "left"
    rule: bool = False


@dataclass
class Scan:
    """A typeset page scanned on a flatbed: turned `turn` degrees, grainy, folded and
    stapled. `stamp` adds the office's received stamp and a pen scrawl beside it;
    `tick` a pen tick by the total; `sign` a pen scrawl over the signer's printed
    name. The stamp's date is `received`, or the day the file arrives. The marks
    state nothing. A `.pdf` name gives a one-page PDF with no text layer, and any
    other name the scan as a JPEG."""

    seed: int
    turn: float
    stamp: bool = True
    tick: bool = True
    sign: bool = False
    office: str = "EARTH & OCEAN SCIENCES"
    received: date | None = None


@dataclass
class Photo:
    """A typeset page printed and photographed with a phone, lying on a desk, turned
    `turn` degrees."""

    seed: int
    turn: float = 1.5


@dataclass
class Image:
    data: bytes
    words: Words


def kept(name: str) -> Image:
    """The picture on disk and its saved boxes."""
    path = next((p for p in sorted(SAMPLES.glob(f"*/{name}")) if p.is_file()), None)
    saved = json.loads(BOXES_FILE.read_text(encoding="utf-8")) if BOXES_FILE.is_file() else {}
    if path is None or name not in saved:
        raise SystemExit(f"{name} or its boxes aren't on disk: run build.py with --photos")
    rows = [None if r is None else [(w, tuple(b)) for w, b in r] for r in saved[name]]
    return Image(path.read_bytes(), rows)


def save_boxes() -> None:
    """Writes the word boxes of the pictures drawn in this run, a row to a line."""
    out = ["{"]
    names = sorted(DRAWN)
    for n, name in enumerate(names):
        lines = ",\n".join("   " + json.dumps(row) for row in DRAWN[name])
        out.append(f"  {json.dumps(name)}: [\n{lines}\n  ]" + ("," if n < len(names) - 1 else ""))
    out.append("}")
    BOXES_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def receipt(name: str, rows: list[Row], *, seed: int, turn: float | None = None) -> Image:
    """A phone photo of a thermal paper receipt printed with `rows`, turned `turn`
    degrees on the desk, or by an angle of the seed's choosing.

    Its text is the strings printed on it, a row each: a line's left string, then
    its right one."""
    if not REDRAW:
        return kept(name)
    import realphoto

    printed = [realphoto.Row(r.left, r.right, r.style, r.align, r.rule) for r in rows]
    data, boxes = realphoto.receipt_photo(printed, seed=seed, turn=turn)
    if any(box is None for _, box in boxes):
        raise ValueError(f"{name}: a word fell off the picture")
    strings = [s for r in rows if not r.rule for s in (r.left, r.right) if s.strip()]
    per_row: Words = []
    at = 0
    for string in strings:
        count = len(string.split())
        per_row.append([(word, box) for word, box in boxes[at : at + count]])
        at += count
    DRAWN[name] = per_row
    return Image(data, per_row)


def put_image(
    g: Grant, name: str, image: Image, arrives: datetime, source: str, **fields: str | None
) -> Doc:
    """Adds a receipt's photo to the grant: its text is the strings printed on it."""
    text = "\n".join(" ".join(word for word, _ in row or []) for row in image.words)
    doc = g.doc(name, image.data, arrives, source, text=text, **fields)
    doc.words = image.words
    return doc


# ---------------------------------------------------------------- pictures of a typeset page

# How much of the page each pen mark and the stamp take, as (width, height) in
# fractions of it, from realphoto.py's drawings on a 1275 by 1650 page.
STAMP_AREA = (0.345, 0.12)
SCRAWL_AREA = (0.1725, 0.0667)
SCRAWL_INK = (0.012, 0.010, 0.167, 0.058)  # where the pen's line is, within its area
TICK_AREA = (0.055, 0.0364)


def picture(name: str, pdf: bytes, text: str, how: Scan | Photo, arrives: datetime) -> Image:
    """The typeset page `pdf`, whose text is `text`, as paper: scanned, or photographed.

    A scan named `.pdf` comes back as a one-page PDF with no text layer; any other
    scan, and a photo, as a JPEG. Either way `words` holds, for each row of `text`,
    the row's words and where each one is on the picture."""
    if not REDRAW:
        return kept(name)
    import realphoto
    import typeset

    words = typeset.page_words(pdf)
    if any(page != 1 for page, _, _ in words):
        raise ValueError(f"{name}: only a one-page document can be scanned or photographed")
    rows = typeset.row_words(words, text)
    sheet = printed_sheet(pdf, words)
    if isinstance(how, Photo):
        data, boxes = realphoto.photo_of_page(sheet, seed=how.seed, turn=how.turn)
    else:
        marks = pen_marks(name, how, words, rows, text, arrives)
        jpeg, boxes = realphoto.scanned_page(sheet, seed=how.seed, turn=how.turn, **marks)
        data = image_pdf(jpeg, sheet.size, name) if name.endswith(".pdf") else jpeg
    if any(box is None for _, box in boxes):
        raise ValueError(f"{name}: a word fell off the picture")
    per_row: Words = [
        None if r is None else [(words[i][1], boxes[i][1]) for i in range(r[0], r[1] + 1)]
        for r in rows
    ]
    DRAWN[name] = per_row
    return Image(data, per_row)


def printed_sheet(pdf: bytes, words: list):
    """The PDF's first page as a printed sheet at a scan's resolution, in grey, with
    each word's place on it."""
    import pypdfium2 as pdfium
    import realphoto

    doc = pdfium.PdfDocument(pdf)
    try:
        page = doc[0]
        image = page.render(scale=SCAN_DPI / 72, grayscale=True).to_pil()
        page.close()
    finally:
        doc.close()
    w, h = image.size
    strings = [
        (word, (int(left * w) - 2, int(top * h) - 3, int(right * w) + 2, int(bottom * h) + 3))
        for _, word, (left, top, right, bottom) in words
    ]
    return realphoto.printed_page(image, strings)


def clear(area: tuple[float, float, float, float], words: list) -> bool:
    """Whether no word of the page lies in `area` (left, top, right, bottom)."""
    left, top, right, bottom = area
    return not any(
        w_left < right and w_right > left and w_top < bottom and w_bottom > top
        for _, _, (w_left, w_top, w_right, w_bottom) in words
    )


def fold_near(target: float, words: list) -> float:
    """The height nearest `target` where a fold line crosses no word, with a little room
    on each side for the line's own slant."""
    for step in range(0, 150):
        for at in (target - step * 0.002, target + step * 0.002):
            if clear((0.0, at - 0.010, 1.0, at + 0.012), words):
                return round(at, 4)
    raise ValueError("no empty band for a fold")


def pen_marks(name: str, how: Scan, words: list, rows: list, text: str, arrives: datetime) -> dict:
    """Where a scan's stamp and pen marks go: on empty paper, covering no word.

    The stamp goes in the widest empty band of the page, the scrawl beside it, the
    tick to the left of the last total, and a signature over the signer's printed
    name, which is the row after the letter's closing."""
    import realphoto

    # The sheet was folded in three. Each fold falls between two rows of print, as near
    # a third of the way down as the print leaves room, so no row is struck through.
    marks: dict = {"folds": tuple(fold_near(third, words) for third in (0.372, 0.694))}
    lines = text.split("\n")
    if how.stamp:
        # The empty bands between the rows of print, top to bottom.
        spans = sorted((top, bottom) for _, _, (_, top, _, bottom) in words)
        gaps, edge = [], 0.08
        for top, bottom in spans:
            if top > edge:
                gaps.append((top - edge, edge))
            edge = max(edge, bottom)
        room, start = max(gaps)
        if room < STAMP_AREA[1] + 0.03:
            raise ValueError(f"{name}: no empty band is tall enough for the stamp")
        at = (0.10, start + min(0.05, (room - STAMP_AREA[1]) / 2))
        scrawl = (0.50, at[1] + 0.035)
        stamped = how.received or arrives.astimezone(PACIFIC)
        marks["stamp"] = realphoto.Stamp(
            "RECEIVED", f"{stamped:%b %d %Y}".upper(), how.office, at=at
        )
        marks["initials_at"] = scrawl
        for mark, area in ((at, STAMP_AREA), (scrawl, SCRAWL_AREA)):
            if not clear((mark[0], mark[1], mark[0] + area[0], mark[1] + area[1]), words):
                raise ValueError(f"{name}: the stamp or the scrawl would cover print")
    if how.tick:
        totals = [r for r, line in zip(rows, lines, strict=True) if r and line.startswith("Total")]
        if not totals:
            raise ValueError(f"{name}: no total to tick")
        left, top, _, _ = words[totals[-1][0]][2]
        at = (left - 0.075, top - 0.014)
        if not clear((at[0], at[1], at[0] + TICK_AREA[0], at[1] + TICK_AREA[1]), words):
            raise ValueError(f"{name}: the tick would cover print")
        marks["check_at"] = at
    if how.sign:
        # The closing is the last row that stands alone and ends in a comma.
        alone = [
            i
            for i, line in enumerate(lines)
            if line.strip().endswith(",")
            and (i == 0 or not lines[i - 1].strip())
            and (i + 1 < len(lines) and not lines[i + 1].strip())
        ]
        signer = next((r for r in rows[alone[-1] + 1 :] if r), None) if alone else None
        if signer is None:
            raise ValueError(f"{name}: no signer's name to sign over")
        left, top, _, _ = words[signer[0]][2]
        at = (left - 0.012, top - SCRAWL_AREA[1] + 0.004)
        ink = (
            at[0] + SCRAWL_INK[0],
            at[1] + SCRAWL_INK[1],
            at[0] + SCRAWL_INK[2],
            at[1] + SCRAWL_INK[3],
        )
        if not clear(ink, words):
            raise ValueError(f"{name}: the signature would cover print")
        marks["initials_at"] = at
    return marks


def image_pdf(jpeg: bytes, size: tuple[int, int], title: str) -> bytes:
    """A one-page PDF holding a scan and nothing else: the JPEG as the whole page, at
    the scan's resolution, with no text layer."""
    width, height = size
    points = (width * 72 / SCAN_DPI, height * 72 / SCAN_DPI)
    draw = b"q %g 0 0 %g 0 0 cm /Im0 Do Q" % points
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %g %g] "
        b"/Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>" % points,
        b"<< /Length %d >>\nstream\n" % len(draw) + draw + b"\nendstream",
        b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
        b"/BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n"
        % (width, height, len(jpeg))
        + jpeg
        + b"\nendstream",
        b"<< /Title (Scan of %s) /Producer (FundTrail sample generator) >>" % title.encode("ascii"),
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 6 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)
