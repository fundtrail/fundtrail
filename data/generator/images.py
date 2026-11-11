"""The samples' images: receipt photos and a scanned invoice, drawn by realphoto.py.

An image's bytes depend on the machine's fonts, so a build keeps the images already
on disk and draws them again only when build.py is run with `--photos` (which needs
Pillow). Drawing an image also gives the box of every string printed on it. The
stand-in agent's records cite a value on an image by the box of the string that
holds it, so the boxes are kept beside the generator, in `image_boxes.json`, and a
build that keeps an image reads its boxes from there.

An image's `Doc.text` is the strings drawn on it, one per line, and `Doc.boxes`
holds each line's box.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from model import Doc, Grant

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parent / "samples"
BOXES_FILE = HERE / "image_boxes.json"
Box = tuple[float, float, float, float]

# build.py turns this on when it's run with --photos.
REDRAW = False
# The boxes of every image drawn in this run, by file name, for build.py to save.
DRAWN: dict[str, list[tuple[str, Box]]] = {}


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
class Stamp:
    """An office's received stamp on a scan: a word, a date line and the office's name,
    at a place given in fractions of the page."""

    word: str
    date: str
    office: str
    at: tuple[float, float]


@dataclass
class Image:
    data: bytes
    boxes: list[tuple[str, Box]]  # each drawn string and its box, in the order drawn


def kept(name: str) -> Image:
    """The image on disk and its saved boxes."""
    path = next((p for p in sorted(SAMPLES.glob(f"*/{name}")) if p.is_file()), None)
    saved = json.loads(BOXES_FILE.read_text(encoding="utf-8")) if BOXES_FILE.is_file() else {}
    if path is None or name not in saved:
        raise SystemExit(f"{name} or its boxes aren't on disk: run build.py with --photos")
    return Image(path.read_bytes(), [(text, tuple(box)) for text, box in saved[name]])


def drawn(name: str, data: bytes, boxes: dict[str, Box]) -> Image:
    listed = [(text, box) for text, box in boxes.items()]
    DRAWN[name] = listed
    return Image(data, listed)


def receipt(name: str, rows: list[Row], *, seed: int) -> Image:
    """A phone photo of a thermal paper receipt printed with `rows`."""
    if not REDRAW:
        return kept(name)
    import realphoto

    printed = [realphoto.Row(r.left, r.right, r.style, r.align, r.rule) for r in rows]
    return drawn(name, *realphoto.receipt_photo(printed, seed=seed))


def invoice_scan(name: str, text: str, *, seed: int, stamp: Stamp) -> Image:
    """A flatbed scan of the invoice whose text is `text`, printed on plain paper, with
    an office's received stamp, a tick and a pen scrawl. The marks state nothing."""
    if not REDRAW:
        return kept(name)
    import realphoto

    page = invoice_page(text)
    data, boxes = realphoto.scanned_page(
        page,
        seed=seed,
        stamp=realphoto.Stamp(stamp.word, stamp.date, stamp.office, at=stamp.at),
        initials_at=(0.47, 0.645),
        check_at=(0.615, 0.402),
    )
    return drawn(name, data, boxes)


def invoice_page(text: str):
    """The invoice as its vendor prints it: every part of it from `text`."""
    import realphoto
    from realphoto import MONO, SANS, SANS_BOLD, SERIF, SERIF_BOLD
    from typeset import Bill

    b = Bill(text.rstrip("\n").split("\n"))
    p = realphoto.Page()
    w, h = p.size
    x0, x1 = 96, w - 96
    # The vendor's name, a little smaller if it's long, beside the title.
    size = 44
    while size > 28 and realphoto.font(SERIF_BOLD, size).getlength(b.vendor) > x1 - x0 - 230:
        size -= 2
    p.text((x0, 100), b.vendor, SERIF_BOLD, size)
    for i, row in enumerate(b.contact):
        p.text((x0, 152 + i * 26), row, SERIF, 21)
    p.text((x1, 100), b.heading, SANS_BOLD, 40, anchor="ra")
    p.line([(x0, 214), (x1, 214)], 3)
    # The invoice's own numbers and its terms, boxed at the right.
    numbers = [*b.details, *b.terms]
    bx = 790
    p.rect((bx, 236, x1, 248 + 27 * len(numbers)), 2)
    for i, row in enumerate(numbers):
        p.text((bx + 12, 244 + i * 27), row, SANS, 20)
    p.text((x0, 240), b.bill_to, SANS_BOLD, 19)
    for i, row in enumerate(b.bill_lines):
        p.text((x0, 268 + i * 27), row, SANS, 20)
    y = max(268 + 27 * len(b.bill_lines), 260 + 27 * len(numbers)) + 14
    for row in b.after_bill:
        p.text((x0, y), row, SANS, 20)
        y += 27
    # The items: a column for each cell of the header, the description taking the room.
    top = y + 24
    wide = len(b.head) == 7
    if wide:
        places = [(x0 + 10, "la"), (x0 + 62, "la"), (x0 + 210, "la"), (800, "ra"), (836, "la")]
    else:
        places = [(x0 + 10, "la"), (x0 + 62, "la"), (840, "ra")]
    places += [(1010, "ra"), (x1 - 10, "ra")]
    p.rect((x0, top, x1, top + 34), 2, fill=226)
    for (x, anchor), label in zip(places, b.head, strict=True):
        p.text((x, top + 7), label, SANS_BOLD, 18, anchor=anchor)
    y = top + 46
    for item in b.items:
        for n, ((x, anchor), cell) in enumerate(zip(places, item, strict=True)):
            # A space after the line's amount keeps it apart from a total of the same sum.
            last = n == len(item) - 1
            face = MONO if wide and n == 1 else SANS
            p.text(
                (x, y),
                cell + (" " if last else ""),
                face,
                19 if face is MONO else 20,
                anchor=anchor,
            )
        y += 34
    bottom = y + 22
    p.rect((x0, top, x1, bottom), 2)
    y = bottom + 26
    for n, (label, amount) in enumerate(b.totals):
        last = n == len(b.totals) - 1
        face, size = (SANS_BOLD, 22) if last else (SANS, 20)
        p.text((860, y), " ".join(label), face, size)
        p.text((x1 - 10, y), amount, face, size, anchor="ra")
        y += 32
    p.line([(850, y - 38), (x1, y - 38)], 2)
    p.text((x0, h - 150), b.remit(), SANS, 17, fill=60)
    p.text((x0, h - 124), "Please include the invoice number with your payment.", SANS, 17, fill=60)
    p.text((x1, h - 124), "Page 1 of 1", SANS, 17, anchor="ra", fill=60)
    return p


def put_image(
    g: Grant, name: str, image: Image, arrives: datetime, source: str, **fields: str | None
) -> Doc:
    """Adds an image to the grant: its text is the strings drawn on it, one per line."""
    text = "\n".join(text.strip() for text, _ in image.boxes)
    doc = g.doc(name, image.data, arrives, source, text=text, **fields)
    doc.boxes = [box for _, box in image.boxes]
    return doc
