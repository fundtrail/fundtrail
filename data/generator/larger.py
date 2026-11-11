"""The larger sample: one grant's whole life, from its award letter to sign-off.

About 30 charges. Most are ordinary and clear on their own. Twelve highlights
each show a part of the app the others don't (the sample content brief, ruling
58). Each highlight's events carry a short `highlight` label in timeline.json,
on the event where the highlight is whole, and a scripted step that is the
highlight's own carries the same label (ruling 77):

 1. The award letter: terms tied to their passages, confirmed.
 2. An invoice emailed before its ledger line posts: it waits, then links.
 3. A taxi receipt photo the user delivers; the trip's expense report rides along.
 4. A $10,000 invoice shared with another award: 56 of 96 samples, $5,833.33,
    and the agent's suggestion about the rest waits. (Decision 0021: kept in
    shared_invoice() so it's easy to change.)
 5. The PI's own conference fee on participant support, and her own "approved"
    email: Possible conflict.
 6. A charge after the end date, cleared once an extension, dated before the
    old end date and found in Drive, is confirmed.
 7. A vendor's email from an unknown address, held until let in, with a cost
    that isn't allowed; a correcting line moves the charge off (Reversed).
    (Decision 0020: kept in held_vendor_invoice() so it's easy to change.)
 8. Spending goes over a budget line and the award's total; accepted with a
    note; a notice adding money raises the limit.
 9. Closeout: the notice of expiration, the closeout review, and sign-off with
    two items open and a note that names them.
10. The same invoice twice: emailed, then a scan in Drive.
11. One effort report clears six salary lines.
12. A bill under its charge: the item still open at sign-off.

The grant, people, amounts and dates are the builder's picks.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from demo import RTC, SUPPLIES_ACCOUNT
from images import Photo, Row, Scan, Stamp, invoice_scan, put_image, receipt
from model import (
    EVIDENCE_COMPLETE,
    MISSING_EVIDENCE,
    POSSIBLE_CONFLICT,
    Grant,
    Ordinary,
    at,
    business_day,
)
from names import (
    CALDER,
    DEPARTMENT,
    ESTUARIES_AIRPORT,
    ESTUARIES_CITY,
    ESTUARIES_HOTEL,
    ESTUARIES_MEETING,
    FALL_MEETING,
    FALL_MEETING_AIRPORT,
    FALL_MEETING_CITY,
    FALL_MEETING_HOTEL,
    GAIL,
    IMOGEN,
    ISOTOPE_FACILITY,
    KITTREDGE,
    LOOMIS,
    MAREN,
    MARINE_STATION,
    MARSH_DIVISION,
    MARSH_LISTING,
    MARSH_SITE,
    MARSH_TITLE,
    RENATA,
    SALTGRASS,
    SAMPLES,
    SHARED_LABS,
    SIMONE,
    SOCIETY,
    SOCIETY_EMAIL,
    SOCIETY_MEETING,
    TAXI,
    TAXI_CITY,
    TOBIAS,
    UNIVERSITY,
    UNIVERSITY_ADDRESS,
    lines,
)
from ordinary import (
    Trip,
    appointment_letter,
    award_letter,
    effort_report,
    months,
    put,
    recharges,
    supplies,
    trip,
)
from render import (
    award_notice,
    eml,
    extension_notice,
    forwarded,
    invoice,
    long_date,
    money,
    usage_statement,
)
from typeset import SYNTHETIC

SLUG = "salt-marsh-carbon"
AWARD = "SYN-2401835"
TITLE = MARSH_TITLE
GRANTS_INBOX = SAMPLES.grants_inbox
START, OLD_END, NEW_END = date(2024, 2, 1), date(2026, 7, 31), date(2027, 1, 31)
AWARD_DATE = date(2024, 1, 16)
OTHER_AWARD = "SYN-2507264"  # the award the shared kit's rest belongs to (another lab's)
LIMIT = 6000000  # the first increment's total obligated to date, in cents
POSTDOC_MONTHLY = 650000
# The rate agreement's Limited group (postdocs), fiscal year July 1, 2025 to June 30, 2026.
LIMITED_RATE = (15, 100)
BENEFITS_LIMITED = "53080 Benefit Assessment - Limited"
RATE_AGREEMENT = "rate_agreement_2025-05-28.pdf"
# The benefit check's table puts the Limited group's pay on 51232 (PR 219); the
# postdoc is in the Limited group.
POSTDOC_SALARY = "51232 Salaries-Limited Benefit Staff"
EMS = MARINE_STATION

# The budget of amendment 000 and of the increment, 001. Names are unique, so a
# budget line is found by its name.
BUDGET_000 = [
    (
        "B. Other Personnel",
        4000000,
        "other_personnel",
        [("Post Doctoral Scholars", 4000000, "other_personnel")],
    ),
    ("C. Fringe Benefits", 600000, "fringe_benefits", []),
    ("E. Travel", 400000, "travel", [("Domestic", 400000, "travel")]),
    ("F. Participant Support Costs", 100000, "participant_support", []),
    (
        "G. Other Direct Costs",
        900000,
        "other_direct_costs",
        [
            ("Materials and Supplies", 600000, "materials_and_supplies"),
            ("Other", 300000, "other_direct_costs_other"),
        ],
    ),
]
BUDGET_001 = [
    (
        "B. Other Personnel",
        3000000,
        "other_personnel",
        [("Post Doctoral Scholars", 3000000, "other_personnel")],
    ),
    ("C. Fringe Benefits", 400000, "fringe_benefits", []),
    ("E. Travel", 400000, "travel", [("Domestic", 400000, "travel")]),
    (
        "G. Other Direct Costs",
        2200000,
        "other_direct_costs",
        [
            ("Materials and Supplies", 1600000, "materials_and_supplies"),
            ("Other", 600000, "other_direct_costs_other"),
        ],
    ),
]

# The documents that arrive as paper: three scanned by the department, each a little
# crooked at its own angle, and one photographed with a phone (issue 312). None is a
# document a highlight's own result rests on. The invoices carry the department's
# received stamp, a tick and a pen scrawl, and the letter a scrawl for a signature. The
# marks state nothing.
PICTURES = {
    "invoice_INV-12655.pdf": Scan(seed=12655, turn=0.7),
    "invoice_EFG-56443.pdf": Scan(seed=56443, turn=-1.1),
    f"appointment_letter_{IMOGEN.name.split()[-1].lower()}.pdf": Scan(
        seed=2025, turn=0.4, stamp=False, tick=False, sign=True
    ),
    "hotel_folio_egu-2024.jpg": Photo(seed=2024),
}

DESCRIPTION = (
    f"The National Science Foundation hereby awards a continuing grant to {UNIVERSITY} for "
    "support of the project described in the proposal referenced above. This amendment "
    "funds the first increment for the period of performance shown below. The project "
    f"measures how fast salt marshes at {MARSH_SITE} bury carbon as sea level rises. Funds "
    "provided for participant support may not be diverted by the awardee to other categories "
    "of expense without the prior written approval of the cognizant NSF Program Officer."
)


def build() -> Grant:
    g = Grant(SLUG, AWARD, START, OLD_END, horizon=at(NEW_END + timedelta(days=60), 23, 59))
    g.typeset = True
    g.org = SAMPLES
    g.pictures = dict(PICTURES)
    rng = random.Random(2401835)
    g.agent_extras = {"rules": {}, "remainders": [], "duplicates": []}
    letter(g)
    ordinary_charges(g, rng)
    taxi_trip(g, rng)
    invoice_before_line(g)
    shared_invoice(g)
    own_fee(g)
    salaries(g)
    same_invoice_twice(g)
    bill_under_charge(g)
    held_vendor_invoice(g)
    over_budget(g)
    extension(g)
    closeout(g)
    g.expect_ordinary()
    check_spending(g)
    return g


# ---------------------------------------------------------------- 1. the award letter


def letter(g: Grant) -> None:
    award_letter(
        g,
        title=TITLE,
        award_date=AWARD_DATE,
        arrives=at(date(2024, 1, 18), 17),
        confirm_at=at(date(2024, 1, 19), 18),
        personnel=[MAREN, TOBIAS],
        program_officer=RENATA,
        conditions=RTC,
        description=DESCRIPTION,
        budget=BUDGET_000,
        approval_rule=True,
        intended_cents=12000000,
        instrument="Continuing Grant",
        highlight="Terms tied to their passages",
        name="award_letter.pdf",
        division=MARSH_DIVISION,
        listing=MARSH_LISTING,
    )


# ---------------------------------------------------------------- ordinary charges

# The ordinary purchases' lines, by invoice number, in place of the ones the seed
# draws: the same subtotal, with the lines a real order of this kind carries. An item
# has one unit price at a vendor, on every invoice.
SUPPLY_LINES = {
    "INV-12655": lines(
        ("Sediment core liners, 50 count", 1, 16400),
        ("Nitrile gloves, powder free, medium, 10 boxes", 1, 8400),
    ),
    "INV-77772": lines(
        ("Cryovials, 2 mL, 500 count", 2, 11250),
        ("Ethanol, 200 proof, 4 L", 2, 15600),
        ("Cryogenic storage boxes, 81 place, 5 pack", 1, 7250),
        ("Cryogenic labels, 1000 count", 1, 4000),
    ),
    "ESS-35630": lines(
        ("Crucibles, porcelain, 50 count", 1, 12900),
        ("Crucible lids, porcelain, 50 count", 1, 6000),
    ),
    "ESS-20042": lines(
        ("Crucibles, porcelain, 50 count", 1, 12900),
        ("Crucible tongs, stainless, 9 in", 2, 3000),
    ),
    "ESS-11567": lines(
        ("Balance calibration weights, set", 1, 31000),
        ("Weighing boats, aluminum, 250 count", 2, 3600),
        ("Forceps, anti-static, stainless", 2, 2400),
    ),
    "EFG-56443": lines(
        ("Field notebooks, waterproof, 12 pack", 5, 7200),
        ("Waders, chest, size L", 3, 18900),
        ("Dry bags, 20 L, 4 pack", 3, 8800),
        ("Wading boots, size 10", 2, 6400),
        ("Wader repair kit", 4, 1200),
    ),
    "EFG-89662": lines(
        ("Waders, chest, size L", 2, 18900),
        ("Dry bags, 20 L, 4 pack", 1, 8800),
        ("Sediment corer replacement head", 3, 42500),
        ("Piston seals, corer, 10 pack", 5, 8500),
    ),
}
# The isotope facility's statements, by number: the analysis and the sample
# preparation it bills with it, at one rate for each service.
ISOTOPE_ROWS = {
    "SIF-2408-98": [
        ("Total organic carbon, per sample", 8, 1250),
        ("Sample grinding and weighing, per sample", 8, 625),
    ],
    "SIF-2509-82": [
        ("Total organic carbon, per sample", 22, 1250),
        ("Sample grinding and weighing, per sample", 18, 625),
    ],
    "SIF-2610-70": [
        ("Carbon and nitrogen isotopes, per sample", 15, 1800),
        ("Tin capsule packing, per sample", 16, 450),
    ],
}


def fare(base_cents: int, transportation_tax_cents: int) -> tuple[tuple[str, int], ...]:
    """A domestic round trip's fare as an airline itemizes it: the base fare, the
    transportation tax on it, and the three fixed charges."""
    return (
        ("Base fare", base_cents),
        ("U.S. transportation tax", transportation_tax_cents),
        ("U.S. flight segment tax", 1000),
        ("Passenger facility charges", 900),
        ("September 11th security fee", 1120),
    )


def ordinary_charges(g: Grant, rng: random.Random) -> None:
    supplies(
        g,
        rng,
        vendors=[CALDER, KITTREDGE, SALTGRASS],
        dates=[
            date(2024, 3, 12),
            date(2024, 6, 18),
            date(2025, 3, 11),
            date(2025, 8, 19),
            date(2026, 4, 14),
            date(2026, 9, 15),
            date(2026, 12, 8),
        ],
        attn=MAREN,
        project_ref=f"{AWARD}, salt marsh carbon burial",
        account=SUPPLIES_ACCOUNT,
        forwarder=MAREN,
        lines_for=SUPPLY_LINES,
    )
    recharges(
        g,
        rng,
        facility=ISOTOPE_FACILITY,
        unit="Campus Core Facilities",
        prefix="SIF",
        service_months=[date(2024, 8, 31), date(2025, 9, 30), date(2026, 10, 31)],
        services=[
            ("Carbon and nitrogen isotopes, per sample", 1800),
            ("Total organic carbon, per sample", 1250),
        ],
        qty=(12, 40),
        pi=MAREN,
        rows_for=ISOTOPE_ROWS,
    )
    trip(
        g,
        rng,
        Trip(
            "estuaries-2026",
            f"{ESTUARIES_MEETING}, talk on marsh cores",
            ESTUARIES_CITY,
            ESTUARIES_AIRPORT,
            date(2026, 5, 11),
            3,
            41200,
            5200,
            ESTUARIES_HOTEL,
            22900,
            date(2026, 3, 30),
            "EXR8MV",
            fare_lines=fare(40353, 3027),
            ticket="0002614408831",
            night_lines=(
                ("Room, standard queen", 19900),
                ("Room occupancy tax", 2250),
                ("Convention center fee", 750),
            ),
        ),
        traveler=MAREN,
    )


# ---------------------------------------------------------------- 3. a receipt photo


def taxi_trip(g: Grant, rng: random.Random) -> None:
    rows = [
        Row(TAXI.upper(), style="big", align="center"),
        Row(TAXI_CITY, style="small", align="center"),
        Row(rule=True),
        Row("CAB 118", "DRIVER 2207"),
        Row("TRIP 004417", "12/09/2024"),
        Row("START 17:38", "END 18:15"),
        Row("DIST 24.6 MI", "RATE 1"),
        Row(rule=True),
        Row(f"FROM: {FALL_MEETING_AIRPORT} AIRPORT", style="small"),
        Row(f"TO: {FALL_MEETING_HOTEL.upper()}", style="small"),
        Row(rule=True),
        Row("METER FARE", "$44.50"),
        Row("AIRPORT ACCESS FEE", "$4.50"),
        Row("TOLLS", "$3.00"),
        Row(rule=True),
        Row("TOTAL", "$52.00", style="big"),
        Row(rule=True),
        Row("CARD ************4417", style="small"),
        Row("AUTH 06214B   SALE", style="small"),
        Row("CUSTOMER COPY", style="small", align="center"),
        Row("THANK YOU", style="small", align="center"),
    ]
    name = "taxi_receipt_egu_2024.jpg"
    taxi = put_image(
        g,
        name,
        receipt(name, rows, seed=118),
        at(date(2024, 12, 30), 18),
        "upload",
        note="The PI's phone photo of the paper taxi receipt: hers to deliver.",
        deliver="user",
    )
    g.highlights[name] = "Receipt photo you deliver"
    g.deliver_file(
        name,
        at(date(2024, 12, 30), 18),
        "The PI uploads her taxi receipt photo on its date.",
        g.highlights[name],
    )
    g.record("bill", name, total="5200", dated="2024-12-09", vendor=TAXI)
    trip(
        g,
        rng,
        Trip(
            "egu-2024",
            f"{FALL_MEETING}, poster",
            FALL_MEETING_CITY,
            FALL_MEETING_AIRPORT,
            date(2024, 12, 9),
            4,
            38600,
            4800,
            FALL_MEETING_HOTEL,
            18900,
            date(2024, 10, 28),
            "EXK2PD",
            extra=(f"Taxi, airport to hotel, {TAXI}", 5200, taxi),
            fare_lines=fare(37563, 2817),
            ticket="0002418770254",
            night_lines=(
                ("Room, standard queen", 16400),
                ("State and city lodging tax", 1837),
                ("Tourism improvement fee", 663),
            ),
        ),
        traveler=MAREN,
    )


# ---------------------------------------------------------------- 2. invoice before its line


def invoice_before_line(g: Grant) -> None:
    text, total = invoice(
        vendor=CALDER.name,
        vendor_address=CALDER.address,
        vendor_email=CALDER.email,
        number="INV-20514",
        dated=date(2025, 2, 6),
        attn=MAREN.name,
        department=DEPARTMENT,
        project_ref=f"{AWARD}, salt marsh carbon burial",
        items=lines(
            ("Sediment core liners, 50 count", 1, 16400),
            ("Sample bags, sterile, 500 count", 1, 9600),
            ("Core liner end caps, 100 count", 1, 4600),
            ("Labeling tape, 19 mm, 12 rolls", 1, 3800),
        ),
        shipping_cents=1250,
        po="PO-25-1102",
        org=SAMPLES,
        account=CALDER.account,
    )
    assert total == 35650
    arrives = at(date(2025, 2, 10), 18, 20)
    name = "invoice_INV-20514.eml"
    body = f"Invoice INV-20514 for {AWARD}, for the files.\n\n{MAREN.first}\n\n" + forwarded(
        sender=(f"{CALDER.name} Billing", CALDER.email),
        at=at(date(2025, 2, 6), 23, 5),
        subject="Invoice INV-20514",
        to=MAREN.email,
        body=text,
    )
    g.doc(
        name,
        eml(
            sender=(MAREN.name, MAREN.email),
            to=GRANTS_INBOX,
            at=arrives,
            subject="Fwd: Invoice INV-20514",
            message_id="fwd-inv-20514@halden.example",
            body=body,
        ),
        arrives,
        "gmail",
        sender=MAREN.email,
        note="The invoice arrives before its ledger line exists, and waits unlinked.",
    )
    ln = g.line(
        date(2025, 2, 6),
        date(2025, 2, 18),
        total,
        "Core liners, sample bags",
        SUPPLIES_ACCOUNT,
        vendor=CALDER.name,
        reference="INV-20514",
        note="The line posts eight days after its invoice arrived. They link now.",
    )
    # The highlight sits where the charge posts, so the charge is on screen (ruling 77).
    g.highlights[ln.line_id] = "Invoice before its line"
    g.record("bill", name, total=str(total), dated="2025-02-06", vendor=CALDER.name)
    g.link(name, ln, total)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "supports")
    g.ordinary.append(Ordinary(ln, [name]))


# ---------------------------------------------------------------- 4. a shared invoice


def shared_invoice(g: Grant) -> None:
    """Decision 0021 (unreviewed): this grant's part of a shared bill, on an email's
    basis, with the agent's suggestion about the rest waiting on the bill."""
    text, total = invoice(
        vendor=LOOMIS.name,
        vendor_address=LOOMIS.address,
        vendor_email=LOOMIS.email,
        number="EGS-20931",
        dated=date(2025, 5, 12),
        attn=MAREN.name,
        department=DEPARTMENT,
        project_ref=f"{SHARED_LABS}, shared order",
        items=lines(("16S library prep kit, 96 reactions", 1, 1000000)),
        po="PO-25-3381",
        org=SAMPLES,
        account=LOOMIS.account,
    )
    assert total == 1000000
    inv = "invoice_EGS-20931.pdf"
    put(
        g,
        inv,
        text,
        "Invoice EGS-20931",
        at(date(2025, 5, 13), 17, 45),
        "upload",
        look=LOOMIS.look,
        note="The shared kit's invoice.",
    )
    sent = at(date(2025, 5, 14), 21, 12)
    body = "\n".join(
        [
            f"Hi {GAIL.first},",
            "",
            f"The {LOOMIS.name} invoice EGS-20931, for $10,000.00, is for one",
            "96-reaction library prep kit that two projects shared. 56 of the 96",
            f"samples were marsh cores for {AWARD}, and the other 40 samples were",
            f"field samples for {OTHER_AWARD}, {SIMONE.name}'s award. Please split the",
            "cost on that basis.",
            "",
            "Thanks,",
            MAREN.first,
        ]
    )
    note = "email_kit_split_basis.eml"
    g.doc(
        note,
        eml(
            sender=(MAREN.name, MAREN.email),
            to=GRANTS_INBOX,
            at=sent,
            subject="Splitting invoice EGS-20931 between two awards",
            message_id="kit-split-egs-20931@halden.example",
            body=body,
        ),
        sent,
        "gmail",
        sender=MAREN.email,
        note="The email that gives the basis: 56 of the 96 samples.",
    )
    ln = g.line(
        date(2025, 5, 12),
        date(2025, 5, 19),
        583333,
        "16S library prep kit, shared",
        SUPPLIES_ACCOUNT,
        vendor=LOOMIS.name,
        reference="EGS-20931",
        note="This grant's part of the shared $10,000.00 invoice: $5,833.33, for 56 of the "
        "96 samples.",
    )
    g.highlights[ln.line_id] = "Shared invoice, 56 of 96"
    g.record("bill", inv, total="1000000", dated="2025-05-12", vendor=LOOMIS.name)
    g.record("note", note)
    g.link(inv, ln, 583333)
    g.link(note, ln)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "supports")
    g.bucket(ln, at(date(2025, 5, 19), 12), EVIDENCE_COMPLETE)
    g.agent_extras["remainders"].append((inv, note, OTHER_AWARD))


# ---------------------------------------------------------------- 5. the PI's own fee


def own_fee(g: Grant) -> None:
    receipt = "\n".join(
        [
            SOCIETY.upper(),
            f"{SOCIETY_MEETING} 2025, June 23 to 26, 2025",
            "",
            "REGISTRATION RECEIPT",
            "",
            "Confirmation: REG-2025-0311",
            "Receipt date: June 2, 2025",
            f"Registrant: {MAREN.name}, {UNIVERSITY}",
            "Registration category: Faculty member, full meeting",
            "",
            f"  {'Registration, full meeting, member rate':<40}{money(59500):>10}",
            f"  {'Abstract submission fee':<40}{money(5500):>10}",
            f"  {'Total paid':<40}{money(65000):>10}",
            "",
            "Paid by: university card ending 2290",
        ]
    )
    receipt_at = at(date(2025, 6, 4), 17, 40)
    body = (
        f"{GAIL.first},\n\nReceipt for my registration at the {SOCIETY_MEETING}. Please\n"
        f"charge it to the participant support line on {AWARD}.\n\n{MAREN.first}\n\n"
        + forwarded(
            sender=(SOCIETY, SOCIETY_EMAIL),
            at=at(date(2025, 6, 2), 18, 2),
            subject="Your registration receipt, REG-2025-0311",
            to=MAREN.email,
            body=receipt,
        )
    )
    name = "registration_receipt_reg-2025-0311.eml"
    g.doc(
        name,
        eml(
            sender=(MAREN.name, MAREN.email),
            to=GRANTS_INBOX,
            at=receipt_at,
            subject="Fwd: Your registration receipt, REG-2025-0311",
            message_id="fwd-reg-2025-0311@halden.example",
            body=body,
        ),
        receipt_at,
        "gmail",
        sender=MAREN.email,
        note="The PI forwards the receipt for her own conference registration.",
    )
    fee = g.line(
        date(2025, 6, 2),
        date(2025, 6, 9),
        65000,
        f"Conference registration - {MAREN.last_first} - {SOCIETY_MEETING}",
        "56714 Participant Support-Other",
        vendor=SOCIETY,
        reference="REG-2025-0311",
        note="The PI's own conference fee, posted to participant support.",
    )
    approval = "\n".join(
        [
            f"{GAIL.first},",
            "",
            f"Approved. Please charge my registration for the {SOCIETY_MEETING}",
            f"to the participant support line on {AWARD}.",
            "",
            MAREN.name,
            f"Principal Investigator, {AWARD}",
        ]
    )
    forward_at = at(date(2025, 9, 15), 19, 5)
    body = (
        f"{GAIL.first},\n\nFor the files on the registration charge on participant support, "
        f"here\nis my approval from June.\n\n{MAREN.first}\n\n"
        + forwarded(
            sender=(MAREN.name, MAREN.email),
            at=at(date(2025, 6, 1), 17, 14),
            subject="Registration on participant support",
            to=f"{GAIL.name} <{GAIL.email}>",
            body=approval,
        )
    )
    approval_name = "approval_forward_registration.eml"
    g.doc(
        approval_name,
        eml(
            sender=(MAREN.name, MAREN.email),
            to=GRANTS_INBOX,
            at=forward_at,
            subject="Fwd: Registration on participant support",
            message_id="fwd-registration-approval@halden.example",
            body=body,
        ),
        forward_at,
        "gmail",
        sender=MAREN.email,
        note='The PI forwards her own email saying "Approved": the wrong approver, and the '
        "wrong channel.",
    )
    g.highlights[approval_name] = "Own fee, own approval"
    g.record("bill", name, total="65000", dated="2025-06-02", vendor=SOCIETY)
    g.record("approval", approval_name, approver_email=MAREN.email, approved_on="2025-06-01")
    g.link(name, fee, 65000)
    g.link(approval_name, fee)
    g.answer(fee, "allowable", "contradicts")
    g.agent_extras["rules"][fee.line_id] = "NSF-PARTICIPANT-NOT-STAFF"
    g.bucket(fee, at(date(2025, 6, 9), 12), POSSIBLE_CONFLICT)
    g.bucket(fee, forward_at + timedelta(hours=1), POSSIBLE_CONFLICT)


# ---------------------------------------------------------------- 11. one report, six lines


def salaries(g: Grant) -> None:
    appt = f"appointment_letter_{IMOGEN.name.split()[-1].lower()}.pdf"
    appointment_letter(
        g,
        name=appt,
        person=IMOGEN,
        title="Postdoctoral Scholar",
        pi=MAREN,
        start=date(2025, 7, 1),
        end=date(2025, 12, 31),
        monthly_cents=POSTDOC_MONTHLY,
        dated=date(2025, 6, 9),
        accepted=date(2025, 6, 12),
        arrives=at(date(2025, 6, 20), 18),
        work="the carbon analysis of the marsh cores collected under this award.",
        project_title=TITLE,
    )
    month_ends = months(date(2025, 7, 1), date(2025, 12, 31))
    report = f"effort_report_{IMOGEN.name.split()[-1].lower()}_2025_07.pdf"
    effort_report(
        g,
        name=report,
        person=IMOGEN,
        title="Postdoctoral Scholar",
        pi=MAREN,
        period=(date(2025, 7, 1), date(2025, 12, 31)),
        salary=[(m, POSTDOC_MONTHLY) for m in month_ends],
        certified=date(2026, 2, 17),
        arrives=at(date(2026, 2, 19), 18),
        project_title=TITLE,
    )
    g.highlights[report] = "One report, six salary lines"
    rate_agreement(g)
    benefit_cents = POSTDOC_MONTHLY * LIMITED_RATE[0] // LIMITED_RATE[1]
    assert POSTDOC_MONTHLY * LIMITED_RATE[0] % LIMITED_RATE[1] == 0
    for me in month_ends:
        posting = business_day(me + timedelta(days=3))
        ln = g.line(
            me,
            posting,
            POSTDOC_MONTHLY,
            f"Salary - {IMOGEN.last_first} - Postdoctoral Scholar - {me:%b %Y}",
            POSTDOC_SALARY,
            reference=f"PAY-{me:%Y-%m}",
        )
        g.link(appt, ln)
        g.link(report, ln)
        g.budget(ln, "Post Doctoral Scholars")
        g.answer(ln, "allowable", "supports")
        g.ordinary.append(Ordinary(ln, [appt, report]))
        # Background, not a highlight: the benefit assessed on that month's salary, at
        # the rate agreement's Limited rate for the fiscal year it was earned. It
        # clears when its salary line does.
        ben = g.line(
            me,
            posting,
            benefit_cents,
            f"Benefits - {IMOGEN.last_first} - Postdoctoral Scholar - {me:%b %Y}",
            BENEFITS_LIMITED,
            reference=f"PAY-{me:%Y-%m}",
        )
        # Code fills its "Benefit rate" item from the confirmed rate and the salary
        # line, with no link (ruling 61), and it waits on its salary line.
        g.budget(ben, "Fringe Benefits")
        g.ordinary.append(Ordinary(ben, [RATE_AGREEMENT, appt, report]))


def rate_agreement(g: Grant) -> None:
    """The university's fringe benefit rate agreement, laid out like a real one:
    a fixed rate per employee group and fiscal year (July 1 to June 30)."""
    groups = [
        ("35.20", "Academic"),
        ("15.00", "Limited"),
        ("5.00", "No Benefit Eligibility"),
        ("44.00", "Staff"),
        ("2.50", "Student"),
    ]
    fy25 = [
        ("34.80", "Academic"),
        ("14.60", "Limited"),
        ("4.50", "No Benefit Eligibility"),
        ("43.00", "Staff"),
        ("2.90", "Student"),
    ]
    rows = [f"{'TYPE':<7}{'FROM':<12}{'TO':<12}{'RATE(%)':<9}{'LOCATION':<10}APPLICABLE TO"]
    rows += [
        f"{'FIXED':<7}{'07/01/2024':<12}{'06/30/2025':<12}{r:<9}{'All':<10}{who}" for r, who in fy25
    ]
    rows += [
        f"{'FIXED':<7}{'07/01/2025':<12}{'06/30/2026':<12}{r:<9}{'All':<10}{who}"
        for r, who in groups
    ]
    rows += [
        f"{'PROV.':<7}{'07/01/2026':<12}Until Amended  Use same rates and conditions as those",
        "                         cited for fiscal year ending June 30, 2026",
    ]
    text = "\n".join(
        [
            "EIN: 00-SAMPLE",
            f"ORGANIZATION: {UNIVERSITY}",
            UNIVERSITY_ADDRESS,
            "Date: 05/28/2025",
            "FILING REF.: The preceding agreement was dated 04/10/2024",
            "",
            "COLLEGES AND UNIVERSITIES RATE AGREEMENT",
            "",
            "The rates approved in this agreement are for use on grants, contracts and other",
            "agreements with the Federal Government, subject to the conditions in Section III.",
            "",
            "SECTION I: FRINGE BENEFIT RATES**",
            "",
            *rows,
            "",
            "** DESCRIPTION OF FRINGE BENEFITS RATE BASE:",
            "Salaries and wages excluding vacation and catastrophic leave.",
            "",
            "SECTION II: SPECIAL REMARKS",
            "",
            "TREATMENT OF FRINGE BENEFITS:",
            "Fringe benefits are charged using the rate for the employee's group in the fiscal",
            "year the salary was earned, posted to the same fund as the salary.",
            "Postdoctoral scholars are in the Limited group.",
            "",
            "SECTION III: GENERAL",
            "",
            "A. LIMITATIONS: The rates in this agreement apply to a given grant, contract or",
            "other agreement only to the extent that funds are available.",
            "",
            f"BY THE INSTITUTION: {UNIVERSITY}",
            "ON BEHALF OF THE GOVERNMENT: Cognizant Federal Agency, Cost Allocation Services",
            "Signed: Director, Cost Allocation Services, 05/28/2025",
            "",
            f"ORGANIZATION: {UNIVERSITY}",
            "AGREEMENT DATE: 05/28/2025",
        ]
    )
    put(
        g,
        RATE_AGREEMENT,
        text,
        "Colleges and Universities Rate Agreement",
        at(date(2025, 6, 16), 18),
        "upload",
        note="The university's fringe benefit rate agreement, for the fiscal year from "
        "July 1, 2025.",
    )
    # Each fixed row is a rate term (ruling 61): its group, its rate as a fraction,
    # and the dates it's in effect. The accountant confirms them once.
    g.confirm(RATE_AGREEMENT, at(date(2025, 6, 17), 17), "The user confirms the benefit rates.")
    for (from_, to), rows_ in (
        (("2024-07-01", "2025-06-30"), fy25),
        (("2025-07-01", "2026-06-30"), groups),
    ):
        for r, who in rows_:
            g.record(
                "rate",
                RATE_AGREEMENT,
                name=who,
                rate=str(Decimal(r) / 100),
                applies_to=who.casefold().replace(" ", "_"),
                effective_from=from_,
                effective_to=to,
                dated="2025-05-28",
            )
    # The provisional row: from July 1, 2026 until amended, each group at its fiscal
    # year 2026 rate. One term per group with no end, as the agent writes it (PR 232).
    for r, who in groups:
        g.record(
            "rate",
            RATE_AGREEMENT,
            name=who,
            rate=str(Decimal(r) / 100),
            applies_to=who.casefold().replace(" ", "_"),
            effective_from="2026-07-01",
            dated="2025-05-28",
        )


# ---------------------------------------------------------------- 10. the same invoice twice


def same_invoice_twice(g: Grant) -> None:
    text, total = invoice(
        vendor=KITTREDGE.name,
        vendor_address=KITTREDGE.address,
        vendor_email=KITTREDGE.email,
        number="ESS-55120",
        dated=date(2025, 10, 6),
        attn=MAREN.name,
        department=DEPARTMENT,
        project_ref=f"{AWARD}, salt marsh carbon burial",
        items=lines(
            ("Crucibles, porcelain, 50 count", 2, 12900),
            ("Tin capsules, 5 x 9 mm, 1000 count", 4, 9875),
            ("Crucible lids, porcelain, 50 count", 2, 6000),
        ),
        shipping_cents=1875,
        po="PO-25-4410",
        org=SAMPLES,
        account=KITTREDGE.account,
    )
    assert total == 79175
    first = "invoice_ESS-55120.eml"
    sent = at(date(2025, 10, 8), 17, 30)
    body = f"Invoice ESS-55120 for {AWARD}, for the files.\n\n{MAREN.first}\n\n" + forwarded(
        sender=(f"{KITTREDGE.name} Billing", KITTREDGE.email),
        at=at(date(2025, 10, 6), 22, 0),
        subject="Invoice ESS-55120",
        to=MAREN.email,
        body=text,
    )
    g.doc(
        first,
        eml(
            sender=(MAREN.name, MAREN.email),
            to=GRANTS_INBOX,
            at=sent,
            subject="Fwd: Invoice ESS-55120",
            message_id="fwd-ess-55120@halden.example",
            body=body,
        ),
        sent,
        "gmail",
        sender=MAREN.email,
        note="Invoice ESS-55120, forwarded by email.",
    )
    ln = g.line(
        date(2025, 10, 6),
        date(2025, 10, 14),
        total,
        "Crucibles, tin capsules",
        SUPPLIES_ACCOUNT,
        vendor=KITTREDGE.name,
        reference="ESS-55120",
    )
    copy = "scan_invoice_ESS-55120.jpg"
    stamp = Stamp("RECEIVED", "OCT 08 2025", "EARTH & OCEAN SCIENCES", at=(0.10, 0.60))
    put_image(
        g,
        copy,
        invoice_scan(copy, text, seed=55120, stamp=stamp),
        at(date(2025, 11, 20), 19),
        "drive",
        note="A scan of the same invoice, saved to the lab's Drive folder six weeks later.",
    )
    g.highlights[copy] = "Same invoice twice"
    g.record("bill", first, total=str(total), dated="2025-10-06", vendor=KITTREDGE.name)
    g.record("bill", copy, total=str(total), dated="2025-10-06", vendor=KITTREDGE.name)
    g.link(first, ln, total)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "supports")
    g.ordinary.append(Ordinary(ln, [first]))
    g.agent_extras["duplicates"].append((copy, first))
    g.script(
        "decide_suggestion",
        at(date(2025, 11, 21), 17),
        "The accountant confirms the scan is a copy of the emailed invoice.",
        "Same invoice twice",
        suggestion="duplicate",
        decision="accept",
        file=copy,
    )


# ---------------------------------------------------------------- 12. a bill under its charge


def bill_under_charge(g: Grant) -> None:
    text, total = invoice(
        vendor=KITTREDGE.name,
        vendor_address=KITTREDGE.address,
        vendor_email=KITTREDGE.email,
        number="ESS-56204",
        dated=date(2025, 11, 3),
        attn=MAREN.name,
        department=DEPARTMENT,
        project_ref=f"{AWARD}, salt marsh carbon burial",
        items=lines(
            ("Sediment trap frames, stainless", 4, 25500),
            ("Sediment trap collection tubes, acrylic", 4, 4500),
        ),
        po="PO-25-4511",
        terms="net 30. Freight billed separately.",
        org=SAMPLES,
        account=KITTREDGE.account,
    )
    assert total == 120000
    name = "invoice_ESS-56204.pdf"
    put(
        g,
        name,
        text,
        "Invoice ESS-56204",
        at(date(2025, 11, 5), 18),
        "upload",
        look=KITTREDGE.look,
        note="Invoice ESS-56204, for $1,200.00.",
    )
    ln = g.line(
        date(2025, 11, 3),
        date(2025, 11, 12),
        126000,
        "Sediment trap frames, with freight",
        SUPPLIES_ACCOUNT,
        vendor=KITTREDGE.name,
        reference="ESS-56204",
        note="Charged $1,260.00: $60.00 of freight whose bill never arrives.",
    )
    g.highlights[ln.line_id] = "Bill under its charge"
    g.record("bill", name, total=str(total), dated="2025-11-03", vendor=KITTREDGE.name)
    g.link(name, ln, total)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "supports")
    g.bucket(ln, at(date(2025, 11, 12), 12), MISSING_EVIDENCE)
    g.bucket(ln, at(date(2027, 3, 10), 12), MISSING_EVIDENCE)


# ---------------------------------------------------------------- 7. a held vendor email


def held_vendor_invoice(g: Grant) -> None:
    """Decision 0020 (unreviewed): a correcting line moves the charge off the grant,
    so it shows as Reversed."""
    text, total = invoice(
        vendor=SALTGRASS.name,
        vendor_address=SALTGRASS.address,
        vendor_email=SALTGRASS.email,
        number="EFG-30418",
        dated=date(2026, 1, 7),
        attn=MAREN.name,
        department=DEPARTMENT,
        project_ref=f"{AWARD}, field crew, January sampling",
        items=lines(
            ("Field crew dinner with wine, after sampling", 1, 18400),
            ("Dry bags, 20 L, 4 pack", 1, 8800),
            ("Dry bags, 10 L, 4 pack", 2, 4400),
        ),
        org=SAMPLES,
        account=SALTGRASS.account,
    )
    assert total == 36000
    sent = at(date(2026, 1, 12), 19)
    name = "email_invoice_EFG-30418.eml"
    body = "\n".join(
        [
            "Hello,",
            "",
            "Please find our invoice EFG-30418 below for the January field crew order.",
            "",
            "Accounts",
            SALTGRASS.name,
            "",
            text,
        ]
    )
    g.doc(
        name,
        eml(
            sender=(f"{SALTGRASS.name} Accounts", SALTGRASS.email),
            to=GRANTS_INBOX,
            at=sent,
            subject="Invoice EFG-30418",
            message_id=f"inv-efg-30418@{SALTGRASS.email.split('@')[1]}",
            body=body,
        ),
        sent,
        "gmail",
        sender=SALTGRASS.email,
        note="The vendor emails from an address nobody on the grant uses: held until let in.",
    )
    let_in = at(date(2026, 1, 15), 17, 30)
    g.held[name] = let_in
    g.script(
        "let_in_mail",
        let_in,
        "The accountant lets in the vendor's held email.",
        "Held vendor email",
        file=name,
    )
    ln = g.line(
        date(2026, 1, 7),
        date(2026, 1, 13),
        total,
        "Field crew dinner, dry bags",
        SUPPLIES_ACCOUNT,
        vendor=SALTGRASS.name,
        reference="EFG-30418",
        note="The vendor's email with this charge's invoice is held until someone lets it "
        "in. The charge includes a dinner with wine, which an NSF award can't pay for.",
    )
    g.highlights[ln.line_id] = "Held vendor email"
    g.record("bill", name, total=str(total), dated="2026-01-07", vendor=SALTGRASS.name)
    g.link(name, ln, total)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "contradicts")
    g.agent_extras["rules"][ln.line_id] = "NSF-NEVER-ALCOHOL"
    g.bucket(ln, at(date(2026, 1, 13), 12), MISSING_EVIDENCE)
    g.bucket(ln, let_in + timedelta(hours=1), POSSIBLE_CONFLICT)

    just = "cost_transfer_justification_CT-26-0042.pdf"
    put(
        g,
        just,
        "\n".join(
            [
                UNIVERSITY.upper(),
                "COST TRANSFER JUSTIFICATION",
                "",
                "Transfer number: CT-26-0042",
                f"From award: {AWARD}",
                "To fund: Department fund EOD-2010",
                f"Ledger line moved: {ln.line_id}, {SALTGRASS.name} invoice EFG-30418, "
                f"{money(total)}",
                "",
                "Why the transfer is needed: The invoice includes a field crew dinner with wine,",
                "which the award can't pay for.",
                "Why the wrong fund was charged: The invoice was coded to the award with the",
                "January field supplies.",
                "How the expense relates to the project: The dry bags were for the award's field",
                "work and are charged again to the department fund with the dinner.",
                "",
                f"Prepared by: {GAIL.name}, March 5, 2026",
            ]
        )
        + "\n",
        "Cost transfer justification CT-26-0042",
        at(date(2026, 3, 6), 18),
        "upload",
        note="The written justification for moving the charge off the grant.",
    )
    fix = g.line(
        date(2026, 3, 6),
        date(2026, 3, 9),
        -total,
        f"Cost transfer off award - {SALTGRASS.name} EFG-30418",
        SUPPLIES_ACCOUNT,
        vendor=SALTGRASS.name,
        reference="CT-26-0042",
        note="The correcting line names the charge it moves off the grant.",
    )
    fix.original_line_id = ln.line_id
    g.highlights[fix.line_id] = "Moved off the grant"
    g.record("note", just)
    g.link(just, fix)
    g.budget(fix, "Materials and Supplies")
    g.answer(fix, "allowable", "supports")
    g.bucket(ln, at(date(2026, 3, 9), 12), "reversed")
    g.bucket(fix, at(date(2026, 3, 9), 12), EVIDENCE_COMPLETE)


# ---------------------------------------------------------------- 8. over budget


def over_budget(g: Grant) -> None:
    text, total = invoice(
        vendor=SALTGRASS.name,
        vendor_address=SALTGRASS.address,
        vendor_email=SALTGRASS.email,
        number="EFG-31207",
        dated=date(2026, 4, 27),
        attn=MAREN.name,
        department=DEPARTMENT,
        project_ref=f"{AWARD}, salt marsh carbon burial",
        items=lines(
            ("Sediment corer, piston type, 1 m", 1, 418000),
            ("Core extruder, 7 cm", 1, 52000),
            ("Corer extension rod, 1 m", 2, 12500),
        ),
        po="PO-26-2280",
        org=SAMPLES,
        account=SALTGRASS.account,
    )
    assert total == 495000
    name = "invoice_EFG-31207.pdf"
    put(
        g,
        name,
        text,
        "Invoice EFG-31207",
        at(date(2026, 4, 28), 18),
        "upload",
        look=SALTGRASS.look,
        note="Invoice EFG-31207, for the corer.",
    )
    ln = g.line(
        date(2026, 4, 27),
        date(2026, 5, 5),
        total,
        "Sediment corer, piston type",
        SUPPLIES_ACCOUNT,
        vendor=SALTGRASS.name,
        reference="EFG-31207",
        note="Spending passes the award's $60,000.00 obligated to date, and Materials "
        "and Supplies passes its line.",
    )
    g.highlights[ln.line_id] = "Over budget"
    g.record("bill", name, total=str(total), dated="2026-04-27", vendor=SALTGRASS.name)
    g.link(name, ln, total)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "supports")
    g.ordinary.append(Ordinary(ln, [name]))
    # The accountant accepts spending over the award's limit, with this note.
    g.script(
        "accept_reason",
        at(date(2026, 5, 6), 17),
        "The second increment of $60,000.00 is expected in June. The Program Officer "
        "confirmed it by phone on May 4.",
        "Over budget",
        check="budget",
        problem="over_limit",
    )
    notice_text = award_notice(
        award_number=AWARD,
        amendment_type="Increment",
        amendment_number="001",
        amendment_date=date(2026, 6, 10),
        award_date=AWARD_DATE,
        description="This amendment provides the second increment of funds for the period of "
        "performance shown below. Except as stated here, the award's terms are unchanged.",
        start=START,
        end=OLD_END,
        title=TITLE,
        instrument="Continuing Grant",
        obligated_cents=6000000,
        intended_cents=12000000,
        to_date_cents=12000000,
        personnel=[(MAREN.name, MAREN.role, MAREN.email), (TOBIAS.name, TOBIAS.role, TOBIAS.email)],
        program_officer=(RENATA.name, RENATA.email),
        conditions=RTC,
        budget=[(b[0], b[1], [(s[0], s[1]) for s in b[3]]) for b in BUDGET_001],
        org=SAMPLES,
        division=MARSH_DIVISION,
        listing=MARSH_LISTING,
    )
    notice = "notice_001_increment.pdf"
    put(
        g,
        notice,
        notice_text,
        f"Award notice {AWARD}, amendment 001",
        at(date(2026, 6, 12), 17),
        "upload",
        note="Amendment 001 adds $60,000.00: the award's limit rises to $120,000.00.",
    )
    g.highlights[notice] = "More money, a higher limit"
    g.confirm(
        notice,
        at(date(2026, 6, 15), 17),
        "The user confirms the increment's terms.",
        g.highlights[notice],
    )
    dated = "2026-06-10"
    g.record(
        "notice",
        notice,
        amendment_number="001",
        amendment_type="Increment",
        obligated_by_amendment="6000000",
        obligated_to_date="12000000",
        dated=dated,
    )
    for line, amount, category, subs in BUDGET_001:
        g.record(
            "budget_line",
            notice,
            name=line.split(". ", 1)[1],
            category=category,
            amount=str(amount),
            dated=dated,
        )
        for sub, sub_amount, sub_category in subs:
            g.record(
                "budget_line",
                notice,
                name=sub,
                category=sub_category,
                amount=str(sub_amount),
                dated=dated,
            )


# ---------------------------------------------------------------- 6. after the end date


def extension(g: Grant) -> None:
    text, total = usage_statement(
        facility=EMS,
        unit="Field Operations",
        number="EMS-2608-21",
        dated=date(2026, 9, 1),
        period="August 1, 2026 to August 31, 2026",
        pi=MAREN.name,
        award_number=AWARD,
        rows=[
            ("Research vessel time, per hour", 14, 17500),
            ("Vessel captain, per hour", 14, 5000),
        ],
        org=SAMPLES,
    )
    assert total == 315000
    name = "usage_statement_EMS-2608-21.pdf"
    put(
        g,
        name,
        text,
        "Usage statement EMS-2608-21",
        at(date(2026, 9, 2), 18, 10),
        "drive",
        note="The marine station's statement for August boat time, after the end date.",
    )
    ln = g.line(
        date(2026, 8, 31),
        date(2026, 9, 8),
        total,
        f"{EMS} - Aug 2026",
        "59009 Recharge-Other Expenses",
        vendor=EMS,
        reference="EMS-2608-21",
        note="Work done after the award's end date, July 31, 2026.",
    )
    g.record("bill", name, total=str(total), dated="2026-09-01")
    g.link(name, ln, total)
    g.budget(ln, "Other")
    g.answer(ln, "allowable", "supports")
    notice = extension_notice(
        award_number=AWARD,
        amendment_number="002",
        amendment_date=date(2026, 7, 15),
        start=START,
        old_end=OLD_END,
        new_end=NEW_END,
        title=TITLE,
        program_officer=(RENATA.name, RENATA.email),
        org=SAMPLES,
        division=MARSH_DIVISION,
    )
    notice_name = "extension_notice_002.pdf"
    arrives = at(date(2026, 9, 14), 16, 30)
    confirmed = at(date(2026, 9, 15), 17)
    put(
        g,
        notice_name,
        notice,
        f"Award notice {AWARD}, amendment 002",
        arrives,
        "drive",
        note="The extension notice, dated 16 days before the old end date, turns up in Drive.",
    )
    g.highlights[notice_name] = "Extension found in Drive"
    g.confirm(
        notice_name,
        confirmed,
        "The user confirms the new end date, January 31, 2027.",
        g.highlights[notice_name],
    )
    g.extensions.append((confirmed, NEW_END))
    g.record("period_of_performance", notice_name, end=NEW_END.isoformat(), dated="2026-07-15")
    g.record(
        "notice",
        notice_name,
        amendment_number="002",
        amendment_type="No Cost Extensions",
        dated="2026-07-15",
    )
    g.bucket(ln, at(date(2026, 9, 8), 12), POSSIBLE_CONFLICT)
    g.bucket(ln, arrives + timedelta(hours=1), POSSIBLE_CONFLICT)
    g.bucket(ln, confirmed + timedelta(hours=1), EVIDENCE_COMPLETE)


# ---------------------------------------------------------------- 9. closeout


def closeout(g: Grant) -> None:
    window = NEW_END - timedelta(days=90)
    notice = "notice_of_expiration.pdf"
    put(
        g,
        notice,
        "\n".join(
            [
                UNIVERSITY.upper(),
                "Contracts and Grants Accounting",
                "",
                "NOTICE OF EXPIRATION",
                "",
                f"Date: {long_date(window)}",
                f"Award: {AWARD}, {TITLE}",
                f"Principal investigator: {MAREN.name}",
                f"End date: {long_date(NEW_END)}",
                "",
                "This award ends in 90 days. Please review every charge for completeness,",
                "accuracy and allowability, and move any charge that doesn't belong to the",
                "award before the books close two months after the end date.",
            ]
        )
        + "\n",
        f"Notice of expiration, {AWARD}",
        at(window, 17),
        "upload",
        note="The university's 90-day notice: the closeout window opens.",
    )
    g.highlights[notice] = "Closeout"
    # The accountant signs off on the evidence report, with this note.
    g.script(
        "sign_off",
        at(date(2027, 3, 10), 18),
        "Two items are open. Invoice ESS-56204 covers $1,200.00 of the $1,260.00 charge, and "
        "the vendor's freight bill for $60.00 has been requested. The principal "
        "investigator's own $650.00 registration fee, charged to participant support, is "
        "still in question.",
        g.highlights[notice],
    )
    g.doc(
        "closeout_certification_receipt.txt",
        "\n".join(
            [
                UNIVERSITY.upper(),
                "Contracts and Grants Accounting",
                "",
                "AWARD CLOSEOUT CERTIFICATION RECEIVED",
                "",
                f"Award: {AWARD}",
                f"Date received: {long_date(date(2027, 3, 12))}",
                "The certification and its attachments are on file.",
                "",
                f"{SYNTHETIC} Not issued by any university.",
            ]
        )
        + "\n",
        at(date(2027, 3, 12), 17),
        "upload",
        note="The university's receipt for the Award Closeout Certification: the "
        "timeline's last event.",
    )


def check_spending(g: Grant) -> None:
    """Spending passes the first increment's limit at the corer, and not before."""
    corer = next(ln for ln in g.lines if ln.reference == "EFG-31207")
    before = sum(ln.amount_cents for ln in g.lines if g.line_arrival(ln) < g.line_arrival(corer))
    assert before <= LIMIT < before + corer.amount_cents, (before, LIMIT, corer.amount_cents)
