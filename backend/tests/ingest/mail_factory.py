"""Synthetic emails for the ingest tests. Every address uses the .example domain."""

import io
from email.message import EmailMessage
from typing import cast

from PIL import Image

MAILBOX = "fundtrail-demo@mail.example"
PI = "pat.rivera@university.example"
STRANGER = "billing@vendor.example"


def png(width: int, height: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (120, 30, 200)).save(out, format="PNG")
    return out.getvalue()


PDF = b"%PDF-1.4\n% synthetic invoice SYN-2401\n%%EOF\n"


def email(
    *,
    sender: str = PI,
    to: str = "fundtrail-demo+abc23def@mail.example",
    delivered_to: str | None = None,
    subject: str = "Approval for sequencing, award SYN-2401",
    body: str = "Approved. Pat",
) -> EmailMessage:
    msg = EmailMessage()
    if delivered_to:
        msg["Delivered-To"] = delivered_to
    msg["From"] = f"Sender <{sender}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = "Tue, 03 Mar 2026 10:15:00 -0800"
    msg.set_content(body)
    return msg


def with_attachments(msg: EmailMessage) -> EmailMessage:
    msg.add_attachment(PDF, maintype="application", subtype="pdf", filename="invoice_1001.pdf")
    msg.add_attachment(png(40, 40), maintype="image", subtype="png", filename="logo.png")
    return msg


def with_pasted_photo(msg: EmailMessage) -> EmailMessage:
    msg.add_alternative("<p>Receipt below</p><img src='cid:photo1'>", subtype="html")
    html = cast(list[EmailMessage], msg.get_payload())[1]
    html.add_related(png(800, 600), maintype="image", subtype="png", cid="<photo1>")
    return msg


def forwarding(inner: EmailMessage, *, sender: str = PI) -> EmailMessage:
    outer = email(sender=sender, subject="Fwd: invoice", body="See the attached message.")
    outer.add_attachment(inner)
    return outer
