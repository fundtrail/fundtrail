"""An email becomes one evidence file per thing in it (decision 0025).

- The message itself, kept as it arrived (the raw bytes, `message/rfc822`).
- Each attached document, pointing back to the message.
- Each attachment of a message forwarded as an attachment, also pointing back to
  the outer message, which holds the forwarded message's text.
- A photo pasted into the body is kept. Only very small images, such as a logo or
  a signature mark, are skipped.
"""

import io
import mimetypes
from dataclasses import dataclass
from datetime import date
from email import message_from_bytes, policy
from email.message import EmailMessage, Message
from email.utils import getaddresses, parsedate_to_datetime

from PIL import Image

from .incoming import IncomingFile, safe_name

# An image smaller than this many pixels (about 200 by 200) is a logo or a
# signature mark, not evidence.
SMALL_IMAGE_PIXELS = 40_000

_SKIPPED_TYPES = {
    "application/pkcs7-signature",
    "application/x-pkcs7-signature",
    "application/pgp-signature",
}


@dataclass(frozen=True)
class ParsedEmail:
    headers: dict[str, list[str]]  # lower-case name -> values, in order
    sender: str | None  # the From address, lower case
    subject: str
    sent_on: date | None


def parse_headers(raw: bytes) -> ParsedEmail:
    msg = message_from_bytes(raw, policy=policy.default)
    headers: dict[str, list[str]] = {}
    for name, value in msg.items():
        headers.setdefault(name.lower(), []).append(str(value))
    senders = [a for _, a in getaddresses(headers.get("from", [])) if a]
    sent_on = None
    if "date" in headers:
        try:
            sent_on = parsedate_to_datetime(headers["date"][0]).date()
        except (TypeError, ValueError):
            sent_on = None
    return ParsedEmail(
        headers=headers,
        sender=senders[0].lower() if senders else None,
        subject=headers.get("subject", [""])[0].strip(),
        sent_on=sent_on,
    )


def is_small_image(data: bytes) -> bool:
    """True for an image too small to be evidence. An image Pillow can't read is kept."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
    except Exception:
        return False
    return width * height < SMALL_IMAGE_PIXELS


def _part_bytes(part: Message) -> bytes | None:
    payload = part.get_payload(decode=True)
    return payload if isinstance(payload, bytes) else None


def _is_evidence_part(part: Message) -> bool:
    if part.is_multipart() or part.get_content_type() == "message/rfc822":
        return False  # containers: their parts are walked
    content_type = part.get_content_type()
    if content_type in _SKIPPED_TYPES:
        return False
    if part.get_filename():
        return True
    if part.get_content_disposition() == "attachment":
        return True
    # A body part with no file name: the text is in the message file. Images are photos
    # pasted into the body.
    return part.get_content_maintype() == "image"


def email_to_files(
    raw: bytes, *, message_id: str, grant_id: str, workspace_id: str
) -> list[IncomingFile]:
    """The message first, then one file per attachment, in the order they appear."""
    parsed = parse_headers(raw)
    message_key = f"gmail:{message_id}"
    files = [
        IncomingFile(
            key=message_key,
            grant_id=grant_id,
            workspace_id=workspace_id,
            source="gmail",
            name=safe_name(parsed.subject, "email") + ".eml",
            media_type="message/rfc822",
            data=raw,
            document_date=parsed.sent_on,
            sender=parsed.sender,
            source_ref=message_id,
        )
    ]
    msg = message_from_bytes(raw, policy=policy.default)
    assert isinstance(msg, EmailMessage)
    for index, part in enumerate(msg.walk()):
        if part is msg or not _is_evidence_part(part):
            continue
        data = _part_bytes(part)
        if not data:
            continue
        content_type = part.get_content_type()
        if part.get_content_maintype() == "image" and is_small_image(data):
            continue
        extension = mimetypes.guess_extension(content_type) or ".bin"
        name = safe_name(part.get_filename() or "", f"attachment-{index}{extension}")
        files.append(
            IncomingFile(
                key=f"{message_key}:{index}",
                grant_id=grant_id,
                workspace_id=workspace_id,
                source="gmail",
                name=name,
                media_type=content_type,
                data=data,
                # An attachment's own date isn't given by the source; a date written inside
                # it becomes a cited value on a record.
                document_date=None,
                sender=parsed.sender,
                source_ref=message_id,
                parent_key=message_key,
            )
        )
    return files
