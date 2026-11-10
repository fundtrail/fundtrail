"""The larger sample: one grant's whole life, from its award letter to sign-off.

About 30 charges. Most are ordinary and clear on their own. Twelve highlights
each show a part of the app the others don't (the sample content brief, ruling
58). Each highlight's events carry a short `highlight` label in timeline.json:

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
    one item open and a note.
10. The same invoice twice: emailed, then a scan in Drive.
11. One effort report clears six salary lines.
12. A bill under its charge: the item still open at sign-off.

The grant, people, amounts and dates are the builder's picks.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from demo import FIELD, HARPER, JAMIE, LAB, POSTDOC_SALARY, ROWAN, RTC, SASHA, SCI, SUPPLIES_ACCOUNT
from model import (
    EVIDENCE_COMPLETE,
    MISSING_EVIDENCE,
    POSSIBLE_CONFLICT,
    Grant,
    Ordinary,
    at,
    business_day,
)
from ordinary import (
    DEPARTMENT,
    GRANTS_INBOX,
    Trip,
    appointment_letter,
    award_letter,
    effort_report,
    months,
    recharges,
    supplies,
    trip,
)
from photo import photo, scan
from render import (
    UNIVERSITY,
    award_notice,
    eml,
    extension_notice,
    forwarded,
    invoice,
    long_date,
    money,
    pdf,
    usage_statement,
)

SLUG = "salt-marsh-carbon"
AWARD = "SYN-2401835"
TITLE = "Salt Marsh Carbon Burial at Example Point"
START, OLD_END, NEW_END = date(2024, 2, 1), date(2026, 7, 31), date(2027, 1, 31)
AWARD_DATE = date(2024, 1, 16)
OTHER_AWARD = "SYN-2507264"  # the award the shared kit's rest belongs to (another lab's)
LIMIT = 6000000  # the first increment's total obligated to date, in cents
POSTDOC_MONTHLY = 650000
# The rate agreement's Limited group (postdocs), fiscal year July 1, 2025 to June 30, 2026.
LIMITED_RATE = (15, 100)
BENEFITS_LIMITED = "53080 Benefit Assessment - Limited"
RATE_AGREEMENT = "rate_agreement_2025-05-28.pdf"
EMS = "Example Marine Station"

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

DESCRIPTION = (
    "This amendment funds the first increment of a new continuing grant for the period "
    "of performance shown below. The project measures how fast salt marshes at Example "
    "Point bury carbon as sea level rises. Participant support costs: funds budgeted for "
    "participant support may not be diverted by the awardee to other categories of expense "
    "without the prior written approval of the cognizant NSF Program Officer."
)


def build() -> Grant:
    g = Grant(SLUG, AWARD, START, OLD_END, horizon=at(NEW_END + timedelta(days=60), 23, 59))
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
        personnel=[HARPER, SASHA],
        program_officer=JAMIE,
        conditions=RTC,
        description=DESCRIPTION,
        budget=BUDGET_000,
        approval_rule=True,
        intended_cents=12000000,
        instrument="Continuing Grant",
        highlight="Terms tied to their passages",
    )


# ---------------------------------------------------------------- ordinary charges


def ordinary_charges(g: Grant, rng: random.Random) -> None:
    supplies(
        g,
        rng,
        vendors=[LAB, SCI, FIELD],
        dates=[
            date(2024, 3, 12),
            date(2024, 6, 18),
            date(2025, 3, 11),
            date(2025, 8, 19),
            date(2026, 4, 14),
            date(2026, 9, 15),
            date(2026, 12, 8),
        ],
        attn=HARPER,
        project_ref=f"{AWARD}, salt marsh carbon burial",
        account=SUPPLIES_ACCOUNT,
        forwarder=HARPER,
    )
    recharges(
        g,
        rng,
        facility="Example Stable Isotope Facility",
        unit="Campus Core Facilities",
        prefix="SIF",
        service_months=[date(2024, 8, 31), date(2025, 9, 30), date(2026, 10, 31)],
        services=[
            ("Carbon and nitrogen isotopes, per sample", 1800),
            ("Total organic carbon, per sample", 1250),
        ],
        qty=(12, 40),
        pi=HARPER,
    )
    trip(
        g,
        rng,
        Trip(
            "estuaries-2026",
            "Example Estuaries Conference, talk on marsh cores",
            "Example Harbor Convention Center, Example Harbor, MA",
            "EXH",
            date(2026, 5, 11),
            3,
            41200,
            5200,
            "Example Harbor Inn",
            22900,
            date(2026, 3, 30),
            "EXR8MV",
        ),
        traveler=HARPER,
    )


# ---------------------------------------------------------------- 3. a receipt photo


def taxi_trip(g: Grant, rng: random.Random) -> None:
    lines = [
        "EXAMPLE CAB CO.",
        "CAB 118   DRIVER 2207",
        "12/09/2024   18:15",
        "FROM: EXS AIRPORT",
        "TO: EXAMPLE SUMMIT HOTEL",
        "",
        "FARE                $52.00",
        "TOTAL               $52.00",
        "",
        "PAID: CARD ****4417",
        "THANK YOU",
    ]
    name = "taxi_receipt_egu_2024.jpg"
    taxi = g.doc(
        name,
        photo(name, lines, seed=2024),
        at(date(2024, 12, 16), 18),
        "upload",
        note="The PI's phone photo of the paper taxi receipt: hers to deliver.",
        text="\n".join(lines),
        deliver="user",
    )
    g.highlights[name] = "Receipt photo you deliver"
    g.deliver_file(
        name, at(date(2024, 12, 16), 18), "The PI uploads her taxi receipt photo on its date."
    )
    g.record("bill", name, total="5200", dated="2024-12-09", vendor="Example Cab Co.")
    trip(
        g,
        rng,
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
            extra=("Taxi, airport to hotel, Example Cab Co.", 5200, taxi),
        ),
        traveler=HARPER,
    )


# ---------------------------------------------------------------- 2. invoice before its line


def invoice_before_line(g: Grant) -> None:
    text, total = invoice(
        vendor=LAB.name,
        vendor_address=LAB.address,
        vendor_email=LAB.email,
        number="INV-20514",
        dated=date(2025, 2, 6),
        attn=HARPER.name,
        department=DEPARTMENT,
        project_ref=f"{AWARD}, salt marsh carbon burial",
        items=[
            ("Sediment core liners, 50 count", 1, 24800),
            ("Sample bags, sterile, 500 count", 1, 9600),
        ],
        shipping_cents=1250,
        po="PO-25-1102",
    )
    arrives = at(date(2025, 2, 10), 18, 20)
    name = "invoice_INV-20514.eml"
    body = f"Invoice INV-20514 for {AWARD}, for the files.\n\nHarper\n\n" + forwarded(
        sender=("Example Lab Supply Co. Billing", LAB.email),
        at=at(date(2025, 2, 6), 23, 5),
        subject="Invoice INV-20514",
        to=HARPER.email,
        body=text,
    )
    g.doc(
        name,
        eml(
            sender=(HARPER.name, HARPER.email),
            to=GRANTS_INBOX,
            at=arrives,
            subject="Fwd: Invoice INV-20514",
            message_id="fwd-inv-20514@university.example",
            body=body,
        ),
        arrives,
        "gmail",
        sender=HARPER.email,
        note="The invoice arrives before its ledger line exists, and waits unlinked.",
    )
    g.highlights[name] = "Invoice before its line"
    ln = g.line(
        date(2025, 2, 6),
        date(2025, 2, 18),
        total,
        "Core liners, sample bags",
        SUPPLIES_ACCOUNT,
        vendor=LAB.name,
        reference="INV-20514",
        note="The line posts eight days after its invoice arrived. They link now.",
    )
    g.record("bill", name, total=str(total), dated="2025-02-06", vendor=LAB.name)
    g.link(name, ln, total)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "supports")
    g.ordinary.append(Ordinary(ln, [name]))


# ---------------------------------------------------------------- 4. a shared invoice


def shared_invoice(g: Grant) -> None:
    """Decision 0021 (unreviewed): this grant's part of a shared bill, on an email's
    basis, with the agent's suggestion about the rest waiting on the bill."""
    text, total = invoice(
        vendor="Example Genomics Supply",
        vendor_address="410 Example Boulevard, Example City, CA 94003",
        vendor_email="billing@genomicssupply.example",
        number="EGS-20931",
        dated=date(2025, 5, 12),
        attn=HARPER.name,
        department=DEPARTMENT,
        project_ref="Fixture and Dummy labs, shared order",
        items=[("16S library prep kit, 96 reactions", 1, 1000000)],
        po="PO-25-3381",
    )
    assert total == 1000000
    inv = "invoice_EGS-20931.pdf"
    g.doc(
        inv,
        pdf(text, title="Invoice EGS-20931"),
        at(date(2025, 5, 13), 17, 45),
        "upload",
        note="The shared kit's invoice.",
        text=text,
    )
    sent = at(date(2025, 5, 14), 21, 12)
    body = "\n".join(
        [
            "Hi Sam,",
            "",
            "The Example Genomics Supply invoice EGS-20931, for $10,000.00, is for one",
            "96-reaction library prep kit that two projects shared. 56 of the 96",
            f"samples were marsh cores for {AWARD}, and the other 40 samples were",
            f"field samples for {OTHER_AWARD}, Kendall Dummy's award. Please split the",
            "cost on that basis.",
            "",
            "Thanks,",
            "Harper",
        ]
    )
    note = "email_kit_split_basis.eml"
    g.doc(
        note,
        eml(
            sender=(HARPER.name, HARPER.email),
            to=GRANTS_INBOX,
            at=sent,
            subject="Splitting invoice EGS-20931 between two awards",
            message_id="kit-split-egs-20931@university.example",
            body=body,
        ),
        sent,
        "gmail",
        sender=HARPER.email,
        note="The email that gives the basis: 56 of the 96 samples.",
    )
    g.highlights[note] = "Shared invoice, 56 of 96"
    ln = g.line(
        date(2025, 5, 12),
        date(2025, 5, 19),
        583333,
        "16S library prep kit, shared",
        SUPPLIES_ACCOUNT,
        vendor="Example Genomics Supply",
        reference="EGS-20931",
        note="This grant's part of the shared $10,000.00 invoice: $5,833.33.",
    )
    g.record("bill", inv, total="1000000", dated="2025-05-12", vendor="Example Genomics Supply")
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
            "EXAMPLE COASTAL SCIENCE SOCIETY",
            "Example Coastal Science Meeting 2025, June 23 to 26, 2025",
            "",
            "REGISTRATION RECEIPT",
            "",
            "Confirmation: REG-2025-0311",
            "Receipt date: June 2, 2025",
            f"Registrant: {HARPER.name}, University of Example",
            "Registration category: Faculty member, full meeting",
            "",
            f"  {'Registration fee':<36}{money(65000):>12}",
            f"  {'Total paid':<36}{money(65000):>12}",
            "",
            "Paid by: university card ending 2290",
        ]
    )
    receipt_at = at(date(2025, 6, 4), 17, 40)
    body = (
        "Sam,\n\nReceipt for my registration at the Example Coastal Science Meeting. Please\n"
        f"charge it to the participant support line on {AWARD}.\n\nHarper\n\n"
        + forwarded(
            sender=("Example Coastal Science Society", "registration@coastalsociety.example"),
            at=at(date(2025, 6, 2), 18, 2),
            subject="Your registration receipt, REG-2025-0311",
            to=HARPER.email,
            body=receipt,
        )
    )
    name = "registration_receipt_reg-2025-0311.eml"
    g.doc(
        name,
        eml(
            sender=(HARPER.name, HARPER.email),
            to=GRANTS_INBOX,
            at=receipt_at,
            subject="Fwd: Your registration receipt, REG-2025-0311",
            message_id="fwd-reg-2025-0311@university.example",
            body=body,
        ),
        receipt_at,
        "gmail",
        sender=HARPER.email,
        note="The PI forwards the receipt for her own conference registration.",
    )
    fee = g.line(
        date(2025, 6, 2),
        date(2025, 6, 9),
        65000,
        "Conference registration - Fixture H - Example Coastal Science Meeting",
        "56714 Participant Support-Other",
        vendor="Example Coastal Science Society",
        reference="REG-2025-0311",
        note="The PI's own conference fee, posted to participant support.",
    )
    approval = "\n".join(
        [
            "Sam,",
            "",
            "Approved. Please charge my registration for the Example Coastal Science",
            f"Meeting to the participant support line on {AWARD}.",
            "",
            "Harper Fixture",
            f"Principal Investigator, {AWARD}",
        ]
    )
    forward_at = at(date(2025, 9, 15), 19, 5)
    body = (
        "Sam,\n\nFor the files on the registration charge on participant support, here\n"
        "is my approval from June.\n\nHarper\n\n"
        + forwarded(
            sender=(HARPER.name, HARPER.email),
            at=at(date(2025, 6, 1), 17, 14),
            subject="Registration on participant support",
            to="Sam Bursar <sam.bursar@university.example>",
            body=approval,
        )
    )
    approval_name = "approval_forward_registration.eml"
    g.doc(
        approval_name,
        eml(
            sender=(HARPER.name, HARPER.email),
            to=GRANTS_INBOX,
            at=forward_at,
            subject="Fwd: Registration on participant support",
            message_id="fwd-registration-approval@university.example",
            body=body,
        ),
        forward_at,
        "gmail",
        sender=HARPER.email,
        note='The PI forwards her own email saying "Approved": the wrong approver, and the '
        "wrong channel.",
    )
    g.highlights[approval_name] = "Own fee, own approval"
    g.record(
        "bill", name, total="65000", dated="2025-06-02", vendor="Example Coastal Science Society"
    )
    g.record("approval", approval_name, approver_email=HARPER.email, approved_on="2025-06-01")
    g.link(name, fee, 65000)
    g.link(approval_name, fee)
    g.answer(fee, "allowable", "contradicts")
    g.agent_extras["rules"][fee.line_id] = "NSF-PARTICIPANT-NOT-STAFF"
    g.bucket(fee, at(date(2025, 6, 9), 12), POSSIBLE_CONFLICT)
    g.bucket(fee, forward_at + timedelta(hours=1), POSSIBLE_CONFLICT)


# ---------------------------------------------------------------- 11. one report, six lines


def salaries(g: Grant) -> None:
    appt = "appointment_letter_mockley.txt"
    appointment_letter(
        g,
        name=appt,
        person=ROWAN,
        title="Postdoctoral Scholar",
        pi=HARPER,
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
    report = "effort_report_mockley_2025_07.txt"
    effort_report(
        g,
        name=report,
        person=ROWAN,
        title="Postdoctoral Scholar",
        pi=HARPER,
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
            f"Salary - {ROWAN.last_first} - Postdoctoral Scholar - {me:%b %Y}",
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
            f"Benefits - {ROWAN.last_first} - Postdoctoral Scholar - {me:%b %Y}",
            BENEFITS_LIMITED,
            reference=f"PAY-{me:%Y-%m}",
        )
        g.link(RATE_AGREEMENT, ben)
        g.budget(ben, "Fringe Benefits")
        g.answer(ben, "allowable", "supports")
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
    rows = [f"{'TYPE':<7}{'FROM':<11}{'TO':<11}{'RATE(%)':<9}{'LOCATION':<10}APPLICABLE TO"]
    rows += [
        f"{'FIXED':<7}{'7/1/2024':<11}{'6/30/2025':<11}{r:<9}{'All':<10}{who}" for r, who in fy25
    ]
    rows += [
        f"{'FIXED':<7}{'7/1/2025':<11}{'6/30/2026':<11}{r:<9}{'All':<10}{who}" for r, who in groups
    ]
    rows += [
        f"{'PROV.':<7}{'7/1/2026':<11}Until Amended   Use same rates and conditions as those",
        "                         cited for fiscal year ending June 30, 2026",
    ]
    text = "\n".join(
        [
            "EIN: 00-EXAMPLE",
            f"ORGANIZATION: {UNIVERSITY}",
            "100 Example Hall, Example City, CA 94000",
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
            "ON BEHALF OF THE GOVERNMENT: Example Cognizant Agency, Cost Allocation Services",
            "Signed: Jordan Ratesetter, Director, 05/28/2025",
            "",
            f"ORGANIZATION: {UNIVERSITY}",
            "AGREEMENT DATE: 05/28/2025",
        ]
    )
    g.doc(
        RATE_AGREEMENT,
        pdf(text, title="Colleges and Universities Rate Agreement"),
        at(date(2025, 6, 16), 18),
        "upload",
        note="The university's fringe benefit rate agreement, for the fiscal year from "
        "July 1, 2025.",
        text=text,
    )
    g.record("note", RATE_AGREEMENT)


# ---------------------------------------------------------------- 10. the same invoice twice


def same_invoice_twice(g: Grant) -> None:
    text, total = invoice(
        vendor=SCI.name,
        vendor_address=SCI.address,
        vendor_email=SCI.email,
        number="ESS-55120",
        dated=date(2025, 10, 6),
        attn=HARPER.name,
        department=DEPARTMENT,
        project_ref=f"{AWARD}, salt marsh carbon burial",
        items=[
            ("Crucibles, porcelain, 50 count", 2, 18900),
            ("Tin capsules, 5 x 9 mm, 1000 count", 4, 9875),
        ],
        shipping_cents=1875,
        po="PO-25-4410",
    )
    first = "invoice_ESS-55120.eml"
    sent = at(date(2025, 10, 8), 17, 30)
    body = f"Invoice ESS-55120 for {AWARD}, for the files.\n\nHarper\n\n" + forwarded(
        sender=("Example Scientific Supply Billing", SCI.email),
        at=at(date(2025, 10, 6), 22, 0),
        subject="Invoice ESS-55120",
        to=HARPER.email,
        body=text,
    )
    g.doc(
        first,
        eml(
            sender=(HARPER.name, HARPER.email),
            to=GRANTS_INBOX,
            at=sent,
            subject="Fwd: Invoice ESS-55120",
            message_id="fwd-ess-55120@university.example",
            body=body,
        ),
        sent,
        "gmail",
        sender=HARPER.email,
        note="Invoice ESS-55120, forwarded by email.",
    )
    ln = g.line(
        date(2025, 10, 6),
        date(2025, 10, 14),
        total,
        "Crucibles, tin capsules",
        SUPPLIES_ACCOUNT,
        vendor=SCI.name,
        reference="ESS-55120",
    )
    rows = text.rstrip("\n").split("\n")
    copy = "scan_invoice_ESS-55120.jpg"
    g.doc(
        copy,
        scan(copy, rows, seed=55120),
        at(date(2025, 11, 20), 19),
        "drive",
        note="A scan of the same invoice, saved to the lab's Drive folder six weeks later.",
        text="\n".join(rows),
    )
    g.highlights[copy] = "Same invoice twice"
    g.record("bill", first, total=str(total), dated="2025-10-06", vendor=SCI.name)
    g.record("bill", copy, total=str(total), dated="2025-10-06", vendor=SCI.name)
    g.link(first, ln, total)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "supports")
    g.ordinary.append(Ordinary(ln, [first]))
    g.agent_extras["duplicates"].append((copy, first))
    g.script(
        "decide_suggestion",
        at(date(2025, 11, 21), 17),
        "The accountant confirms the scan is a copy of the emailed invoice.",
        suggestion="duplicate",
        decision="accept",
        file=copy,
    )


# ---------------------------------------------------------------- 12. a bill under its charge


def bill_under_charge(g: Grant) -> None:
    text, total = invoice(
        vendor=SCI.name,
        vendor_address=SCI.address,
        vendor_email=SCI.email,
        number="ESS-56204",
        dated=date(2025, 11, 3),
        attn=HARPER.name,
        department=DEPARTMENT,
        project_ref=f"{AWARD}, salt marsh carbon burial",
        items=[("Sediment trap frames, stainless", 4, 30000)],
        po="PO-25-4511",
        terms="net 30. Freight billed separately.",
    )
    assert total == 120000
    name = "invoice_ESS-56204.txt"
    g.doc(name, text, at(date(2025, 11, 5), 18), "upload", note="Invoice ESS-56204, for $1,200.00.")
    ln = g.line(
        date(2025, 11, 3),
        date(2025, 11, 12),
        126000,
        "Sediment trap frames, with freight",
        SUPPLIES_ACCOUNT,
        vendor=SCI.name,
        reference="ESS-56204",
        note="Charged $1,260.00: $60.00 of freight whose bill never arrives.",
    )
    g.highlights[ln.line_id] = "Bill under its charge"
    g.record("bill", name, total=str(total), dated="2025-11-03", vendor=SCI.name)
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
        vendor=FIELD.name,
        vendor_address=FIELD.address,
        vendor_email=FIELD.email,
        number="EFG-30418",
        dated=date(2026, 1, 7),
        attn=HARPER.name,
        department=DEPARTMENT,
        project_ref=f"{AWARD}, field crew, January sampling",
        items=[
            ("Field crew dinner with wine, after sampling", 1, 18400),
            ("Dry bags, 20 L, 4 pack", 2, 8800),
        ],
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
            "Example Field Gear",
            "",
            text,
        ]
    )
    g.doc(
        name,
        eml(
            sender=("Example Field Gear Accounts", FIELD.email),
            to=GRANTS_INBOX,
            at=sent,
            subject="Invoice EFG-30418",
            message_id="inv-efg-30418@fieldgear.example",
            body=body,
        ),
        sent,
        "gmail",
        sender=FIELD.email,
        note="The vendor emails from an address nobody on the grant uses: held until let in.",
    )
    g.highlights[name] = "Held vendor email"
    let_in = at(date(2026, 1, 15), 17, 30)
    g.held[name] = let_in
    g.script("let_in_mail", let_in, "The accountant lets in the vendor's held email.", file=name)
    ln = g.line(
        date(2026, 1, 7),
        date(2026, 1, 13),
        total,
        "Field crew dinner, dry bags",
        SUPPLIES_ACCOUNT,
        vendor=FIELD.name,
        reference="EFG-30418",
        note="Includes a dinner with wine, which an NSF award can't pay for.",
    )
    g.record("bill", name, total=str(total), dated="2026-01-07", vendor=FIELD.name)
    g.link(name, ln, total)
    g.budget(ln, "Materials and Supplies")
    g.answer(ln, "allowable", "contradicts")
    g.agent_extras["rules"][ln.line_id] = "NSF-NEVER-ALCOHOL"
    g.bucket(ln, at(date(2026, 1, 13), 12), MISSING_EVIDENCE)
    g.bucket(ln, let_in + timedelta(hours=1), POSSIBLE_CONFLICT)

    just = "cost_transfer_justification_CT-26-0042.txt"
    g.doc(
        just,
        "\n".join(
            [
                UNIVERSITY.upper(),
                "COST TRANSFER JUSTIFICATION",
                "",
                "Transfer number: CT-26-0042",
                f"From award: {AWARD}",
                "To fund: Department fund EOD-2010",
                f"Ledger line moved: {ln.line_id}, Example Field Gear invoice EFG-30418, "
                f"{money(total)}",
                "",
                "Why the transfer is needed: the invoice includes a field crew dinner with wine,",
                "which the award can't pay for.",
                "Why the wrong fund was charged: the invoice was coded to the award with the",
                "January field supplies.",
                "How the expense relates to the project: the dry bags were for the award's field",
                "work and are charged again to the department fund with the dinner.",
                "",
                "Prepared by: Sam Bursar, March 5, 2026",
            ]
        )
        + "\n",
        at(date(2026, 3, 6), 18),
        "upload",
        note="The written justification for moving the charge off the grant.",
    )
    fix = g.line(
        date(2026, 3, 6),
        date(2026, 3, 9),
        -total,
        "Cost transfer off award - Example Field Gear EFG-30418",
        SUPPLIES_ACCOUNT,
        vendor=FIELD.name,
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
        vendor=FIELD.name,
        vendor_address=FIELD.address,
        vendor_email=FIELD.email,
        number="EFG-31207",
        dated=date(2026, 4, 27),
        attn=HARPER.name,
        department=DEPARTMENT,
        project_ref=f"{AWARD}, salt marsh carbon burial",
        items=[("Sediment corer, piston type, 1 m", 1, 495000)],
        po="PO-26-2280",
    )
    name = "invoice_EFG-31207.txt"
    g.doc(name, text, at(date(2026, 4, 28), 18), "upload", note="Invoice EFG-31207, for the corer.")
    ln = g.line(
        date(2026, 4, 27),
        date(2026, 5, 5),
        total,
        "Sediment corer, piston type",
        SUPPLIES_ACCOUNT,
        vendor=FIELD.name,
        reference="EFG-31207",
        note="Spending passes the award's $60,000.00 obligated to date, and Materials "
        "and Supplies passes its line.",
    )
    g.highlights[ln.line_id] = "Over budget"
    g.record("bill", name, total=str(total), dated="2026-04-27", vendor=FIELD.name)
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
        personnel=[(HARPER.name, HARPER.role, HARPER.email), (SASHA.name, SASHA.role, SASHA.email)],
        program_officer=(JAMIE.name, JAMIE.email),
        conditions=RTC,
        budget=[(b[0], b[1], [(s[0], s[1]) for s in b[3]]) for b in BUDGET_001],
    )
    notice = "notice_001_increment.txt"
    g.doc(
        notice,
        notice_text,
        at(date(2026, 6, 12), 17),
        "upload",
        note="Amendment 001 adds $60,000.00: the award's limit rises to $120,000.00.",
    )
    g.highlights[notice] = "More money, a higher limit"
    g.confirm(notice, at(date(2026, 6, 15), 17), "The user confirms the increment's terms.")
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
        pi=HARPER.name,
        award_number=AWARD,
        rows=[("Research vessel time, per hour", 18, 17500)],
    )
    name = "usage_statement_EMS-2608-21.txt"
    g.doc(
        name,
        text,
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
        program_officer=(JAMIE.name, JAMIE.email),
    )
    notice_name = "extension_notice_002.txt"
    arrives = at(date(2026, 9, 14), 16, 30)
    confirmed = at(date(2026, 9, 15), 17)
    g.doc(
        notice_name,
        notice,
        arrives,
        "drive",
        note="The extension notice, dated 16 days before the old end date, turns up in Drive.",
    )
    g.highlights[notice_name] = "Extension found in Drive"
    g.confirm(notice_name, confirmed, "The user confirms the new end date, January 31, 2027.")
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
    notice = "notice_of_expiration.txt"
    g.doc(
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
                f"Principal investigator: {HARPER.name}",
                f"End date: {long_date(NEW_END)}",
                "",
                "This award ends in 90 days. Please review every charge for completeness,",
                "accuracy and allowability, and move any charge that doesn't belong to the",
                "award before the books close two months after the end date.",
            ]
        )
        + "\n",
        at(window, 17),
        "upload",
        note="The university's 90-day notice: the closeout window opens.",
    )
    g.highlights[notice] = "Closeout"
    # The accountant signs off on the evidence report, with this note.
    g.script(
        "sign_off",
        at(date(2027, 3, 10), 18),
        "One item is open: invoice ESS-56204 covers $1,200.00 of the $1,260.00 charge, and "
        "the vendor's freight bill for $60.00 has been requested.",
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
