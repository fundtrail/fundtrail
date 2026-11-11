"""The unused seed grants' receipt photo: a paper receipt on a desk, drawn with Pillow.

The samples' images are drawn by images.py and realphoto.py. This one is kept as
it is on disk. It's drawn again only if it's missing, which needs Pillow.
"""

from __future__ import annotations

import io
import random
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent

MONO_FONTS = (
    "/System/Library/Fonts/Courier.ttc",
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)


def _font(size: int):
    from PIL import ImageFont

    for path in MONO_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def receipt_photo(lines: list[str], *, seed: int) -> bytes:
    """A JPEG photo of a thermal receipt holding `lines`, slightly turned."""
    from PIL import Image, ImageDraw, ImageFilter

    rng = random.Random(seed)
    font = _font(30)
    line_h = 38
    paper_w = 620
    paper_h = 80 + line_h * len(lines) + 60
    paper = Image.new("RGB", (paper_w, paper_h), (246, 243, 236))
    draw = ImageDraw.Draw(paper)
    for i, text in enumerate(lines):
        ink = 40 + rng.randint(0, 25)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        x = (paper_w - width) // 2 if text.isupper() and len(text) < 26 else 34
        draw.text((x, 60 + i * line_h), text, font=font, fill=(ink, ink, ink + 5))
    # Faint creases across the paper.
    for _ in range(3):
        y = rng.randint(80, paper_h - 80)
        draw.line([(0, y), (paper_w, y + rng.randint(-6, 6))], fill=(232, 229, 220), width=2)
    paper = paper.rotate(rng.uniform(-3.5, 3.5), expand=True, fillcolor=(0, 0, 0, 0))

    w, h = paper.size[0] + 260, paper.size[1] + 220
    desk = Image.new("RGB", (w, h), (92, 70, 52))
    grain = ImageDraw.Draw(desk)
    for y in range(0, h, 3):
        shade = 84 + rng.randint(0, 18)
        grain.line([(0, y), (w, y)], fill=(shade, int(shade * 0.76), int(shade * 0.56)))
    desk = desk.filter(ImageFilter.GaussianBlur(1.2))
    shadow = Image.new("L", paper.size, 0)
    shadow.paste(255, mask=paper.convert("L").point(lambda v: 255 if v > 10 else 0))
    desk.paste((40, 30, 22), (138, 122), shadow.filter(ImageFilter.GaussianBlur(8)))
    desk.paste(paper, (130, 110), paper.convert("L").point(lambda v: 255 if v > 10 else 0))
    desk = desk.filter(ImageFilter.GaussianBlur(0.6))
    desk = desk.resize((desk.size[0] * 2 // 3, desk.size[1] * 2 // 3))
    out = io.BytesIO()
    desk.save(out, "JPEG", quality=72, optimize=True)
    return out.getvalue()


def photo(name: str, lines: list[str], *, seed: int) -> bytes:
    """The photo already on disk, or a fresh drawing of it if it's missing."""
    for path in [*(DATA / "samples").glob(f"*/{name}"), *(DATA / "demo").glob(f"*/{name}")]:
        if path.is_file():
            return path.read_bytes()
    return receipt_photo(lines, seed=seed)
