"""The seed pack for adding a grant from scratch (decision 0024).

A folder of files the user drops in: an award letter, a ledger, emails,
invoices and a receipt photo. The ledger's last two lines post after the
demo's opening date, so the clock releases them, and their invoices are
already in the pack, waiting unlinked.

The key assumes this script, in the demo workspace, on the opening date: the
user uploads the award letter, confirms its terms, uploads the ledger and then
the rest of the files. Ledger lines already past their posting date arrive
when the ledger is uploaded (decision 0023).
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from model import EVIDENCE_COMPLETE, Grant, at
from ordinary import GRANTS_INBOX, Person, Trip, award_letter, trip
from photo import photo
from render import eml, forwarded, invoice, money, pdf, sentence, short

EMERY = Person("Emery Testwell", "emery.testwell@university.example", "Principal Investigator")
KAI = Person("Kai Officer", "kai.officer@funder.example")
TITLE = "Low-Cost Nitrate Sensors for Example Valley Groundwater"
DEPARTMENT = "Department of Earth and Ocean Sciences"
SUPPLIES = "55016 Lab Instruments and Supplies"

ELECTRONICS = (
    "Example Electronics Supply",
    "300 Example Circuit, Example City, CA 94007",
    "invoices@electronicssupply.example",
)

UPLOAD_LETTER = at(date(2026, 11, 16), 17, 30)
CONFIRM = at(date(2026, 11, 16), 17, 40)
UPLOAD_LEDGER = at(date(2026, 11, 16), 17, 45)
UPLOAD_FILES = at(date(2026, 11, 16), 17, 50)


def build() -> Grant:
    g = Grant("nitrate-sensors", "SYN-2511958", date(2025, 9, 1), date(2028, 8, 31))
    rng = random.Random(2511958)
    award_letter(
        g,
        title=TITLE,
        award_date=date(2025, 8, 12),
        arrives=UPLOAD_LETTER,
        confirm_at=CONFIRM,
        personnel=[EMERY],
        program_officer=KAI,
        conditions=(
            "This award is subject to the NSF Grant General Conditions (GC-1) effective "
            "October 1, 2024, and to the terms of this notice."
        ),
        description=(
            "This amendment funds a new project for the period of performance shown "
            "below. The project builds low-cost sensors that measure nitrate in "
            "groundwater wells on Example Valley farms."
        ),
        budget=[
            ("E. Travel", 600000, "travel", [("Domestic", 600000, "travel")]),
            (
                "G. Other Direct Costs",
                3400000,
                "other_direct_costs",
                [("Materials and Supplies", 3400000, "materials_and_supplies")],
            ),
        ],
        name="award_letter.pdf",
        as_pdf=True,
    )
    g.docs[-1].note = "The user starts a new grant by uploading its award letter."
    g.accountant[-1]["note"] = "The user confirms every term read from the award letter."

    file_times = iter(UPLOAD_FILES + timedelta(minutes=i) for i in range(20))

    def purchase(number: str, dated: date, posting: date, items, shipping: int, as_email: bool):
        text, total = invoice(
            vendor=ELECTRONICS[0] if number.startswith("EES") else "Example Scientific Supply",
            vendor_address=ELECTRONICS[1]
            if number.startswith("EES")
            else "55 Example Road, Example Town, CA 94010",
            vendor_email=ELECTRONICS[2]
            if number.startswith("EES")
            else "billing@scisupply.example",
            number=number,
            dated=dated,
            attn=EMERY.name,
            department=DEPARTMENT,
            project_ref=f"{g.award_number}, nitrate sensors",
            items=items,
            shipping_cents=shipping,
            po=f"PO-{dated:%y}-{rng.randint(1000, 9999)}",
        )
        vendor = ELECTRONICS[0] if number.startswith("EES") else "Example Scientific Supply"
        arrives = next(file_times)
        if as_email:
            name = f"email_invoice_{number}.eml"
            sent = at(dated, 22, 10)
            body = f"Invoice {number} for {g.award_number}.\n\nEmery\n\n" + forwarded(
                sender=(
                    f"{vendor} Billing",
                    "billing@scisupply.example"
                    if vendor.endswith("Scientific Supply")
                    else ELECTRONICS[2],
                ),
                at=sent - timedelta(hours=3),
                subject=f"Invoice {number}",
                to=EMERY.email,
                body=text,
            )
            g.doc(
                name,
                eml(
                    sender=(EMERY.name, EMERY.email),
                    to=GRANTS_INBOX,
                    at=sent,
                    subject=f"Fwd: Invoice {number}",
                    message_id=f"fwd-{number.lower()}@university.example",
                    body=body,
                ),
                arrives,
                "upload",
                note=f"Invoice {number}, saved from email and uploaded.",
            )
        else:
            name = f"invoice_{number}.pdf"
            g.doc(
                name,
                pdf(text, title=f"Invoice {number}"),
                arrives,
                "upload",
                note=sentence(f"Invoice {number} from {vendor}"),
                text=text,
            )
        desc = short(", ".join(d for d, _, _ in items))
        ln = g.line(dated, posting, total, desc, SUPPLIES, vendor=vendor, reference=number)
        g.record("bill", name, total=str(total), dated=dated.isoformat(), vendor=vendor)
        g.link(name, ln, total)
        g.budget(ln, "Materials and Supplies")
        g.answer(ln, "allowable", "supports")
        return ln

    lines = [
        purchase(
            "EES-5531",
            date(2025, 10, 14),
            date(2025, 10, 21),
            [
                ("Nitrate ion-selective electrode", 4, 41500),
                ("Microcontroller board", 6, 3850),
                ("Sensor cable, 5 m", 10, 2875),
            ],
            2400,
            False,
        ),
        purchase(
            "EES-6012",
            date(2026, 2, 9),
            date(2026, 2, 17),
            [("Sensor housing, PVC, machined", 8, 12400), ("O-ring kit", 2, 3450)],
            1875,
            False,
        ),
        purchase(
            "ESS-31877",
            date(2026, 4, 20),
            date(2026, 4, 28),
            [
                ("Nitrate standard solution, 1000 ppm", 3, 8950),
                ("Ionic strength adjuster, 500 mL", 2, 2650),
            ],
            0,
            True,
        ),
    ]

    # A field trip: the trip template's files arrive in the trip's own time, so move
    # them to the upload afterwards.
    before = len(g.docs)
    lines.append(
        trip(
            g,
            rng,
            Trip(
                "valley-wells-2026",
                "installing sensors in Example Valley wells",
                "Example Valley Research Farm, Example Valley, CA",
                "EXV",
                date(2026, 6, 8),
                3,
                21800,
                3200,
                "Example Valley Motor Inn",
                14200,
                date(2026, 5, 11),
                "EXV3JM",
            ),
            traveler=EMERY,
        )
    )
    for d in g.docs[before:]:
        d.at = next(file_times)
        d.source = "upload"
        d.sender = None
        if d.name.endswith(".eml"):
            d.note = "The airline receipt email for the field trip, saved and uploaded."

    # A hardware store purchase on the department card: the receipt is a phone photo.
    items = [
        ("PVC PIPE 1IN X 10FT", 2, 897),
        ("PVC CAP 1IN", 8, 129),
        ("PIPE CEMENT 8OZ", 1, 948),
        ("ZIP TIES 100PK", 2, 699),
        ("HOSE CLAMPS 10PK", 3, 849),
    ]
    subtotal = sum(q * p for _, q, p in items)
    tax = (subtotal * 925 + 5000) // 10000
    total = subtotal + tax
    photo_lines = [
        "EXAMPLE HARDWARE & SUPPLY",
        "412 EXAMPLE AVE",
        "EXAMPLE CITY CA 94002",
        "",
        "11/02/2026   14:37   REG 3",
        "",
        *[f"{d:<20} {q} @ {p / 100:.2f}" for d, q, p in items],
        "",
        f"SUBTOTAL {money(subtotal):>17}",
        f"TAX 9.25% {money(tax):>16}",
        f"TOTAL {money(total):>20}",
        "",
        "VISA ****3310",
        "THANK YOU FOR SHOPPING",
    ]
    photo_name = "hardware_receipt.jpg"
    g.doc(
        photo_name,
        photo(photo_name, photo_lines, seed=2511958),
        next(file_times),
        "upload",
        note="A phone photo of a paper receipt for well fittings, bought on the department card.",
        text="\n".join(photo_lines),
    )
    ln = g.line(
        date(2026, 11, 2),
        date(2026, 11, 9),
        total,
        "Well fittings, card purchase",
        SUPPLIES,
        vendor="Example Hardware & Supply",
        reference="PCARD-2611-0042",
    )
    g.record(
        "bill", photo_name, total=str(total), dated="2026-11-02", vendor="Example Hardware & Supply"
    )
    g.link(photo_name, ln, total)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "supports")
    lines.append(ln)

    # Two orders placed before the opening date that post after it.
    lines.append(
        purchase(
            "EES-7420",
            date(2026, 11, 12),
            date(2026, 11, 24),
            [("Sensor circuit board, assembled", 10, 18500)],
            2400,
            False,
        )
    )
    lines.append(
        purchase(
            "ESS-32410",
            date(2026, 11, 13),
            date(2026, 12, 7),
            [("Nitrate standard solution, 1000 ppm", 4, 8950)],
            1250,
            True,
        )
    )

    for ln in g.lines:
        posting = at(ln.posting_date, 0, 0)
        ln.arrives = max(posting, UPLOAD_LEDGER)
        if posting > UPLOAD_LEDGER:
            ln.note = "Posts after the opening date. The clock releases it, and its invoice is "
            ln.note += "already on file."
        b_at = max(ln.arrives + timedelta(hours=1), at(ln.arrives.date(), 12))
        if b_at < UPLOAD_FILES + timedelta(minutes=20):
            b_at = at(ln.arrives.date(), 19)
        g.bucket(ln, b_at, EVIDENCE_COMPLETE)
    return g
