"""The second look on a photo or scanned page (decision 0012, ruling 78).

One model call per photo or page, with every boxed area on it as its own numbered crop. The call
sees only the crops: not the page, not the agent's values, not what the field is. It returns
what it reads in each, and code compares that with the agent's value. A crop it can't read
comes back as unreadable.

This module builds the request content and reads the reply. Calling the model, and comparing
what it read, are the agent's (app/agent/second_look.py).
"""

import base64
import io
import re
from typing import Any

from PIL import Image

SYSTEM = (
    "You read text in small images cropped from documents such as receipts, invoices and "
    "letters. Each crop is numbered. For each crop, write the text you see in it, exactly as "
    "written: the same digits, punctuation, currency signs and spelling, on one line. Don't "
    "correct, complete or explain anything. If a crop has no text, or you can't read it with "
    "confidence, write UNREADABLE for it.\n\n"
    "Reply with one line per crop and nothing else, in this form:\n"
    "1: <text>\n"
    "2: <text>"
)

UNREADABLE = "UNREADABLE"

_LINE = re.compile(r"^\s*(\d+)\s*[:.)]\s?(.*?)\s*$")


def _encode(image: Image.Image) -> dict[str, Any]:
    out = io.BytesIO()
    image.convert("RGB").save(out, format="PNG")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(out.getvalue()).decode("ascii"),
        },
    }


def request_content(crops: list[Image.Image]) -> list[dict[str, Any]]:
    """The user message's content: each crop after its number."""
    content: list[dict[str, Any]] = []
    for n, crop in enumerate(crops, start=1):
        content.append({"type": "text", "text": f"Crop {n}:"})
        content.append(_encode(crop))
    content.append(
        {"type": "text", "text": f"Read each of the {len(crops)} crops, one line per crop."}
    )
    return content


def parse_readings(reply: str, count: int) -> list[str | None]:
    """What the reply reads in each of `count` crops, in order. None for a crop it couldn't read,
    one it left out, or one it answered more than once."""
    seen: dict[int, list[str]] = {}
    for line in reply.splitlines():
        m = _LINE.match(line)
        if m is None:
            continue
        seen.setdefault(int(m.group(1)), []).append(m.group(2))
    out: list[str | None] = []
    for n in range(1, count + 1):
        answers = seen.get(n, [])
        text = answers[0].strip() if len(answers) == 1 else ""
        out.append(None if not text or text.upper() == UNREADABLE else text)
    return out
