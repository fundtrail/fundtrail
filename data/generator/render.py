"""Renders the seed's documents: award notices, invoices, emails, letters and PDFs.

Every renderer returns the document's text. `pdf()` lays text out in a simple
PDF with real, uncompressed text, so the seed's test can read it back with the
standard library.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")
UNIVERSITY = "University of Example"
UNIVERSITY_ADDRESS = "100 Example Hall, Example City, CA 94000"

NSF_GRANTS_OFFICIAL = ("Avery Ledger", "avery.ledger@funder.example")
NSF_AWARDING_OFFICIAL = ("Morgan Signet", "morgan.signet@funder.example")


def long_date(d: date) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    dollars, rest = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{rest:02d}"


def whole_money(cents: int) -> str:
    """An award notice prints whole dollars, like $60,000."""
    assert cents % 100 == 0
    return f"${cents // 100:,}"


def email_date(at: datetime) -> str:
    """An RFC 2822 date in Pacific time, for an email's Date header."""
    local = at.astimezone(PACIFIC)
    return local.strftime("%a, ") + f"{local.day} " + local.strftime("%b %Y %H:%M:%S %z")


def pappg(on: date) -> str:
    """The policy guide in force on a date: NSF 24-1 from May 20, 2024, NSF 23-1 before."""
    return "NSF 24-1" if on >= date(2024, 5, 20) else "NSF 23-1"


def sentence(text: str) -> str:
    """Text ending in one period, so a name like "Example Lab Supply Co." gets no second."""
    return text if text.endswith(".") else text + "."


def short(text: str, limit: int = 60) -> str:
    """Text cut at a word boundary to fit a ledger description."""
    if len(text) <= limit:
        return text
    cut = text[: limit + 1].rsplit(" ", 1)[0]
    return cut.rstrip(" ,")


def wrap(text: str, width: int = 74) -> list[str]:
    out: list[str] = []
    line = ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    if line:
        out.append(line)
    return out


# ---------------------------------------------------------------- award notices


def award_notice(
    *,
    award_number: str,
    amendment_type: str,
    amendment_number: str,
    amendment_date: date,
    description: str,
    start: date,
    end: date,
    title: str,
    instrument: str = "Standard Grant",
    obligated_cents: int,
    personnel: list[tuple[str, str, str]],
    intended_cents: int | None = None,
    to_date_cents: int | None = None,
    award_date: date | None = None,
    program_officer: tuple[str, str],
    conditions: str,
    budget: list[tuple[str, int, list[tuple[str, int]]]],
) -> str:
    """An award notice laid out like a real NSF notice (domain.md).

    `personnel` is (name, role, email). `budget` is (line, amount, sub-lines),
    where the line carries its letter, such as "E. Travel".
    """
    lines = [
        "NATIONAL SCIENCE FOUNDATION",
        "AWARD NOTICE",
        "",
        "RECIPIENT INFORMATION",
        f"Recipient: {UNIVERSITY}",
        f"Address: {UNIVERSITY_ADDRESS}",
        "",
        "AMENDMENT INFORMATION",
        f"Amendment Type: {amendment_type}",
        f"Amendment Number: {amendment_number}",
        f"Amendment Date: {long_date(amendment_date)}",
    ]
    desc = wrap("Amendment Description: " + description)
    lines += desc
    lines += [
        "",
        "AWARD INFORMATION",
        f"Award Number (FAIN): {award_number}",
        f"Award Instrument: {instrument}",
        f"Award Date: {long_date(award_date or amendment_date)}",
        f"Period of Performance Start Date: {long_date(start)}",
        f"Period of Performance End Date: {long_date(end)}",
        f"Project Title: {title}",
        f"Funding Opportunity: {pappg(amendment_date)} Proposal & Award Policies & Procedures "
        "Guide (PAPPG)",
        "",
        "FUNDING INFORMATION",
        f"Amount Obligated by this Amendment: {whole_money(obligated_cents)}",
        f"Total Intended Award Amount: {whole_money(intended_cents or obligated_cents)}",
        "Cost Share: $0",
        f"Total Amount Obligated to Date: {whole_money(to_date_cents or obligated_cents)}",
        "Expenditure Limitation: Not applicable",
        "",
        "PROJECT PERSONNEL",
    ]
    for name, role, email in personnel:
        lines += [f"{name}, {role}", f"  Email: {email}", f"  Organization: {UNIVERSITY}"]
    lines += [
        "",
        "NSF CONTACT INFORMATION",
        f"Managing Grants Official: {NSF_GRANTS_OFFICIAL[0]}",
        f"  Email: {NSF_GRANTS_OFFICIAL[1]}",
        f"Awarding Official: {NSF_AWARDING_OFFICIAL[0]}",
        f"  Email: {NSF_AWARDING_OFFICIAL[1]}",
        f"Managing Program Officer: {program_officer[0]}",
        f"  Email: {program_officer[1]}",
        "",
        "TERMS AND CONDITIONS",
    ]
    lines += wrap(conditions)
    lines += ["", "BUDGET", "Only the lines that hold funds are shown.", ""]
    total = 0
    letters = []
    for line, amount, subs in budget:
        total += amount
        letters.append(line.split(".")[0])
        lines.append(f"{line:<52}{whole_money(amount):>9}")
        for sub, sub_amount in subs:
            lines.append(f"     {sub:<47}{whole_money(sub_amount):>9}")
    assert total == obligated_cents, (award_number, total, obligated_cents)
    lines.append(f"{'H. Total Direct Costs':<52}{whole_money(total):>9}")
    lines += ["", "Except as modified by this amendment, the award conditions remain unchanged."]
    return "\n".join(lines) + "\n"


def extension_notice(
    *,
    award_number: str,
    amendment_number: str,
    amendment_date: date,
    start: date,
    old_end: date,
    new_end: date,
    title: str,
    program_officer: tuple[str, str],
) -> str:
    """A no-cost extension: a few sections, the change stated as dates."""
    lines = [
        "NATIONAL SCIENCE FOUNDATION",
        "AWARD NOTICE",
        "",
        "RECIPIENT INFORMATION",
        f"Recipient: {UNIVERSITY}",
        f"Address: {UNIVERSITY_ADDRESS}",
        "",
        "AMENDMENT INFORMATION",
        "Amendment Type: No Cost Extensions",
        f"Amendment Number: {amendment_number}",
        f"Amendment Date: {long_date(amendment_date)}",
    ]
    lines += wrap(
        "Amendment Description: The purpose of this amendment is to extend the end date "
        f"from {long_date(old_end)} to {long_date(new_end)}, as notified by the awardee "
        "under its authority to extend the award once without additional funds. No funds "
        "are added by this amendment."
    )
    lines += [
        "",
        "AWARD INFORMATION",
        f"Award Number (FAIN): {award_number}",
        f"Period of Performance Start Date: {long_date(start)}",
        f"Period of Performance End Date: {long_date(new_end)}",
        f"Project Title: {title}",
        "",
        "NSF CONTACT INFORMATION",
        f"Managing Grants Official: {NSF_GRANTS_OFFICIAL[0]}",
        f"  Email: {NSF_GRANTS_OFFICIAL[1]}",
        f"Managing Program Officer: {program_officer[0]}",
        f"  Email: {program_officer[1]}",
        "",
        "Except as modified by this amendment, the award conditions remain unchanged.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- bills


def invoice(
    *,
    vendor: str,
    vendor_address: str,
    vendor_email: str,
    number: str,
    dated: date,
    attn: str,
    department: str,
    project_ref: str,
    items: list[tuple[str, int, int]],
    shipping_cents: int = 0,
    po: str | None = None,
    terms: str = "net 30",
) -> tuple[str, int]:
    """A vendor's invoice. `items` is (description, quantity, unit cents).

    Returns the text and the total in cents.
    """
    lines = [
        vendor.upper(),
        vendor_address,
        vendor_email,
        "",
        "INVOICE",
        "",
        f"Invoice number: {number}",
        f"Invoice date: {long_date(dated)}",
    ]
    if po:
        lines.append(f"Customer PO: {po}")
    lines += [
        "",
        "Bill to:",
        f"  {UNIVERSITY}, {department}",
        f"  Attn: {attn}",
        f"  {UNIVERSITY_ADDRESS}",
        f"Project reference: {project_ref}",
        "",
        f"{'Item':<6}{'Description':<44}{'Qty':>5}{'Unit price':>13}{'Amount':>12}",
    ]
    subtotal = 0
    for n, (desc, qty, unit) in enumerate(items, start=1):
        amount = qty * unit
        subtotal += amount
        lines.append(f"{n:<6}{desc:<44}{qty:>5}{money(unit):>13}{money(amount):>12}")
    total = subtotal + shipping_cents
    lines += [
        "",
        f"{'Subtotal':<68}{money(subtotal):>12}",
        f"{'Shipping':<68}{money(shipping_cents):>12}",
        f"{'Total due':<68}{money(total):>12}",
        "",
        f"Terms: {terms}",
    ]
    return "\n".join(lines) + "\n", total


def usage_statement(
    *,
    facility: str,
    unit: str,
    number: str,
    dated: date,
    period: str,
    pi: str,
    award_number: str,
    rows: list[tuple[str, int, int]],
) -> tuple[str, int]:
    """A campus facility's monthly usage statement for an internal recharge."""
    lines = [
        UNIVERSITY.upper(),
        facility,
        unit,
        "",
        "RECHARGE USAGE STATEMENT",
        "",
        f"Statement number: {number}",
        f"Statement date: {long_date(dated)}",
        f"Service period: {period}",
        f"Principal investigator: {pi}",
        f"Award charged: {award_number}",
        "",
        f"{'Service':<46}{'Units':>7}{'Rate':>12}{'Amount':>14}",
    ]
    total = 0
    for desc, qty, rate in rows:
        amount = qty * rate
        total += amount
        lines.append(f"{desc:<46}{qty:>7}{money(rate):>12}{money(amount):>14}")
    lines += [
        "",
        f"{'Total charged to award':<65}{money(total):>14}",
        "",
        "Rates are the facility's approved recharge rates for the fiscal year.",
    ]
    return "\n".join(lines) + "\n", total


def eml(
    *,
    sender: tuple[str, str],
    to: tuple[str, str],
    at: datetime,
    subject: str,
    message_id: str,
    body: str,
    cc: tuple[str, str] | None = None,
) -> str:
    """A plain-text email, as a .eml file."""
    head = [
        f"From: {sender[0]} <{sender[1]}>",
        f"To: {to[0]} <{to[1]}>",
    ]
    if cc:
        head.append(f"Cc: {cc[0]} <{cc[1]}>")
    head += [
        f"Date: {email_date(at)}",
        f"Subject: {subject}",
        f"Message-ID: <{message_id}>",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
    ]
    return "\n".join(head) + "\n" + body.rstrip("\n") + "\n"


def forwarded(*, sender: tuple[str, str], at: datetime, subject: str, to: str, body: str) -> str:
    """A forwarded message block, placed under a note in an email's body."""
    return "\n".join(
        [
            "---------- Forwarded message ----------",
            f"From: {sender[0]} <{sender[1]}>",
            f"Date: {email_date(at)}",
            f"Subject: {subject}",
            f"To: {to}",
            "",
            body.rstrip("\n"),
        ]
    )


# ---------------------------------------------------------------- PDF


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf(text: str, *, title: str, lines_per_page: int = 60) -> bytes:
    """A simple PDF of the text in Courier, one text line per PDF line.

    The text stays uncompressed, so it's real text a reader can select and the
    seed's test can read back. Only ASCII is allowed.
    """
    text.encode("ascii")
    rows = text.rstrip("\n").split("\n")
    pages = [rows[i : i + lines_per_page] for i in range(0, len(rows), lines_per_page)] or [[]]
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    catalog = add(b"")  # filled in below
    pages_obj = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    kids = []
    for page_rows in pages:
        ops = ["BT", "/F1 9.5 Tf", "12 TL", "40 752 Td"]
        for row in page_rows:
            ops.append(f"({_pdf_escape(row)}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("ascii")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page = add(
            (
                f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>"
            ).encode("ascii")
        )
        kids.append(page)
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode("ascii")
    objects[pages_obj - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    ).encode("ascii")
    info = add(f"<< /Title ({_pdf_escape(title)}) /Producer (FundTrail seed generator) >>".encode())

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        catalog,
        info,
        xref,
    )
    return bytes(out)
