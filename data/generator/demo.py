"""The demo workspace's three grants, with the example situations written by hand.

Grant A, salt marsh carbon (SYN-2401835), runs through to closeout. Grant B,
coastal microbial genomics (SYN-2507264), is in the middle of its life. Grant C,
river delta sediment (SYN-2309472), passes its end date late in its timeline, and
its extension notice turns up after that.

The situations from docs/product.md, "Demo data (examples)":

- S1, Grant B: the professor's conference fee charged to participant support,
  and later their own "approved" email.
- S2, Grant C: work done after the end date, and an extension notice, signed
  before the old end date, that turns up in Drive.
- S3, a purchase shared by two grants, three ways: A and B split an invoice on
  an email's basis ("56 of 96 samples"), B and C on the invoice's own itemized
  lines, and A and C with nothing that gives the basis.
- S4, Grant B: a bill that arrives before its ledger line posts.

Grant B also has lab reagents filed on a participant support account, which
moves money out of participant support with no approval on file, so the award
letter's approval rule is exercised.

Everything else is ordinary, made by the templates in ordinary.py.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from model import (
    EVIDENCE_COMPLETE,
    NEEDS_HUMAN,
    POSSIBLE_CONFLICT,
    Grant,
    Ordinary,
    at,
)
from ordinary import (
    DEPARTMENT,
    GRANTS_INBOX,
    Person,
    Trip,
    Vendor,
    appointment_letter,
    award_letter,
    months,
    recharges,
    salary_series,
    spread,
    supplies,
    trip,
)
from photo import photo
from render import eml, extension_notice, forwarded, invoice, long_date, money, pdf

HORIZON = at(date(2027, 3, 31), 23, 59)

RTC = (
    "This award is subject to the Research Terms and Conditions and the NSF Agency "
    "Specific Requirements in effect on the award date, and to the terms of this notice."
)
GC1 = (
    "This award is subject to the NSF Grant General Conditions (GC-1) effective "
    "October 1, 2024, and to the terms of this notice."
)

HARPER = Person("Harper Fixture", "harper.fixture@university.example", "Principal Investigator")
SASHA = Person("Sasha Stub", "sasha.stub@university.example", "Co-Principal Investigator")
ROWAN = Person("Rowan Mockley", "rowan.mockley@university.example", "Postdoctoral Scholar")
KENDALL = Person("Kendall Dummy", "kendall.dummy@university.example", "Principal Investigator")
HARPER_CO = Person(HARPER.name, HARPER.email, "Co-Principal Investigator")
LOGAN = Person("Logan Synth", "logan.synth@university.example", "Graduate Student Researcher")
PARKER = Person("Parker Proxy", "parker.proxy@university.example", "Principal Investigator")
JULES = Person(
    "Jules Samplewell", "jules.samplewell@university.example", "Graduate Student Researcher"
)
JAMIE = Person("Jamie Program", "jamie.program@funder.example")
LEE = Person("Lee Reviewer", "lee.reviewer@funder.example")
PAT = Person("Pat Panel", "pat.panel@funder.example")
SAM_BURSAR = ("Sam Bursar", "sam.bursar@university.example")

LAB = Vendor(
    "Example Lab Supply Co.",
    "200 Example Parkway, Example City, CA 94001",
    "orders@labsupply.example",
    "INV",
    (
        ("Sediment core liners, 50 count", 24800),
        ("Nitrile gloves, medium, case of 1000", 8950),
        ("Pipette tips, 1000 uL, 10 racks", 6420),
        ("Sample bags, sterile, 500 count", 9600),
        ("Glass fiber filters, 47 mm, 100 count", 7380),
        ("Cryovials, 2 mL, 500 count", 11250),
        ("Ethanol, 200 proof, 4 L", 15600),
    ),
)
SCI = Vendor(
    "Example Scientific Supply",
    "55 Example Road, Example Town, CA 94010",
    "billing@scisupply.example",
    "ESS",
    (
        ("Sample bottles, acid washed, 125 mL, 72", 13440),
        ("Balance calibration weights, set", 21500),
        ("Crucibles, porcelain, 50 count", 18900),
        ("Hydrochloric acid, trace metal, 2.5 L", 16420),
        ("Tin capsules, 5 x 9 mm, 1000 count", 9875),
    ),
)
FIELD = Vendor(
    "Example Field Gear",
    "9 Example Wharf, Example Harbor, CA 94020",
    "accounts@fieldgear.example",
    "EFG",
    (
        ("Waders, chest, size L", 18900),
        ("Field notebooks, waterproof, 12 pack", 7200),
        ("Sediment corer replacement head", 42500),
        ("GPS unit batteries, 24 pack", 3600),
        ("Dry bags, 20 L, 4 pack", 8800),
    ),
)

SUPPLIES_ACCOUNT = "55016 Lab Instruments and Supplies"
POSTDOC_SALARY = "50120 Postdoctoral Scholar Salaries"
GSR_SALARY = "50310 Graduate Student Researcher Salaries"


def build() -> tuple[list[Grant], dict[str, list[str]]]:
    """The three grants, and the lines each leaves out of its key's buckets."""
    a = Grant(
        "salt-marsh-carbon", "SYN-2401835", date(2024, 2, 1), date(2027, 1, 31), horizon=HORIZON
    )
    b = Grant(
        "coastal-microbial-genomics",
        "SYN-2507264",
        date(2025, 7, 1),
        date(2028, 6, 30),
        horizon=HORIZON,
    )
    c = Grant(
        "river-delta-sediment", "SYN-2309472", date(2023, 9, 1), date(2026, 8, 31), horizon=HORIZON
    )
    left_out = {a.slug: [], b.slug: [], c.slug: []}
    grant_a(a, random.Random(2401835), left_out[a.slug])
    grant_b(b, random.Random(2507264), left_out[b.slug])
    grant_c(c, random.Random(2309472), left_out[c.slug])
    shared_costs(a, b, c)
    for g in (a, b, c):
        g.expect_ordinary()
    return [a, b, c], left_out


# ---------------------------------------------------------------- Grant A


A_TITLE = "Salt Marsh Carbon Burial at Example Point"


def grant_a(g: Grant, rng: random.Random, left_out: list[str]) -> None:
    award_letter(
        g,
        title=A_TITLE,
        award_date=date(2024, 1, 16),
        arrives=at(date(2024, 1, 18), 17),
        confirm_at=at(date(2024, 1, 19), 18),
        personnel=[HARPER, SASHA],
        program_officer=JAMIE,
        conditions=RTC,
        description=(
            "This amendment funds a new project for the period of performance shown "
            "below. The project measures how fast salt marshes at Example Point bury "
            "carbon as sea level rises."
        ),
        budget=[
            (
                "B. Other Personnel",
                18800000,
                "other_personnel",
                [("Post Doctoral Scholars", 18800000, "other_personnel")],
            ),
            ("C. Fringe Benefits", 4000000, "fringe_benefits", []),
            ("E. Travel", 800000, "travel", [("Domestic", 800000, "travel")]),
            (
                "G. Other Direct Costs",
                3800000,
                "other_direct_costs",
                [
                    ("Materials and Supplies", 2800000, "materials_and_supplies"),
                    ("Other", 1000000, "other_direct_costs_other"),
                ],
            ),
        ],
    )
    appointment_letter(
        g,
        name="appointment_letter_mockley.txt",
        person=ROWAN,
        title="Postdoctoral Scholar",
        pi=HARPER,
        start=date(2024, 2, 1),
        end=date(2026, 12, 31),
        monthly_cents=520000,
        dated=date(2024, 1, 8),
        accepted=date(2024, 1, 12),
        arrives=at(date(2024, 1, 25), 18),
        work="the analysis of salt marsh sediment cores for carbon burial rates.",
        project_title=A_TITLE,
    )
    salary_series(
        g,
        rng,
        person=ROWAN,
        title="Postdoctoral Scholar",
        salary_account=POSTDOC_SALARY,
        monthly_cents=520000,
        first=date(2024, 2, 1),
        last=date(2026, 12, 31),
        budget_line="Post Doctoral Scholars",
        appointments=[("appointment_letter_mockley.txt", date(2024, 2, 1), date(2026, 12, 31))],
        pi=HARPER,
        project_title=A_TITLE,
        horizon=HORIZON,
    )
    supplies(
        g,
        rng,
        vendors=[LAB, SCI, FIELD],
        dates=spread(rng, date(2024, 3, 1), date(2026, 9, 30), 16),
        attn=HARPER,
        project_ref=f"{g.award_number}, salt marsh carbon burial",
        account=SUPPLIES_ACCOUNT,
        forwarder=HARPER,
    )
    for t, traveler in (
        (
            Trip(
                "egu-2024",
                "Example Geophysical Union Fall Meeting, poster",
                "Example Summit Convention Center, Example Springs, CO",
                "EXS",
                date(2024, 12, 9),
                4,
                38600,
                4800,
                "Example Summit Hotel",
                18900,
                date(2024, 10, 28),
                "EXK2PD",
            ),
            HARPER,
        ),
        (
            Trip(
                "estuaries-2025",
                "Example Estuaries Conference, talk on marsh cores",
                "Example Harbor Convention Center, Example Harbor, MA",
                "EXH",
                date(2025, 11, 3),
                3,
                41200,
                5200,
                "Example Harbor Inn",
                22900,
                date(2025, 9, 22),
                "EXR8MV",
            ),
            ROWAN,
        ),
        (
            Trip(
                "marsh-field-2026",
                "field sampling at the Example Point marsh",
                "Example Point Field Station, Example Bayou, LA",
                "EXB",
                date(2026, 6, 15),
                5,
                32800,
                4400,
                "Example Bayou Lodge",
                13900,
                date(2026, 5, 4),
                "EXF4QT",
            ),
            ROWAN,
        ),
    ):
        trip(g, rng, t, traveler=traveler)
    recharges(
        g,
        rng,
        facility="Example Stable Isotope Facility",
        unit="Campus Core Facilities",
        prefix="SIF",
        service_months=sorted(rng.sample(months(date(2024, 5, 1), date(2026, 9, 30)), 9)),
        services=[
            ("Carbon and nitrogen isotopes, per sample", 1800),
            ("Total organic carbon, per sample", 1250),
        ],
        qty=(12, 48),
        pi=HARPER,
    )


# ---------------------------------------------------------------- Grant B


B_TITLE = "Coastal Microbial Genomics: Field Study and Training Workshop"
PARTICIPANTS = [
    "Bailey Trainee",
    "Cameron Novice",
    "Dakota Learner",
    "Ellis Fellow",
    "Frankie Scholar",
    "Gray Apprentice",
    "Hayden Intern",
    "Indigo Cadet",
]


def grant_b(g: Grant, rng: random.Random, left_out: list[str]) -> None:
    award_letter(
        g,
        title=B_TITLE,
        award_date=date(2025, 6, 18),
        arrives=at(date(2025, 6, 20), 17),
        confirm_at=at(date(2025, 6, 23), 17),
        personnel=[KENDALL, HARPER_CO],
        program_officer=LEE,
        conditions=GC1,
        description=(
            "This amendment funds a new project for the period of performance shown "
            "below. The project studies coastal sediment microbes and runs a summer "
            "training workshop for undergraduate participants. Participant support "
            "costs: funds budgeted for participant support may not be diverted by the "
            "awardee to other categories of expense without the prior written approval "
            "of the cognizant NSF Program Officer."
        ),
        budget=[
            (
                "B. Other Personnel",
                11200000,
                "other_personnel",
                [("Graduate Students", 11200000, "other_personnel")],
            ),
            ("C. Fringe Benefits", 300000, "fringe_benefits", []),
            ("E. Travel", 600000, "travel", [("Domestic", 600000, "travel")]),
            (
                "F. Participant Support Costs",
                2400000,
                "participant_support",
                [
                    ("Stipends", 1800000, "participant_support"),
                    ("Other", 600000, "participant_support"),
                ],
            ),
            (
                "G. Other Direct Costs",
                3500000,
                "other_direct_costs",
                [("Materials and Supplies", 3500000, "materials_and_supplies")],
            ),
        ],
        approval_rule=True,
    )
    appointment_letter(
        g,
        name="appointment_letter_synth.txt",
        person=LOGAN,
        title="Graduate Student Researcher",
        pi=KENDALL,
        start=date(2025, 9, 1),
        end=date(2027, 8, 31),
        monthly_cents=310000,
        dated=date(2025, 8, 4),
        accepted=date(2025, 8, 7),
        arrives=at(date(2025, 8, 11), 18),
        work="the DNA extraction and sequencing of the coastal sediment samples.",
        project_title=B_TITLE,
    )
    salary_series(
        g,
        rng,
        person=LOGAN,
        title="Graduate Student Researcher",
        salary_account=GSR_SALARY,
        monthly_cents=310000,
        first=date(2025, 9, 1),
        last=date(2027, 1, 31),
        budget_line="Graduate Students",
        appointments=[("appointment_letter_synth.txt", date(2025, 9, 1), date(2027, 8, 31))],
        pi=KENDALL,
        project_title=B_TITLE,
        horizon=HORIZON,
    )
    supplies(
        g,
        rng,
        vendors=[LAB, SCI],
        dates=spread(rng, date(2025, 8, 1), date(2026, 10, 31), 9)
        + spread(rng, date(2026, 12, 1), date(2027, 1, 22), 2),
        attn=KENDALL,
        project_ref=f"{g.award_number}, coastal microbial genomics",
        account=SUPPLIES_ACCOUNT,
        forwarder=KENDALL,
    )
    # A trip whose taxi receipt is a phone photo of the paper slip.
    taxi_lines = [
        "EXAMPLE CAB CO.",
        "CAB 214   DRIVER 5531",
        "02/23/2026   19:42",
        "FROM: EXR AIRPORT",
        "TO: EXAMPLE RIVERFRONT HOTEL",
        "",
        "FARE                $46.50",
        "TOTAL               $46.50",
        "",
        "PAID: CARD ****4417",
        "THANK YOU",
    ]
    taxi_name = "taxi_receipt_ocean_sciences_2026.jpg"
    taxi = g.doc(
        taxi_name,
        photo(taxi_name, taxi_lines, seed=2026),
        at(date(2026, 3, 2), 18, 30),
        "upload",
        note="A phone photo of the paper taxi receipt from the airport.",
        text="\n".join(taxi_lines),
    )
    g.record("bill", taxi_name, total="4650", dated="2026-02-23", vendor="Example Cab Co.")
    trip(
        g,
        rng,
        Trip(
            "ocean-sciences-2026",
            "Example Ocean Sciences Meeting, workshop results talk",
            "Example Riverfront Convention Center, Example River City, LA",
            "EXR",
            date(2026, 2, 23),
            4,
            35400,
            4600,
            "Example Riverfront Hotel",
            17900,
            date(2026, 1, 12),
            "EXN5WB",
            extra=("Taxi, airport to hotel, Example Cab Co.", 4650, taxi),
        ),
        traveler=LOGAN,
    )
    workshop_stipends(g)
    conference_fee(g)
    moved_out_of_participant_support(g)
    bill_before_line(g)


def workshop_stipends(g: Grant) -> None:
    """Eight ordinary participant stipends from the summer workshop.

    A stipend paid to a participant moves no money out of participant support, so
    the award letter's approval rule doesn't apply. The participant list and the
    payment record fill its checklist.
    """
    roster = "\n".join(
        [
            "UNIVERSITY OF EXAMPLE",
            "Coastal Microbes Summer Workshop 2026",
            f"Award {g.award_number}, {B_TITLE}",
            "",
            "PARTICIPANT LIST",
            "",
            "Workshop dates: July 13, 2026 to July 24, 2026",
            "Location: Example Point Field Station",
            "",
            "Participants (undergraduate students from other institutions):",
            *[f"  {i + 1}. {n}, Example State College" for i, n in enumerate(PARTICIPANTS)],
            "",
            "No participant is an employee of the University of Example or works on the",
            "project. Each participant receives a stipend of $750.00.",
            "",
            "Prepared by: Kendall Dummy, Principal Investigator",
            "Date: July 27, 2026",
        ]
    )
    g.doc(
        "workshop_participant_list.txt",
        roster + "\n",
        at(date(2026, 7, 27), 20),
        "upload",
        note="The workshop's participant list.",
    )
    rows = [f"  {n:<28}STP-26-07{i + 1:02d}{money(75000):>18}" for i, n in enumerate(PARTICIPANTS)]
    register = "\n".join(
        [
            "UNIVERSITY OF EXAMPLE",
            "Student Payments Office",
            "",
            "PARTICIPANT STIPEND PAYMENT RECORD",
            "",
            "Program: Coastal Microbes Summer Workshop 2026",
            f"Award: {g.award_number}",
            "Payment date: July 24, 2026",
            "",
            f"  {'Participant':<28}{'Payment':<12}{'Amount':>16}",
            *rows,
            "",
            f"  {'Total paid':<40}{money(600000):>16}",
        ]
    )
    g.doc(
        "workshop_stipend_payments.pdf",
        pdf(register, title="Stipend payments"),
        at(date(2026, 7, 31), 17, 15),
        "drive",
        note="The payment record for the workshop's stipends.",
        text=register,
    )
    g.record("note", "workshop_participant_list.txt")
    items = {}
    for i, n in enumerate(PARTICIPANTS):
        items[f"items[{i}].description"] = n
        items[f"items[{i}].amount"] = "75000"
    g.record("bill", "workshop_stipend_payments.pdf", total="600000", dated="2026-07-24", **items)
    for i, n in enumerate(PARTICIPANTS):
        first, last = n.split()
        ln = g.line(
            date(2026, 7, 24),
            date(2026, 7, 29),
            75000,
            f"Participant stipend - {last} {first[0]} - Coastal Microbes Workshop 2026",
            "56712 Participant Support-Stipends",
            vendor=n,
            reference=f"STP-26-07{i + 1:02d}",
        )
        g.link("workshop_participant_list.txt", ln)
        g.link("workshop_stipend_payments.pdf", ln, 75000)
        g.budget(ln, "Stipends")
        g.answer(ln, "allowable", "supports")
        g.ordinary.append(
            Ordinary(ln, ["workshop_participant_list.txt", "workshop_stipend_payments.pdf"])
        )


def conference_fee(g: Grant) -> None:
    """S1: the PI's own conference fee on participant support, then their own approval."""
    receipt_sent = at(date(2026, 3, 10), 18, 2)
    receipt_at = at(date(2026, 3, 12), 17, 40)
    receipt = "\n".join(
        [
            "EXAMPLE COASTAL SCIENCE SOCIETY",
            "Example Coastal Science Meeting 2026, April 20 to 23, 2026",
            "",
            "REGISTRATION RECEIPT",
            "",
            "Confirmation: REG-2026-0457",
            "Receipt date: March 10, 2026",
            f"Registrant: {KENDALL.name}, University of Example",
            "Registration category: Faculty member, full meeting",
            "",
            f"  {'Registration fee':<36}{money(65000):>12}",
            f"  {'Total paid':<36}{money(65000):>12}",
            "",
            "Paid by: university card ending 2290",
        ]
    )
    body = (
        "Sam,\n\n"
        "Receipt for my registration at the Example Coastal Science Meeting. Please\n"
        f"charge it to the participant support line on {g.award_number}.\n\n"
        "Kendall\n\n"
        + forwarded(
            sender=("Example Coastal Science Society", "registration@coastalsociety.example"),
            at=receipt_sent,
            subject="Your registration receipt, REG-2026-0457",
            to=KENDALL.email,
            body=receipt,
        )
    )
    name = "registration_receipt_reg-2026-0457.eml"
    g.doc(
        name,
        eml(
            sender=(KENDALL.name, KENDALL.email),
            to=GRANTS_INBOX,
            at=receipt_at,
            subject="Fwd: Your registration receipt, REG-2026-0457",
            message_id="fwd-reg-2026-0457@university.example",
            body=body,
        ),
        receipt_at,
        "gmail",
        sender=KENDALL.email,
        note="S1. The PI forwards the receipt for her own conference registration and asks for "
        "it to go on participant support.",
    )
    fee = g.line(
        date(2026, 3, 10),
        date(2026, 3, 17),
        65000,
        "Conference registration - Dummy K - Example Coastal Science Meeting",
        "56714 Participant Support-Other",
        vendor="Example Coastal Science Society",
        reference="REG-2026-0457",
        note="S1. The PI's own conference fee, posted to participant support.",
    )
    approved_at = at(date(2026, 3, 9), 17, 14)
    forward_at = at(date(2026, 11, 24), 19, 5)
    approval = "\n".join(
        [
            "Sam,",
            "",
            "Approved. Please charge my registration for the Example Coastal Science",
            f"Meeting to the participant support line on {g.award_number}.",
            "",
            "Kendall Dummy",
            f"Principal Investigator, {g.award_number}",
        ]
    )
    body = (
        "Sam,\n\n"
        "For the files on the registration charge on participant support, here\n"
        "is my approval from March.\n\n"
        "Kendall\n\n"
        + forwarded(
            sender=(KENDALL.name, KENDALL.email),
            at=approved_at,
            subject="Registration on participant support",
            to=f"{SAM_BURSAR[0]} <{SAM_BURSAR[1]}>",
            body=approval,
        )
    )
    approval_name = "approval_forward_registration.eml"
    g.doc(
        approval_name,
        eml(
            sender=(KENDALL.name, KENDALL.email),
            to=GRANTS_INBOX,
            at=forward_at,
            subject="Fwd: Registration on participant support",
            message_id="fwd-registration-approval@university.example",
            body=body,
        ),
        forward_at,
        "gmail",
        sender=KENDALL.email,
        note="S1. Months later, the PI forwards her own March email saying "
        '"Approved": the wrong approver, through the wrong channel.',
    )
    g.record(
        "bill", name, total="65000", dated="2026-03-10", vendor="Example Coastal Science Society"
    )
    g.record("approval", approval_name, approver_email=KENDALL.email, approved_on="2026-03-09")
    g.link(name, fee, 65000)
    g.link(approval_name, fee)
    g.answer(fee, "allowable", "contradicts")
    g.bucket(fee, at(date(2026, 3, 17), 12), POSSIBLE_CONFLICT)
    g.bucket(fee, at(date(2026, 11, 25), 12), POSSIBLE_CONFLICT)


def moved_out_of_participant_support(g: Grant) -> None:
    """Lab reagents filed on a participant support account, with no approval on file.

    The agent assigns them to Materials and Supplies, so money moves out of
    participant support: the award letter's rule asks for the Program Officer's
    approval, and the ledger's account disagrees with the budget line.
    """
    text, total = invoice(
        vendor=SCI.name,
        vendor_address=SCI.address,
        vendor_email=SCI.email,
        number="ESS-29944",
        dated=date(2026, 9, 14),
        attn=KENDALL.name,
        department=DEPARTMENT,
        project_ref=f"{g.award_number}, coastal microbial genomics",
        items=[
            ("DNA extraction kit, 50 preps", 2, 41800),
            ("PCR master mix, 5 mL", 3, 11200),
        ],
        po="PO-26-4471",
    )
    name = "invoice_ESS-29944.txt"
    g.doc(
        name,
        text,
        at(date(2026, 9, 16), 18, 25),
        "upload",
        note="The invoice for lab reagents that are later filed on participant support.",
    )
    ln = g.line(
        date(2026, 9, 14),
        date(2026, 9, 22),
        total,
        "DNA extraction kit, PCR master mix",
        "56714 Participant Support-Other",
        vendor=SCI.name,
        reference="ESS-29944",
        note="Lab reagents filed on participant support: money moved out of participant "
        "support with no approval on file.",
    )
    g.record("bill", name, total=str(total), dated="2026-09-14", vendor=SCI.name)
    g.link(name, ln, total)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "supports")
    g.bucket(ln, at(date(2026, 9, 22), 12), NEEDS_HUMAN)
    g.bucket(ln, at(date(2026, 12, 1), 12), NEEDS_HUMAN)


def bill_before_line(g: Grant) -> None:
    """S4: an invoice arrives two weeks before its ledger line posts."""
    text, total = invoice(
        vendor=LAB.name,
        vendor_address=LAB.address,
        vendor_email=LAB.email,
        number="INV-11872",
        dated=date(2026, 11, 18),
        attn=KENDALL.name,
        department=DEPARTMENT,
        project_ref=f"{g.award_number}, coastal microbial genomics",
        items=[
            ("Sample bags, sterile, 500 count", 2, 9600),
            ("Nitrile gloves, medium, case of 1000", 2, 8950),
        ],
        shipping_cents=1875,
        po="PO-26-5120",
    )
    arrives = at(date(2026, 11, 19), 18, 20)
    body = (
        f"Invoice INV-11872 for {g.award_number}, for the files. The order shipped today.\n\n"
        "Kendall\n\n"
        + forwarded(
            sender=("Example Lab Supply Co. Billing", LAB.email),
            at=at(date(2026, 11, 18), 23, 5),
            subject="Invoice INV-11872",
            to=KENDALL.email,
            body=text,
        )
    )
    name = "invoice_INV-11872.eml"
    g.doc(
        name,
        eml(
            sender=(KENDALL.name, KENDALL.email),
            to=GRANTS_INBOX,
            at=arrives,
            subject="Fwd: Invoice INV-11872",
            message_id="fwd-inv-11872@university.example",
            body=body,
        ),
        arrives,
        "gmail",
        sender=KENDALL.email,
        note="S4. The invoice arrives before its ledger line posts, and waits unlinked.",
    )
    ln = g.line(
        date(2026, 11, 18),
        date(2026, 12, 2),
        total,
        "Sample bags, sterile, 500 count, Nitrile gloves",
        SUPPLIES_ACCOUNT,
        vendor=LAB.name,
        reference="INV-11872",
        note="S4. The line posts after its invoice arrived. The agent links them now.",
    )
    g.record("bill", name, total=str(total), dated="2026-11-18", vendor=LAB.name)
    g.link(name, ln, total)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "supports")
    g.bucket(ln, at(date(2026, 12, 2), 12), EVIDENCE_COMPLETE)


# ---------------------------------------------------------------- Grant C


C_TITLE = "Sediment Transport in Example River Delta Channels"


def grant_c(g: Grant, rng: random.Random, left_out: list[str]) -> None:
    award_letter(
        g,
        title=C_TITLE,
        award_date=date(2023, 8, 10),
        arrives=at(date(2023, 8, 14), 17),
        confirm_at=at(date(2023, 8, 15), 17),
        personnel=[PARKER],
        program_officer=PAT,
        conditions=RTC,
        description=(
            "This amendment funds a new project for the period of performance shown "
            "below. The project measures how sediment moves through the channels of the "
            "Example River delta."
        ),
        budget=[
            (
                "B. Other Personnel",
                12500000,
                "other_personnel",
                [("Graduate Students", 12500000, "other_personnel")],
            ),
            ("C. Fringe Benefits", 400000, "fringe_benefits", []),
            ("E. Travel", 400000, "travel", [("Domestic", 400000, "travel")]),
            (
                "G. Other Direct Costs",
                4100000,
                "other_direct_costs",
                [
                    ("Materials and Supplies", 1700000, "materials_and_supplies"),
                    ("Other", 2400000, "other_direct_costs_other"),
                ],
            ),
        ],
    )
    for name, start, end, dated, accepted, arrives in (
        (
            "appointment_letter_samplewell_2023.txt",
            date(2023, 9, 1),
            date(2026, 8, 31),
            date(2023, 8, 1),
            date(2023, 8, 3),
            at(date(2023, 8, 21), 18),
        ),
        (
            "appointment_letter_samplewell_2026.txt",
            date(2026, 9, 1),
            date(2027, 8, 31),
            date(2026, 8, 20),
            date(2026, 8, 21),
            at(date(2026, 8, 25), 18),
        ),
    ):
        appointment_letter(
            g,
            name=name,
            person=JULES,
            title="Graduate Student Researcher",
            pi=PARKER,
            start=start,
            end=end,
            monthly_cents=290000,
            dated=dated,
            accepted=accepted,
            arrives=arrives,
            work="the field measurements and sediment trap analysis in the delta channels.",
            project_title=C_TITLE,
        )
    salary_series(
        g,
        rng,
        person=JULES,
        title="Graduate Student Researcher",
        salary_account=GSR_SALARY,
        monthly_cents=290000,
        first=date(2023, 9, 1),
        last=date(2027, 1, 31),
        budget_line="Graduate Students",
        appointments=[
            ("appointment_letter_samplewell_2023.txt", date(2023, 9, 1), date(2026, 8, 31)),
            ("appointment_letter_samplewell_2026.txt", date(2026, 9, 1), date(2027, 8, 31)),
        ],
        pi=PARKER,
        project_title=C_TITLE,
        horizon=HORIZON,
    )
    supplies(
        g,
        rng,
        vendors=[FIELD, LAB],
        dates=spread(rng, date(2023, 10, 1), date(2026, 7, 31), 10),
        attn=PARKER,
        project_ref=f"{g.award_number}, river delta sediment transport",
        account=SUPPLIES_ACCOUNT,
        forwarder=PARKER,
    )
    trip(
        g,
        rng,
        Trip(
            "sediment-workshop-2024",
            "Example Sediment Dynamics Workshop, talk",
            "Example Lakeside Conference Center, Example Lakes, WI",
            "EXL",
            date(2024, 10, 14),
            3,
            29800,
            3900,
            "Example Lakeside Inn",
            16400,
            date(2024, 9, 3),
            "EXL6HC",
        ),
        traveler=PARKER,
    )
    recharges(
        g,
        rng,
        facility="Example Marine Station",
        unit="Field Operations",
        prefix="EMS",
        service_months=sorted(rng.sample(months(date(2023, 11, 1), date(2026, 6, 30)), 6)),
        services=[("Research vessel time, per hour", 17500), ("Small boat time, per hour", 6500)],
        qty=(4, 16),
        pi=PARKER,
    )
    extension(g)


def extension(g: Grant) -> None:
    """S2: boat time after the old end date, then the extension notice turns up."""
    from render import usage_statement

    text, total = usage_statement(
        facility="Example Marine Station",
        unit="Field Operations",
        number="EMS-2609-14",
        dated=date(2026, 10, 1),
        period="September 1, 2026 to September 30, 2026",
        pi=PARKER.name,
        award_number=g.award_number,
        rows=[("Research vessel time, per hour", 18, 17500)],
    )
    name = "usage_statement_EMS-2609-14.txt"
    g.doc(
        name,
        text,
        at(date(2026, 10, 2), 18, 10),
        "drive",
        note="S2. The marine station's statement for September boat time, after the old end date.",
    )
    ln = g.line(
        date(2026, 9, 30),
        date(2026, 10, 6),
        total,
        "Example Marine Station - Sep 2026",
        "59009 Recharge-Other Expenses",
        vendor="Example Marine Station",
        reference="EMS-2609-14",
        note="S2. Work done after the end date in the award letter, August 31, 2026.",
    )
    g.record("bill", name, total=str(total), dated="2026-10-01")
    g.link(name, ln, total)
    g.budget(ln, "Other")
    g.answer(ln, "allowable", "supports")

    notice = extension_notice(
        award_number=g.award_number,
        amendment_number="001",
        amendment_date=date(2026, 8, 14),
        start=g.start,
        old_end=g.end,
        new_end=date(2027, 8, 31),
        title=C_TITLE,
        program_officer=(PAT.name, PAT.email),
    )
    notice_name = "extension_notice_001.txt"
    arrives = at(date(2026, 11, 20), 16, 30)
    confirmed = at(date(2026, 11, 23), 17)
    g.doc(
        notice_name,
        notice,
        arrives,
        "drive",
        note="S2. Weeks later, the extension notice, dated 17 days before the old "
        "end date, turns up in the PI's Drive folder.",
    )
    g.confirm(
        notice_name,
        confirmed,
        "The accountant confirms the new end date, August 31, 2027. In the demo the user "
        "does this.",
    )
    g.extensions.append((confirmed, date(2027, 8, 31)))
    g.record("period_of_performance", notice_name, end="2027-08-31", dated="2026-08-14")
    g.record(
        "notice",
        notice_name,
        amendment_number="001",
        amendment_type="No Cost Extensions",
        dated="2026-08-14",
    )
    g.bucket(ln, at(date(2026, 10, 6), 12), POSSIBLE_CONFLICT)
    g.bucket(ln, arrives + timedelta(hours=1), POSSIBLE_CONFLICT)
    g.bucket(ln, confirmed + timedelta(hours=1), EVIDENCE_COMPLETE)


# ---------------------------------------------------------------- shared costs


def shared_costs(a: Grant, b: Grant, c: Grant) -> None:
    """S3: three purchases, each shared by two grants. Each grant gets its own copy."""
    # S3a: A and B, split on an email's basis, 56 of 96 samples.
    text, total = invoice(
        vendor="Example Genomics Supply",
        vendor_address="410 Example Boulevard, Example City, CA 94003",
        vendor_email="billing@genomicssupply.example",
        number="EGS-20931",
        dated=date(2026, 5, 12),
        attn=HARPER.name,
        department=DEPARTMENT,
        project_ref="Fixture and Dummy labs, shared order",
        items=[("16S library prep kit, 96 reactions", 1, 1000000)],
        po="PO-26-3381",
    )
    assert total == 1000000
    inv = "invoice_EGS-20931.pdf"
    email_name = "email_kit_split_basis.eml"
    sent = at(date(2026, 5, 14), 21, 12)
    body = "\n".join(
        [
            "Hi Sam,",
            "",
            "The Example Genomics Supply invoice EGS-20931, for $10,000.00, is for one",
            "96-reaction library prep kit that our two projects shared. 56 of the 96",
            f"samples were marsh cores for {a.award_number}, and the other 40 samples were",
            f"workshop field samples for {b.award_number}. Please split the cost on that",
            "basis.",
            "",
            "Thanks,",
            "Harper",
        ]
    )
    for g, amount, posting in ((a, 583333, date(2026, 5, 19)), (b, 416667, date(2026, 5, 20))):
        g.doc(
            inv,
            pdf(text, title="Invoice EGS-20931"),
            at(date(2026, 5, 13), 17, 45),
            "upload",
            note="S3a. The shared kit's invoice. The other grant holds its own copy.",
            text=text,
        )
        g.doc(
            email_name,
            eml(
                sender=(HARPER.name, HARPER.email),
                to=GRANTS_INBOX,
                at=sent,
                subject="Splitting invoice EGS-20931 between two awards",
                message_id="kit-split-egs-20931@university.example",
                body=body,
                cc=(KENDALL.name, KENDALL.email),
            ),
            sent,
            "gmail",
            sender=HARPER.email,
            note="S3a. The email that gives the basis: 56 of the 96 samples.",
        )
        ln = g.line(
            date(2026, 5, 12),
            posting,
            amount,
            "16S library prep kit, shared",
            SUPPLIES_ACCOUNT,
            vendor="Example Genomics Supply",
            reference="EGS-20931",
            note=f"S3a. This grant's part of the shared $10,000.00 invoice: {money(amount)}.",
        )
        g.record("bill", inv, total="1000000", dated="2026-05-12", vendor="Example Genomics Supply")
        g.record("note", email_name)
        g.link(inv, ln, amount)
        g.link(email_name, ln)
        g.budget(ln, "Materials and Supplies")
        g.answer(ln, "allowable", "supports")
        g.bucket(ln, at(posting, 12), EVIDENCE_COMPLETE)

    # S3b: B and C, split on the invoice's own itemized lines.
    text, total = invoice(
        vendor="Example Field Instruments",
        vendor_address="18 Example Court, Example Valley, CA 94030",
        vendor_email="ar@fieldinstruments.example",
        number="EFI-40817",
        dated=date(2026, 4, 8),
        attn=f"{PARKER.name} and {KENDALL.name}",
        department=DEPARTMENT,
        project_ref="one order for two awards, see the items",
        items=[
            ("Turbidity sensor, optical (SYN-2309472)", 1, 145000),
            ("Conductivity probe (SYN-2507264)", 1, 98000),
        ],
        po="PO-26-2904",
    )
    inv = "invoice_EFI-40817.txt"
    for g, amount, posting, desc in (
        (c, 145000, date(2026, 4, 15), "Turbidity sensor, optical"),
        (b, 98000, date(2026, 4, 16), "Conductivity probe"),
    ):
        g.doc(
            inv,
            text,
            at(date(2026, 4, 10), 18),
            "upload",
            note="S3b. One invoice for two awards, itemized by award. The other grant holds "
            "its own copy.",
        )
        ln = g.line(
            date(2026, 4, 8),
            posting,
            amount,
            desc,
            SUPPLIES_ACCOUNT,
            vendor="Example Field Instruments",
            reference="EFI-40817",
            note="S3b. This grant's itemized line of a shared invoice.",
        )
        g.record(
            "bill",
            inv,
            total=str(total),
            dated="2026-04-08",
            vendor="Example Field Instruments",
            **{
                "items[0].description": "Turbidity sensor, optical (SYN-2309472)",
                "items[0].amount": "145000",
                "items[1].description": "Conductivity probe (SYN-2507264)",
                "items[1].amount": "98000",
            },
        )
        g.link(inv, ln, amount)
        g.budget(ln, "Materials and Supplies")
        g.answer(ln, "allowable", "supports")
        g.bucket(ln, at(posting, 12), EVIDENCE_COMPLETE)

    # S3c: A and C, with nothing that gives the basis.
    text, total = invoice(
        vendor="Example Cryogenics",
        vendor_address="7 Example Industrial Way, Example City, CA 94005",
        vendor_email="invoices@cryogenics.example",
        number="ECX-7702",
        dated=date(2026, 3, 3),
        attn="Earth and Ocean Sciences shared dewar",
        department=DEPARTMENT,
        project_ref="SYN-2401835 and SYN-2309472",
        items=[("Liquid nitrogen, 180 L", 1, 129000), ("Dewar delivery and handling", 1, 21000)],
    )
    assert total == 150000
    inv = "invoice_ECX-7702.txt"
    for g, amount in ((a, 90000), (c, 60000)):
        g.doc(
            inv,
            text,
            at(date(2026, 3, 5), 18),
            "upload",
            note="S3c. A shared invoice. Nothing on file says how it splits.",
        )
        ln = g.line(
            date(2026, 3, 3),
            date(2026, 3, 10),
            amount,
            "Liquid nitrogen, shared dewar",
            SUPPLIES_ACCOUNT,
            vendor="Example Cryogenics",
            reference="ECX-7702",
            note=f"S3c. {money(amount)} of a $1,500.00 invoice, with no basis on file.",
        )
        g.record("bill", inv, total="150000", dated="2026-03-03", vendor="Example Cryogenics")
        g.link(inv, ln, amount)
        g.budget(ln, "Materials and Supplies")
        g.bucket(ln, at(date(2026, 3, 10), 12), NEEDS_HUMAN)


__all__ = ["HORIZON", "build", "long_date"]
