"""Sending an evidence file to the model, as it is.

- Plain text and email go as a citable plain-text document: the stored text, unchanged, so the
  API's character indexes are indexes into the stored file.
- A PDF goes as a citable PDF document, unchanged.
- A photo goes as an image at a size we control, no larger than the model's high-resolution tier
  (2,576 pixels on the long edge), so a pixel box on it maps back onto the original.

Citations must be on for every document in a request or none, so every file sent is a citable
document, and the lists of charges and documents go as plain text.

Not handled yet: .docx (its text has to be extracted first), and scanned PDFs with no text (their
pages have to go as images). open_file reports those as files it can't open.
"""

import base64
import io
from dataclasses import dataclass
from typing import Any

from PIL import Image

from .adapter import EvidenceFile
from .citations import SentDocument, SentImage

# The model's high-resolution tier for images: the long edge in pixels.
MAX_IMAGE_EDGE = 2576

TEXT_TYPES = ("text/", "message/rfc822")
IMAGE_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG", "image/gif": "GIF", "image/webp": "WEBP"}


class CantOpen(Exception):
    """A file the agent can't send to the model, as a plain sentence."""


@dataclass
class Opened:
    """What one open_file sends: the content blocks, and the documents and images among them."""

    blocks: list[dict[str, Any]]
    document: SentDocument | None = None
    image: SentImage | None = None


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


def open_file(f: EvidenceFile, data: bytes) -> Opened:
    """The blocks that send a whole file to the model."""
    media = f.media_type.lower()
    head = {"type": "text", "text": describe(f)}
    title = f"{f.name} ({f.id})"
    if media.startswith(TEXT_TYPES):
        text = data.decode("utf-8", errors="replace")
        block = {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": text},
            "title": title,
            "citations": {"enabled": True},
        }
        return Opened([head, block], document=SentDocument(f.id, "text", text=text))
    if media == "application/pdf":
        block = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.b64encode(data).decode("ascii"),
            },
            "title": title,
            "citations": {"enabled": True},
        }
        return Opened([head, block], document=SentDocument(f.id, "pdf", pdf=data))
    if media in IMAGE_TYPES:
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except Exception as error:  # Pillow raises many kinds for a damaged file
            raise CantOpen(f"file {f.id} couldn't be read as an image") from error
        scale = min(1.0, MAX_IMAGE_EDGE / max(image.size))
        if scale < 1.0:
            size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            image = image.resize(size, Image.Resampling.LANCZOS)
        out = io.BytesIO()
        fmt = "PNG" if image.mode not in ("RGB", "L") else "JPEG"
        image.save(out, format=fmt)
        sent_type = "image/png" if fmt == "PNG" else "image/jpeg"
        note = {
            "type": "text",
            "text": (
                f"{describe(f)}. This is a photo or scan with no citations: for each value give "
                f"a pixel box on this {image.width} by {image.height} image."
            ),
        }
        block = {
            "type": "image",
            # We sized it ourselves; the API errors rather than resize it without saying so.
            "transformations": {"oversized_image": "error"},
            "source": {
                "type": "base64",
                "media_type": sent_type,
                "data": base64.b64encode(out.getvalue()).decode("ascii"),
            },
        }
        return Opened([note, block], image=SentImage(f.id, 1, image.width, image.height))
    raise CantOpen(
        f"file {f.id} is a {f.media_type}, which the agent can't open yet; flag the file"
    )
