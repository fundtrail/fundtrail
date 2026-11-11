"""Photos and scans of paper documents, drawn with Pillow, with a box for every printed string.

Two pictures:

- `receipt_photo`: a thermal-paper receipt photographed with a phone on a desk.
- `scanned_page`: a printed page scanned on a flatbed, a little crooked, with an office's
  date stamp and pen marks.

Each returns the JPEG's bytes and `boxes`: for every string drawn, its box on the finished
image as (left, top, width, height) in fractions of the image, keyed by the string. The
stand-in agent's records cite a value on a photo by the box of the string that holds it, so
the box follows the paper through the turn, the perspective and the resize.

Dev-only, like photo.py: needs Pillow, and the look depends on the fonts on the machine.
"""

from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass, field

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

FONT_DIRS = (
    "/System/Library/Fonts/Supplemental/",
    "/System/Library/Fonts/",
    "/usr/share/fonts/truetype/dejavu/",
)
Box = tuple[float, float, float, float]


def font(names: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont:
    for name in names:
        for folder in FONT_DIRS:
            try:
                return ImageFont.truetype(folder + name, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


MONO = ("Courier New Bold.ttf", "DejaVuSansMono-Bold.ttf")
MONO_LIGHT = ("Courier New.ttf", "DejaVuSansMono.ttf")
SERIF = ("Times New Roman.ttf", "DejaVuSerif.ttf")
SERIF_BOLD = ("Times New Roman Bold.ttf", "DejaVuSerif-Bold.ttf")
SANS = ("Arial.ttf", "DejaVuSans.ttf")
SANS_BOLD = ("Arial Bold.ttf", "DejaVuSans-Bold.ttf")
NARROW_BOLD = ("Arial Narrow Bold.ttf", "DejaVuSansCondensed-Bold.ttf")


@dataclass
class Marks:
    """Records where each string was drawn, as an index image that rides through every
    transform the paper goes through."""

    size: tuple[int, int]
    texts: list[str] = field(default_factory=list)
    index: Image.Image | None = None

    def __post_init__(self) -> None:
        self.index = Image.new("L", self.size, 0)

    def add(self, text: str, box: tuple[int, int, int, int]) -> None:
        """Remember `text` at `box` (left, top, right, bottom). At most 250 strings."""
        if not text.strip() or text in self.texts:
            return
        self.texts.append(text)
        assert self.index is not None
        ImageDraw.Draw(self.index).rectangle(box, fill=len(self.texts))

    def boxes(self, moved: Image.Image) -> dict[str, Box]:
        """Each string's box on `moved`, the index image after the paper's transforms."""
        w, h = moved.size
        out: dict[str, Box] = {}
        for i, text in enumerate(self.texts, start=1):
            found = moved.point(lambda v, i=i: 255 if v == i else 0).getbbox()
            if found is None:
                continue
            left, top, right, bottom = found
            out[text] = (
                round(left / w, 4),
                round(top / h, 4),
                round((right - left) / w, 4),
                round((bottom - top) / h, 4),
            )
        return out


def perspective(src_quad, dst_quad) -> list[float]:
    """Coefficients for Image.transform: maps each output point back to the source."""
    rows = []
    for (x, y), (u, v) in zip(dst_quad, src_quad, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y, u])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y, v])
    n = 8
    for i in range(n):
        pivot = max(range(i, n), key=lambda r: abs(rows[r][i]))
        rows[i], rows[pivot] = rows[pivot], rows[i]
        p = rows[i][i]
        rows[i] = [value / p for value in rows[i]]
        for r in range(n):
            if r != i:
                f = rows[r][i]
                rows[r] = [a - f * b for a, b in zip(rows[r], rows[i], strict=True)]
    return [rows[i][8] for i in range(n)]


def _noise(size: tuple[int, int], sigma: float, seed: int) -> Image.Image:
    """Gaussian noise that is the same for the same seed (Image.effect_noise isn't seeded)."""
    rng = random.Random(seed)
    w, h = size
    data = bytes(max(0, min(255, int(rng.gauss(128, sigma)))) for _ in range(w * h))
    return Image.frombytes("L", size, data)


def _soft_noise(
    size: tuple[int, int], cells: tuple[int, int], sigma: float, seed: int
) -> Image.Image:
    return _noise(cells, sigma, seed).resize(size, Image.Resampling.BICUBIC)


# ------------------------------------------------------------------ thermal receipt


@dataclass
class Row:
    """One printed line. `right` puts a second string at the right edge (a label and its
    amount). `style`: "big", "normal" or "small"; `align`: "center" or "left"."""

    left: str = ""
    right: str = ""
    style: str = "normal"
    align: str = "left"
    rule: bool = False


def _thermal_paper(rows: list[Row], seed: int) -> tuple[Image.Image, Marks]:
    rng = random.Random(seed)
    # Drawn at a third of the size with no smoothing, then enlarged: a thermal head's dots.
    scale = 3
    pw = 232
    sizes = {"big": 19, "normal": 13, "small": 11}
    fonts = {
        "big": font(NARROW_BOLD, sizes["big"]),
        "normal": font(MONO, sizes["normal"]),
        "small": font(MONO_LIGHT, sizes["small"]),
    }
    step = {"big": 25, "normal": 17, "small": 14}
    margin = 14
    height = 34 + sum(8 if r.rule else step[r.style] for r in rows) + 60
    small = Image.new("L", (pw, height), 0)
    d = ImageDraw.Draw(small)
    d.fontmode = "1"
    marks = Marks((pw * scale, height * scale))
    y = 30
    for r in rows:
        if r.rule:
            for x in range(margin, pw - margin, 4):
                d.line([(x, y + 3), (x + 1, y + 3)], fill=255)
            y += 8
            continue
        f = fonts[r.style]
        if r.left:
            width = d.textlength(r.left, font=f)
            x = (pw - width) / 2 if r.align == "center" else margin
            d.text((x, y), r.left, font=f, fill=255)
            box = d.textbbox((x, y), r.left, font=f)
            marks.add(
                r.left,
                tuple(int(v * scale) for v in (box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2)),
            )
        if r.right:
            width = d.textlength(r.right, font=f)
            x = pw - margin - width
            d.text((x, y), r.right, font=f, fill=255)
            box = d.textbbox((x, y), r.right, font=f)
            marks.add(
                r.right,
                tuple(int(v * scale) for v in (box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2)),
            )
        y += step[r.style]
    size = (pw * scale, height * scale)
    ink = small.resize(size, Image.Resampling.NEAREST).filter(ImageFilter.GaussianBlur(1.1))
    ink = ink.point(lambda v: min(255, int(v * 1.35)))
    # The head prints lighter in vertical bands, and the print fades toward one end.
    bands = _noise((size[0] // 9, 1), 55, seed + 1).resize(size, Image.Resampling.BICUBIC)
    bands = bands.point(lambda v: 255 if v > 100 else 150 + v)
    fade = Image.linear_gradient("L").resize(size).point(lambda v: 190 + v * 65 // 255)
    speck = _noise((size[0] // 2, size[1] // 2), 40, seed + 2).resize(
        size, Image.Resampling.BILINEAR
    )
    speck = speck.point(lambda v: 255 if v > 78 else 120)
    ink = ImageChops.multiply(ImageChops.multiply(ImageChops.multiply(ink, bands), fade), speck)

    paper = Image.new("RGB", size, (244, 242, 236))
    paper.paste((52, 48, 62), (0, 0), ink.point(lambda v: v * 9 // 10))
    # Curl: the paper came off a roll, so it bows along its length; and a few soft creases.
    curl = Image.new("L", (1, 256))
    curl.putdata([int(226 + 26 * math.sin(math.pi * (i / 255) * 2.2 + 0.4)) for i in range(256)])
    curl = curl.resize(size, Image.Resampling.BICUBIC)
    bumps = _soft_noise(size, (5, 9), 40, seed + 3).filter(ImageFilter.GaussianBlur(20))
    bumps = bumps.point(lambda v: max(0, min(255, 236 + (v - 128) // 4)))
    shade = ImageChops.multiply(curl, bumps)
    paper = ImageChops.multiply(paper, Image.merge("RGB", (shade, shade, shade)))
    d = ImageDraw.Draw(paper)
    for frac in (0.31, 0.63):
        fy = int(size[1] * frac) + rng.randint(-12, 12)
        tilt = rng.randint(-6, 6)
        d.line([(0, fy), (size[0], fy + tilt)], fill=(214, 211, 203), width=2)
        d.line([(0, fy + 3), (size[0], fy + 3 + tilt)], fill=(250, 249, 245), width=1)
    # Torn off the printer's cutter: a fine, slightly uneven sawtooth at both ends.
    mask = Image.new("L", size, 255)
    d = ImageDraw.Draw(mask)
    x = 0
    while x < size[0]:
        tooth = rng.randint(7, 10)
        depth = rng.randint(4, 7)
        d.polygon([(x, 0), (x + tooth / 2, depth), (x + tooth, 0)], fill=0)
        d.polygon([(x, size[1]), (x + tooth / 2, size[1] - depth), (x + tooth, size[1])], fill=0)
        x += tooth
    paper.putalpha(mask)
    return paper, marks


def _desk(size: tuple[int, int], seed: int) -> Image.Image:
    """A laminate desktop: a flat warm grey with fine speckle, out of focus."""
    w, h = size
    fine = _noise((w // 2, h // 2), 9, seed + 10).resize(size, Image.Resampling.BILINEAR)
    cloud = _soft_noise(size, (7, 9), 26, seed + 11).filter(ImageFilter.GaussianBlur(40))
    base = ImageChops.add(fine, cloud.point(lambda v: 128 + (v - 128) // 5), scale=2)
    desk = ImageOps.colorize(base, black=(98, 92, 84), white=(196, 188, 174))
    return desk.filter(ImageFilter.GaussianBlur(1.6))


def receipt_photo(rows: list[Row], *, seed: int) -> tuple[bytes, dict[str, Box]]:
    """A phone photo of a thermal receipt lying on a desk."""
    rng = random.Random(seed)
    size = (1512, 2016)
    scene = _desk(size, seed)
    # The edge of a notebook at the top of the frame, out of focus.
    d = ImageDraw.Draw(scene)
    d.polygon([(880, -40), (1560, -40), (1560, 230), (930, 150)], fill=(38, 44, 58))
    d.line([(930, 150), (1560, 230)], fill=(88, 96, 112), width=5)
    scene = scene.filter(ImageFilter.GaussianBlur(2.2))

    paper, marks = _thermal_paper(rows, seed)
    pw, ph = paper.size
    # Fit the receipt in the frame, turned a little, seen from slightly below its foot.
    fit = min(1500 / ph, 760 / pw)
    w2, h2 = pw * fit, ph * fit
    cx, cy = size[0] / 2 + rng.randint(-30, 30), size[1] / 2 + 30
    turn = math.radians(rng.uniform(-7, 7))
    pinch = 0.07
    corners = [
        (-w2 / 2 * (1 - pinch), -h2 / 2),
        (w2 / 2 * (1 - pinch), -h2 / 2),
        (w2 / 2, h2 / 2),
        (-w2 / 2, h2 / 2),
    ]
    quad = [
        (cx + x * math.cos(turn) - y * math.sin(turn), cy + x * math.sin(turn) + y * math.cos(turn))
        for x, y in corners
    ]
    coeffs = perspective([(0, 0), (pw, 0), (pw, ph), (0, ph)], quad)
    warped = paper.transform(size, Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC)
    assert marks.index is not None
    moved = marks.index.transform(
        size, Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.NEAREST
    )
    alpha = warped.getchannel("A")
    # A soft shadow: the paper lifts off the desk more at one side.
    shadow = alpha.filter(ImageFilter.GaussianBlur(22)).point(lambda v: v * 5 // 10)
    scene.paste((30, 26, 22), (26, 30), shadow)
    tight = alpha.filter(ImageFilter.GaussianBlur(5)).point(lambda v: v * 4 // 10)
    scene.paste((30, 26, 22), (6, 8), tight)
    scene.paste(warped.convert("RGB"), (0, 0), alpha)

    # Window light from one side, darker corners, a slightly warm white balance.
    big = (
        Image.linear_gradient("L")
        .resize((size[1] * 3, size[1] * 3))
        .rotate(62, resample=Image.Resampling.BICUBIC)
    )
    mid = big.size[0] // 2
    light = big.crop(
        (
            mid - size[0] // 2,
            mid - size[1] // 2,
            mid - size[0] // 2 + size[0],
            mid - size[1] // 2 + size[1],
        )
    )
    light = light.filter(ImageFilter.GaussianBlur(30)).point(lambda v: 150 + v * 105 // 255)
    vignette = (
        ImageOps.invert(Image.radial_gradient("L"))
        .resize(size)
        .point(lambda v: 196 + v * 59 // 255)
    )
    lit = ImageChops.multiply(light, vignette)
    scene = ImageChops.multiply(scene, Image.merge("RGB", (lit, lit, lit)))
    r, g, b = scene.split()
    scene = Image.merge(
        "RGB", (r.point(lambda v: min(255, int(v * 1.03))), g, b.point(lambda v: int(v * 0.94)))
    )
    scene = scene.filter(ImageFilter.GaussianBlur(0.9))
    grain = _noise((size[0] // 2, size[1] // 2), 7, seed + 20).resize(
        size, Image.Resampling.BILINEAR
    )
    scene = ImageChops.add(scene, Image.merge("RGB", (grain, grain, grain)), scale=1, offset=-128)
    scene = ImageEnhance.Contrast(scene).enhance(1.06)
    out = io.BytesIO()
    scene.save(out, "JPEG", quality=80)
    return out.getvalue(), marks.boxes(moved)


# ------------------------------------------------------------------- scanned page


@dataclass
class Page:
    """A printed page being laid out: draw strings on it and it remembers where they went."""

    size: tuple[int, int] = (1275, 1650)  # US Letter at 150 dots per inch
    image: Image.Image = field(init=False)
    marks: Marks = field(init=False)

    def __post_init__(self) -> None:
        self.image = Image.new("L", self.size, 255)
        self.marks = Marks(self.size)
        self.draw = ImageDraw.Draw(self.image)

    def text(
        self,
        xy: tuple[float, float],
        text: str,
        names: tuple[str, ...],
        size: int,
        *,
        anchor: str = "la",
        fill: int = 20,
    ) -> None:
        f = font(names, size)
        self.draw.text(xy, text, font=f, fill=fill, anchor=anchor)
        box = self.draw.textbbox(xy, text, font=f, anchor=anchor)
        self.marks.add(text, (box[0] - 4, box[1] - 4, box[2] + 4, box[3] + 4))

    def line(self, xy, width: int = 2, fill: int = 40) -> None:
        self.draw.line(xy, fill=fill, width=width)

    def rect(self, box, width: int = 2, fill: int | None = None) -> None:
        self.draw.rectangle(box, outline=40, width=width, fill=fill)


@dataclass
class Stamp:
    """An office's received stamp: a word, a date line and the office's name."""

    word: str
    date: str
    office: str
    at: tuple[float, float]  # fractions of the page
    turn: float = -6.0


def _stamp(stamp: Stamp, seed: int) -> Image.Image:
    layer = Image.new("RGBA", (420, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ink = (44, 62, 150, 235)
    d.rectangle((4, 4, 415, 145), outline=ink, width=4)
    d.text((210, 34), stamp.word, font=font(SANS_BOLD, 40), fill=ink, anchor="mm")
    d.line([(14, 60), (405, 60)], fill=ink, width=2)
    d.text((210, 86), stamp.date, font=font(MONO, 34), fill=ink, anchor="mm")
    d.text((210, 124), stamp.office, font=font(SANS_BOLD, 19), fill=ink, anchor="mm")
    # Uneven inking: blotches where the pad was dry, heavier at one side.
    blot = _soft_noise(layer.size, (30, 12), 60, seed + 30).filter(ImageFilter.GaussianBlur(2))
    blot = blot.point(lambda v: 255 if v > 104 else 70 + v)
    side = (
        Image.linear_gradient("L")
        .rotate(90, expand=True)
        .resize(layer.size)
        .point(lambda v: 150 + v * 105 // 255)
    )
    layer.putalpha(ImageChops.multiply(ImageChops.multiply(layer.getchannel("A"), blot), side))
    layer = layer.filter(ImageFilter.GaussianBlur(0.7))
    return layer.rotate(stamp.turn, expand=True, resample=Image.Resampling.BICUBIC)


def _pen_stroke(
    d: ImageDraw.ImageDraw, points: list[tuple[float, float]], ink, width: int = 3
) -> None:
    d.line(points, fill=ink, width=width, joint="curve")


def _initials(seed: int) -> Image.Image:
    """A quick pen scrawl, as someone initials a page: loops, not letters from a font."""
    rng = random.Random(seed)
    layer = Image.new("RGBA", (220, 110), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ink = (24, 30, 92, 230)
    points = []
    phase = rng.uniform(0.9, 1.5)
    for i in range(121):
        t = i / 120
        swing = 2 * math.pi * 3.6 * t
        x = 16 + 150 * t + 15 * math.sin(swing)
        y = 54 - 30 * math.sin(swing + phase) * (1 - 0.5 * t) + 8 * t
        points.append((x, y))
    _pen_stroke(d, points, ink)
    _pen_stroke(d, [(points[-1][0], points[-1][1]), (198, 70), (212, 58)], ink)
    return layer.filter(ImageFilter.GaussianBlur(0.5))


def _check(seed: int) -> Image.Image:
    layer = Image.new("RGBA", (70, 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    _pen_stroke(d, [(6, 30), (20, 50), (62, 6)], (24, 30, 92, 230), 4)
    return layer.filter(ImageFilter.GaussianBlur(0.5))


def scanned_page(
    page: Page,
    *,
    seed: int,
    stamp: Stamp | None = None,
    initials_at: tuple[float, float] | None = None,
    check_at: tuple[float, float] | None = None,
    turn: float = 0.9,
) -> tuple[bytes, dict[str, Box]]:
    """The page as a flatbed scan: stamped and marked, a little crooked, grainy."""
    rng = random.Random(seed)
    w, h = page.size
    sheet = Image.merge("RGB", (page.image,) * 3).convert("RGBA")
    # The print itself: toner is a little soft and drops out in specks.
    drop = _noise((w // 2, h // 2), 34, seed + 40).resize((w, h), Image.Resampling.BILINEAR)
    drop = drop.point(lambda v: 60 if v > 214 else 0)
    printed = ImageChops.add(page.image.filter(ImageFilter.GaussianBlur(0.6)), drop)
    sheet = Image.merge("RGB", (printed,) * 3).convert("RGBA")
    if stamp is not None:
        sheet.alpha_composite(_stamp(stamp, seed), (int(w * stamp.at[0]), int(h * stamp.at[1])))
    if initials_at is not None:
        sheet.alpha_composite(_initials(seed), (int(w * initials_at[0]), int(h * initials_at[1])))
    if check_at is not None:
        sheet.alpha_composite(_check(seed), (int(w * check_at[0]), int(h * check_at[1])))
    # Paper: off-white, a fold across the middle from the envelope, two staple holes.
    tone = Image.new("RGB", (w, h), (247, 246, 241))
    paper = ImageChops.multiply(sheet.convert("RGB"), tone)
    d = ImageDraw.Draw(paper)
    for frac in (0.372, 0.694):
        fy = int(h * frac) + rng.randint(-6, 6)
        d.line([(0, fy), (w, fy + rng.randint(-3, 3))], fill=(228, 227, 222), width=3)
        d.line([(0, fy + 3), (w, fy + 3)], fill=(252, 252, 250), width=1)
    for dx in (0, 16):
        d.ellipse((58 + dx, 52, 62 + dx, 56), fill=(120, 120, 120))
    paper = paper.convert("RGBA").rotate(
        turn, expand=True, resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0)
    )
    assert page.marks.index is not None
    moved_marks = page.marks.index.rotate(
        turn, expand=True, resample=Image.Resampling.NEAREST, fillcolor=0
    )
    # The scanner's bed shows past the sheet's edge, with the sheet's shadow.
    bed = Image.new("RGB", (w, h), (233, 233, 231))
    off = ((w - paper.width) // 2 + 6, (h - paper.height) // 2 + 4)
    shadow = paper.getchannel("A").filter(ImageFilter.GaussianBlur(5))
    bed.paste((170, 170, 170), (off[0] + 4, off[1] + 5), shadow)
    bed.paste(paper.convert("RGB"), off, paper.getchannel("A"))
    moved = Image.new("L", (w, h), 0)
    moved.paste(moved_marks, off)
    # The scan: soft, grainy, a darker band along the lid's hinge, compressed.
    bed = bed.filter(ImageFilter.GaussianBlur(0.5))
    grain = _noise((w // 2, h // 2), 6, seed + 41).resize((w, h), Image.Resampling.BILINEAR)
    bed = ImageChops.add(bed, Image.merge("RGB", (grain,) * 3), scale=1, offset=-128)
    hinge = (
        Image.linear_gradient("L")
        .rotate(90, expand=True)
        .resize((w, h))
        .point(lambda v: 255 if v > 10 else 222 + v * 3)
    )
    bed = ImageChops.multiply(bed, Image.merge("RGB", (hinge,) * 3))
    bed = ImageEnhance.Contrast(bed).enhance(1.1)
    out = io.BytesIO()
    bed.save(out, "JPEG", quality=58)
    return out.getvalue(), page.marks.boxes(moved)
