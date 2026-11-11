"""The small sample: a grant whose timeline starts with its award letter.

Its first scheduled events are the award letter and then the ledger file. Each
ledger line arrives at the later of the ledger's arrival and 00:00 UTC on its
posting date (decision 0023), so the last two lines, posting later,
arrive when the clock reaches them, and their invoices are already on file.
The other evidence follows a few minutes after the ledger. Three files are
marked for the user to deliver (ruling 44): from their date, FOR_USER_AT, each
waits under the timeline's Now, with Get the file and Deliver for me, until the
user delivers it. The clock never delivers it.

The answer key assumes the user actions in `user_actions.json`: confirm the
award letter's terms, and deliver the three marked files by upload on their
date. Content is a placeholder until the samples' content is decided.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from images import Row, put_image, receipt
from model import Grant, Ordinary, at
from names import (
    DEPARTMENT,
    HARDWARE,
    HARDWARE_ADDRESS,
    KITTREDGE,
    LIONEL,
    OWEN,
    SAMPLES,
    SENSORS_DIVISION,
    SENSORS_LISTING,
    SENSORS_TITLE,
    TANNERY,
    UNIVERSITY,
    VALLEY,
    VALLEY_AIRPORT,
    VALLEY_FARM,
    VALLEY_INN,
    lines,
)
from ordinary import Trip, award_letter, put, trip
from render import eml, forwarded, invoice, money, sentence, short

TITLE = SENSORS_TITLE
SUPPLIES = "55016 Lab Instruments and Supplies"
GRANTS_INBOX = SAMPLES.grants_inbox

LETTER_AT = at(date(2026, 11, 16), 17, 30)
CONFIRM = at(date(2026, 11, 16), 17, 40)
LEDGER_AT = at(date(2026, 11, 16), 17, 45)
FILES_AT = at(date(2026, 11, 16), 17, 50)
FOR_USER_AT = at(date(2026, 11, 18), 17, 0)


def build() -> Grant:
    g = Grant("nitrate-sensors", "SYN-2511958", date(2025, 9, 1), date(2028, 8, 31))
    g.typeset = True
    g.org = SAMPLES
    rng = random.Random(2511958)
    award_letter(
        g,
        title=TITLE,
        award_date=date(2025, 8, 12),
        arrives=LETTER_AT,
        confirm_at=CONFIRM,
        personnel=[OWEN],
        program_officer=LIONEL,
        conditions=(
            "This award is subject to the NSF Grant General Conditions (GC-1) effective "
            "October 1, 2024, and to the terms of this notice."
        ),
        description=(
            f"The National Science Foundation hereby awards a standard grant to {UNIVERSITY} "
            "for support of the project described in the proposal referenced above. This "
            "amendment funds a new project for the period of performance shown below. The "
            "project builds low-cost sensors that measure nitrate in groundwater wells on "
            f"{VALLEY} farms."
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
        division=SENSORS_DIVISION,
        listing=SENSORS_LISTING,
    )
    g.starts_at = LETTER_AT
    g.ledger_at = LEDGER_AT
    g.docs[-1].note = "The award letter arrives. It's the first thing on the sample's timeline."

    file_times = iter(FILES_AT + timedelta(minutes=i) for i in range(20))
    for_the_user: list[str] = []

    def purchase(
        number: str,
        dated: date,
        posting: date,
        described: str,
        charged: int,
        items,
        shipping: int,
        as_email: bool,
        for_user: bool = False,
        by_gmail_at: datetime | None = None,
    ):
        seller = TANNERY if number.startswith(TANNERY.prefix) else KITTREDGE
        text, total = invoice(
            vendor=seller.name,
            vendor_address=seller.address,
            vendor_email=seller.email,
            number=number,
            dated=dated,
            attn=OWEN.name,
            department=DEPARTMENT,
            project_ref=f"{g.award_number}, nitrate sensors",
            items=lines(*items),
            shipping_cents=shipping,
            po=f"PO-{dated:%y}-{rng.randint(1000, 9999)}",
            org=SAMPLES,
            account=seller.account,
        )
        assert total == charged, f"{number}: {total} isn't the {charged} charged"
        vendor = seller.name
        arrives = FOR_USER_AT if for_user else by_gmail_at or next(file_times)
        deliver = "user" if for_user else None
        if as_email:
            name = f"email_invoice_{number}.eml"
            sent = by_gmail_at or at(dated, 22, 10)
            body = f"Invoice {number} for {g.award_number}.\n\n{OWEN.first}\n\n" + forwarded(
                sender=(f"{vendor} Billing", seller.email),
                at=sent - timedelta(hours=3),
                subject=f"Invoice {number}",
                to=OWEN.email,
                body=text,
            )
            g.doc(
                name,
                eml(
                    sender=(OWEN.name, OWEN.email),
                    to=GRANTS_INBOX,
                    at=sent,
                    subject=f"Fwd: Invoice {number}",
                    message_id=f"fwd-{number.lower()}@halden.example",
                    body=body,
                ),
                arrives,
                "gmail" if by_gmail_at else "upload",
                sender=OWEN.email if by_gmail_at else None,
                note=f"Invoice {number}, forwarded by email before its ledger line posts."
                if by_gmail_at
                else f"Invoice {number}, an email saved as a file.",
                deliver=deliver,
            )
        else:
            name = f"invoice_{number}.pdf"
            put(
                g,
                name,
                text,
                f"Invoice {number}",
                arrives,
                "upload",
                look=seller.look,
                note=sentence(f"Invoice {number} from {vendor}"),
                deliver=deliver,
            )
        ln = g.line(
            dated, posting, total, short(described), SUPPLIES, vendor=vendor, reference=number
        )
        g.record("bill", name, total=str(total), dated=dated.isoformat(), vendor=vendor)
        g.link(name, ln, total)
        g.budget(ln, "Materials and Supplies")
        g.answer(ln, "allowable", "supports")
        g.ordinary.append(Ordinary(ln, [name]))
        if for_user:
            for_the_user.append(name)
        return ln

    charges = [
        purchase(
            "EES-5531",
            date(2025, 10, 14),
            date(2025, 10, 21),
            "Nitrate ion-selective electrode, Microcontroller board, Sensor cable, 5 m",
            220250,
            [
                ("Nitrate ion-selective electrode", 4, 36500),
                ("Microcontroller board", 6, 3850),
                ("Sensor cable, 5 m", 10, 2875),
                ("Electrode filling solution, 125 mL", 4, 2250),
                ("Waterproof cable glands, 10 pack", 5, 2200),
            ],
            2400,
            False,
        ),
        purchase(
            "EES-6012",
            date(2026, 2, 9),
            date(2026, 2, 17),
            "Sensor housing, PVC, machined, O-ring kit",
            107975,
            [
                ("Sensor housing, PVC, machined", 8, 11200),
                ("O-ring kit", 2, 3450),
                ("Housing end caps, threaded, PVC", 8, 1200),
            ],
            1875,
            False,
        ),
        purchase(
            "ESS-31877",
            date(2026, 4, 20),
            date(2026, 4, 28),
            "Nitrate standard solution, 1000 ppm, Ionic strength adjuster, 500 mL",
            32150,
            [
                ("Nitrate standard solution, 1000 ppm", 3, 7950),
                ("Ionic strength adjuster, 500 mL", 2, 2650),
                ("Volumetric flasks, 100 mL, class A, 2 pack", 1, 3000),
            ],
            0,
            True,
        ),
    ]

    # A field trip: the trip template's files arrive in the trip's own time, so move
    # them to the upload afterwards.
    before = len(g.docs)
    charges.append(
        trip(
            g,
            rng,
            Trip(
                "valley-wells-2026",
                f"installing sensors in {VALLEY} wells",
                VALLEY_FARM,
                VALLEY_AIRPORT,
                date(2026, 6, 8),
                3,
                21800,
                3200,
                VALLEY_INN,
                14200,
                date(2026, 5, 11),
                "EXV3JM",
                fare_lines=(
                    ("Base fare", 20447),
                    ("U.S. transportation tax", 1533),
                    ("U.S. flight segment tax", 1000),
                    ("Passenger facility charges", 900),
                    ("September 11th security fee", 1120),
                ),
                ticket="0002605513097",
                night_lines=(
                    ("Room, standard queen", 12800),
                    ("Transient occupancy tax", 1280),
                    ("Tourism assessment", 120),
                ),
            ),
            traveler=OWEN,
        )
    )
    for d in g.docs[before:]:
        d.at = next(file_times)
        d.source = "upload"
        d.sender = None
        if d.name.endswith(".eml"):
            d.note = "The airline receipt email for the field trip, saved as a file."

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
    rows = [
        Row(HARDWARE.upper(), align="center"),
        *[Row(line, style="small", align="center") for line in HARDWARE_ADDRESS],
        Row(rule=True),
        Row("11/02/2026  14:37", "REG 3"),
        Row("TRANS 008214", "CASHIER 12"),
        Row(rule=True),
    ]
    for d, q, p in items:
        # A line bought more than once prints its count and price under its name.
        rows.append(Row(d, money(q * p), style="small"))
        if q > 1:
            rows.append(Row(f"  {q} @ {money(p)}", style="small"))
    rows += [
        Row(rule=True),
        Row("SUBTOTAL", money(subtotal)),
        Row("TAX 9.25%", money(tax)),
        Row("TOTAL", money(total), style="big"),
        Row(rule=True),
        Row("VISA ************3310", style="small"),
        Row("AUTH 71082C   SALE", style="small"),
        Row("CUSTOMER COPY", style="small", align="center"),
        Row("THANK YOU FOR SHOPPING", style="small", align="center"),
    ]
    photo_name = "hardware_receipt.jpg"
    put_image(
        g,
        photo_name,
        receipt(photo_name, rows, seed=2511958),
        FOR_USER_AT,
        "upload",
        note="A phone photo of a paper receipt for well fittings, bought on the department card.",
        deliver="user",
    )
    for_the_user.append(photo_name)
    ln = g.line(
        date(2026, 11, 2),
        date(2026, 11, 9),
        total,
        "Well fittings, card purchase",
        SUPPLIES,
        vendor=HARDWARE,
        reference="PCARD-2611-0042",
    )
    g.record("bill", photo_name, total=str(total), dated="2026-11-02", vendor=HARDWARE)
    g.link(photo_name, ln, total)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "supports")
    g.ordinary.append(Ordinary(ln, [photo_name]))
    charges.append(ln)

    # Two orders whose lines post later in the timeline, with their invoices on file.
    charges.append(
        purchase(
            "EES-7420",
            date(2026, 11, 12),
            date(2026, 11, 24),
            "Sensor circuit board, assembled",
            187400,
            [
                ("Sensor circuit board, assembled", 10, 16200),
                ("Pin header kit, 2.54 mm", 10, 800),
                ("Conformal coating, per board", 10, 1500),
            ],
            2400,
            False,
        )
    )
    charges.append(
        purchase(
            "ESS-32410",
            date(2026, 11, 13),
            date(2026, 12, 7),
            "Nitrate standard solution, 1000 ppm",
            37050,
            [
                ("Nitrate standard solution, 1000 ppm", 4, 7950),
                ("pH buffer set, 4, 7 and 10, 500 mL", 1, 4000),
            ],
            1250,
            True,
            by_gmail_at=at(date(2026, 11, 19), 17, 20),
        )
    )
    g.highlights["award_letter.pdf"] = "Terms tied to their passages"
    g.highlights["email_invoice_ESS-32410.eml"] = "Invoice before its line"
    g.highlights[photo_name] = "Receipt photo you deliver"

    for name in sorted(for_the_user):
        g.deliver_file(
            name,
            FOR_USER_AT,
            "The user brings in a file marked for them, by upload, on its date.",
        )
    g.expect_ordinary()
    return g
