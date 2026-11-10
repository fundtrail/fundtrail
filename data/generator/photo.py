"""Receipt photos: a paper receipt on a desk, drawn with Pillow.

Dev-only. Pillow isn't a dependency of the app: run the generator with
`uv run --with pillow python data/generator/build.py` to redraw the photos.
Without Pillow the generator keeps the photos already on disk.
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


def available() -> bool:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


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
    """The photo, drawn fresh when Pillow is installed, else the one already on disk."""
    if available():
        return receipt_photo(lines, seed=seed)
    for path in [*(DATA / "samples").glob(f"*/{name}"), *(DATA / "demo").glob(f"*/{name}")]:
        if path.is_file():
            return path.read_bytes()
    raise SystemExit(f"{name} isn't on disk and Pillow isn't installed: run with uv --with pillow")


# A scanned page: white paper, straight, text from the top left. agent_records.py
# works out a value's box from these numbers.
SCAN_WIDTH = 1000
SCAN_MARGIN = 60
SCAN_TOP = 80
SCAN_LINE = 34


def scanned_page(lines: list[str], *, seed: int) -> bytes:
    """A JPEG of a page scanned in grey, holding `lines`."""
    from PIL import Image, ImageDraw, ImageFilter

    rng = random.Random(seed)
    font = _font(24)
    height = SCAN_TOP + SCAN_LINE * len(lines) + 80
    page = Image.new("L", (SCAN_WIDTH, height), 244)
    draw = ImageDraw.Draw(page)
    for i, text in enumerate(lines):
        draw.text((SCAN_MARGIN, SCAN_TOP + i * SCAN_LINE), text, font=font, fill=35)
    for _ in range(400):
        x, y = rng.randint(0, SCAN_WIDTH - 1), rng.randint(0, height - 1)
        draw.point((x, y), fill=rng.randint(200, 235))
    page = page.filter(ImageFilter.GaussianBlur(0.5))
    out = io.BytesIO()
    page.save(out, "JPEG", quality=70, optimize=True)
    return out.getvalue()


def scan(name: str, lines: list[str], *, seed: int) -> bytes:
    """The scan, drawn fresh when Pillow is installed, else the one already on disk."""
    if available():
        return scanned_page(lines, seed=seed)
    for path in [*(DATA / "samples").glob(f"*/{name}"), *(DATA / "demo").glob(f"*/{name}")]:
        if path.is_file():
            return path.read_bytes()
    raise SystemExit(f"{name} isn't on disk and Pillow isn't installed: run with uv --with pillow")
