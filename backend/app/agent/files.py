"""Sending an evidence file to the model, as it is.

- Plain text and email go as a citable plain-text document: the stored text, unchanged, so the
  API's character indexes are indexes into the stored file.
- A PDF goes as a citable PDF document, unchanged. A page with no text layer is a scan: it also
  goes as an image of the page at a size we control, so the agent can box values on it. A PDF
  whose pages all have no text goes as those images only.
- A photo goes as an image at a size we control, no larger than the model's high-resolution tier
  (2,576 pixels on the long edge), so a pixel box on it maps back onto the original.

Citations must be on for every document in a request or none, so every file sent is a citable
document, and the lists of charges and documents go as plain text.

Not handled yet: .docx (its text has to be extracted first). open_file reports it as a file it
can't open.
"""

import base64
import io
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PIL import Image

from app.ingest.channel_times import reading_text
from app.quotes.page_images import pdf_pages_with_text, render_pdf_page
from app.quotes.pdf import UnreadablePdfError

from .adapter import EvidenceFile
from .citations import SentDocument, SentImage

# The model's high-resolution tier for images: the long edge in pixels, and the most pixels in
# all. The API refuses a larger image we've marked not to be resized: a 1991 by 2576 page came
# back "would be downsized to 1688x2184", which is 1920 by 1920 pixels in all.
MAX_IMAGE_EDGE = 2576
MAX_IMAGE_PIXELS = 1920 * 1920

TEXT_TYPES = ("text/", "message/rfc822")
IMAGE_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG", "image/gif": "GIF", "image/webp": "WEBP"}
# A scan with more pages than this sends only its first pages as images (handwriting and long
# scans aren't settled: architecture.md, "Not decided yet").
MAX_SCANNED_PAGES = 20


class CantOpen(Exception):
    """A file the agent can't send to the model, as a plain sentence."""


@dataclass
class Opened:
    """What one open_file sends: the content blocks, and the documents and images among them."""

    blocks: list[dict[str, Any]]
    document: SentDocument | None = None
    images: list[SentImage] | None = None  # a photo, or each scanned page sent as an image


def describe(f: EvidenceFile) -> str:
    parts = [
        f"File {f.id}: {f.name}",
        f"source {f.source}",
        f"arrived {f.arrived_at:%Y-%m-%d %H:%M} UTC",
    ]
    if f.sender:
        parts.append(f"sender {f.sender}")
    if f.document_date:
        parts.append(f"dated {f.document_date:%Y-%m-%d}")
    if f.parent_id:
        parts.append(f"attachment of {f.parent_id}")
    return ", ".join(parts)


def open_file(f: EvidenceFile, data: bytes, reading_now: datetime | None = None) -> Opened:
    """The blocks that send a whole file to the model.

    `reading_now` is set on a sample grant, whose channel times come from the grant's now
    (issue 165, point 4): a live email is read with its Date header replaced by it, and the
    citations into it map back to the stored file.
    """
    media = f.media_type.lower()
    head = {"type": "text", "text": describe(f)}
    title = f"{f.name} ({f.id})"
    if media.startswith(TEXT_TYPES):
        text = data.decode("utf-8", errors="replace")
        reading = None
        if reading_now is not None and media == "message/rfc822":
            reading = reading_text(text, reading_now)
        block = {
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": reading.text if reading is not None else text,
            },
            "title": title,
            "citations": {"enabled": True},
        }
        sent = SentDocument(f.id, "text", text=text, reading=reading)
        return Opened([head, block], document=sent)
    if media == "application/pdf":
        return _open_pdf(f, data, head, title)
    if media in IMAGE_TYPES:
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except Exception as error:  # Pillow raises many kinds for a damaged file
            raise CantOpen(f"file {f.id} couldn't be read as an image") from error
        image = fit(image)
        block, sent = image_block(f.id, 1, image)
        note = {
            "type": "text",
            "text": (
                f"{describe(f)}. This is a photo or scan with no citations: for each value give "
                f"a pixel box on this {image.width} by {image.height} image."
            ),
        }
        return Opened([note, block], images=[sent])
    raise CantOpen(
        f"file {f.id} is a {f.media_type}, which the agent can't open yet; flag the file"
    )


def fit(image: Image.Image) -> Image.Image:
    """The image at a size we control: no larger than the model's high-resolution tier."""
    scale = min(
        1.0,
        MAX_IMAGE_EDGE / max(image.size),
        (MAX_IMAGE_PIXELS / (image.width * image.height)) ** 0.5,
    )
    if scale < 1.0:
        # Rounded down, so the size never runs over a limit.
        size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image


def image_block(file_id: str, page: int, image: Image.Image) -> tuple[dict[str, Any], SentImage]:
    """An image content block, and what was sent, for a photo or a scanned page."""
    out = io.BytesIO()
    fmt = "PNG" if image.mode not in ("RGB", "L") else "JPEG"
    image.save(out, format=fmt)
    block = {
        "type": "image",
        # We sized it ourselves; the API errors rather than resize it without saying so.
        "transformations": {"oversized_image": "error"},
        "source": {
            "type": "base64",
            "media_type": "image/png" if fmt == "PNG" else "image/jpeg",
            "data": base64.b64encode(out.getvalue()).decode("ascii"),
        },
    }
    return block, SentImage(file_id, page, image.width, image.height)


def _open_pdf(f: EvidenceFile, data: bytes, head: dict[str, Any], title: str) -> Opened:
    """A PDF as a citable document, with each page that has no text layer also as an image.

    A page with real text keeps its citations and the text check. A scanned page has nothing to
    cite, so the agent boxes its values on the page's image, and the second look reads them.
    """
    try:
        has_text = pdf_pages_with_text(data)
    except UnreadablePdfError:
        has_text = []  # sent as it is; the API says what it makes of it
    scanned = [n for n, text in enumerate(has_text, start=1) if not text]
    blocks: list[dict[str, Any]] = [head]
    document: SentDocument | None = None
    if not scanned or len(scanned) < len(has_text):
        blocks.append(
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.b64encode(data).decode("ascii"),
                },
                "title": title,
                "citations": {"enabled": True},
            }
        )
        document = SentDocument(f.id, "pdf", pdf=data)
    if not scanned:
        return Opened(blocks, document=document)
    sent: list[SentImage] = []
    for page in scanned[:MAX_SCANNED_PAGES]:
        image = fit(render_pdf_page(data, page, MAX_IMAGE_EDGE))
        block, image_sent = image_block(f.id, page, image)
        blocks.append(
            {
                "type": "text",
                "text": (
                    f"Page {page} of file {f.id} is a scan with no text to cite: for each value "
                    f"on it give a pixel box on this {image.width} by {image.height} image, with "
                    f"page {page}."
                ),
            }
        )
        blocks.append(block)
        sent.append(image_sent)
    if len(scanned) > MAX_SCANNED_PAGES:
        blocks.append(
            {
                "type": "text",
                "text": (
                    f"Only the first {MAX_SCANNED_PAGES} of its {len(scanned)} scanned pages were "
                    "sent: flag the file if a value you need is on a later page."
                ),
            }
        )
    return Opened(blocks, document=document, images=sent)


def reading_now(inputs: Any, f: EvidenceFile) -> datetime | None:
    """The time a sample grant's live email is read as sent: the grant's now when it arrived,
    which is also the sent date stored with it. None on a grant on the real date."""
    if not getattr(inputs, "channel_times_from_grant_now", False):
        return None
    return f.arrived_at
