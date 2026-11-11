"""Templates for a grant's ordinary charges and their ordinary evidence.

Salaries with their appointment letters and certified effort reports,
supplies with invoices, trips with their receipts and expense reports, and a
campus facility's recharges with usage statements. Each template adds the
files, the ledger lines and the answer key's expectations to a `Grant`.
"""

from __future__ import annotations

import calendar
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import typeset
from model import Doc, Grant, Line, Ordinary, at, business_day
from names import LEGACY, Person, Vendor
from render import (
    award_notice,
    eml,
    forwarded,
    invoice,
    long_date,
    money,
    pdf,
    sentence,
    short,
    usage_statement,
)

# The unused seed grants' inbox. A template takes the grant's own from `g.org`.
GRANTS_INBOX = LEGACY.grants_inbox
DEPARTMENT = "Department of Earth and Ocean Sciences"

__all__ = ["Person", "Vendor"]  # defined in names.py, and used from here by demo.py


def mail_domain(g: Grant) -> str:
    """The university's email domain, for the Message-ID of a forwarded email."""
    return g.org.grants_inbox[1].split("@")[1]


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def months(first: date, last: date) -> list[date]:
    """Month ends from the month of `first` to the month of `last`."""
    out = []
    y, m = first.year, first.month
    while (y, m) <= (last.year, last.month):
        out.append(month_end(y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def utc_hour(rng: random.Random, d: date, lo: int = 16, hi: int = 23) -> datetime:
    """A time during the Pacific working day on date d, in UTC."""
    return at(d, rng.randint(lo, hi), rng.choice([0, 5, 10, 15, 20, 30, 40, 45, 50]))


def put(
    g: Grant,
    name: str,
    text: str,
    title: str,
    arrives: datetime,
    source: str,
    *,
    look: str | None = None,
    **fields: str | None,
) -> Doc:
    """Adds a document whose content is `text`, in the form its name gives.

    A `.pdf` on a sample is typeset (typeset.render), in the `look` of whoever
    issued it. On the unused seed grants it's the typewriter PDF they were built
    with. Any other name is the text itself. `text` stays the document's text, the
    one the stand-in agent cites from.
    """
    if not name.endswith(".pdf"):
        return g.doc(name, text, arrives, source, **fields)
    if not g.typeset:
        return g.doc(name, pdf(text, title=title), arrives, source, text=text, **fields)
    data, pages = typeset.render(name, text, look)
    doc = g.doc(name, data, arrives, source, text=text, **fields)
    doc.pages = pages
    return doc


def paper(g: Grant, stem: str) -> str:
    """The file name for a document that's plain text on the unused seed grants and a
    typeset PDF on a sample."""
    return f"{stem}.pdf" if g.typeset else f"{stem}.txt"


# ---------------------------------------------------------------- the award letter


def award_letter(
    g: Grant,
    *,
    title: str,
    award_date: date,
    arrives: datetime,
    confirm_at: datetime,
    personnel: list[Person],
    program_officer: Person,
    conditions: str,
    description: str,
    budget: list[tuple[str, int, str, list[tuple[str, int, str]]]],
    approval_rule: bool = False,
    name: str = "award_letter.txt",
    source: str = "upload",
    intended_cents: int | None = None,
    instrument: str = "Standard Grant",
    highlight: str | None = None,
    division: str | None = None,
    listing: str | None = None,
) -> None:
    """The award notice, the accountant confirming its terms, and its records.

    `budget` is (line with its letter, amount, category, sub-lines), each
    sub-line (name, amount, category).
    """
    total = sum(b[1] for b in budget)
    text = award_notice(
        award_number=g.award_number,
        amendment_type="New Project",
        amendment_number="000",
        amendment_date=award_date,
        description=description,
        start=g.start,
        end=g.end,
        title=title,
        obligated_cents=total,
        intended_cents=intended_cents,
        instrument=instrument,
        personnel=[(p.name, p.role, p.email) for p in personnel],
        program_officer=(program_officer.name, program_officer.email),
        conditions=conditions,
        budget=[(b[0], b[1], [(s[0], s[1]) for s in b[3]]) for b in budget],
        org=g.org,
        division=division,
        listing=listing,
    )
    note = (
        "The award letter arrives. It's the first thing on the grant's timeline."
        if g.typeset
        else "The award letter arrives: the grant's first scheduled event."
    )
    put(g, name, text, f"Award notice {g.award_number}", arrives, source, note=note)
    g.confirm(name, confirm_at, "The user confirms every term read from the award letter.")
    if highlight:
        g.highlights[name] = highlight
    dated = award_date.isoformat()
    g.record(
        "period_of_performance", name, start=g.start.isoformat(), end=g.end.isoformat(), dated=dated
    )
    g.record(
        "notice",
        name,
        amendment_number="000",
        amendment_type="New Project",
        obligated_by_amendment=str(total),
        obligated_to_date=str(total),
        dated=dated,
    )
    for line, amount, category, subs in budget:
        g.record(
            "budget_line",
            name,
            name=line.split(". ", 1)[1],
            category=category,
            amount=str(amount),
            dated=dated,
        )
        for sub, sub_amount, sub_category in subs:
            g.record(
                "budget_line",
                name,
                name=sub,
                category=sub_category,
                amount=str(sub_amount),
                dated=dated,
            )
    for p in personnel:
        g.record("person", name, name=p.name, email=p.email, role=p.role, dated=dated)
    g.record(
        "person",
        name,
        name=g.org.grants_official[0],
        email=g.org.grants_official[1],
        role="Managing Grants Official",
        dated=dated,
    )
    g.record(
        "person",
        name,
        name=g.org.awarding_official[0],
        email=g.org.awarding_official[1],
        role="Awarding Official",
        dated=dated,
    )
    g.record(
        "person",
        name,
        name=program_officer.name,
        email=program_officer.email,
        role="Managing Program Officer",
        dated=dated,
    )
    if approval_rule:
        # The rule is about moving money out of participant support (issue 39).
        g.record("approval_rule", name, dated=dated, scope="moved_out")


# ---------------------------------------------------------------- salaries


def appointment_letter(
    g: Grant,
    *,
    name: str,
    person: Person,
    title: str,
    pi: Person,
    start: date,
    end: date,
    monthly_cents: int,
    dated: date,
    accepted: date,
    arrives: datetime,
    work: str,
    project_title: str,
) -> None:
    text = "\n".join(
        [
            g.org.university.upper(),
            DEPARTMENT,
            g.org.address,
            "",
            long_date(dated),
            "",
            person.name,
            person.email,
            "",
            f"Re: Appointment as {title}",
            "",
            f"Dear {person.name.split()[0]},",
            "",
            f"I am pleased to confirm your appointment as a {title} in the",
            f"{DEPARTMENT}, working in the laboratory of Professor {pi.name}.",
            "",
            f"Appointment period: {long_date(start)} through {long_date(end)}",
            f"Title: {title}",
            f"Monthly salary charged to award {g.award_number}: {money(monthly_cents)}",
            "",
            "Funding for this appointment:",
            f"  Award {g.award_number}, {project_title}:",
            f"  100 percent of salary, {money(monthly_cents)} per month",
            "",
            *_wrap_para(f"Your work on award {g.award_number} is {work}"),
            "",
            "Effort on sponsored awards is certified twice a year, for January to June",
            "and for July to December.",
            "",
            "Sincerely,",
            "",
            pi.name,
            "Professor and Principal Investigator",
            pi.email,
            "",
            f"Accepted: {person.name}, {long_date(accepted)}",
        ]
    )
    put(
        g,
        name,
        text + "\n",
        f"Appointment letter, {person.name}",
        arrives,
        "upload",
        note=f"{person.name}'s appointment letter.",
    )
    g.record("note", name)


def _wrap_para(text: str, width: int = 74) -> list[str]:
    from render import wrap

    return wrap(text, width)


def effort_report(
    g: Grant,
    *,
    name: str,
    person: Person,
    title: str,
    pi: Person,
    period: tuple[date, date],
    salary: list[tuple[date, int]],
    certified: date,
    arrives: datetime,
    project_title: str,
) -> None:
    rows = [f"  {d:%B %Y}".ljust(20) + f"{money(c):>14}" for d, c in salary]
    total = sum(c for _, c in salary)
    text = "\n".join(
        [
            g.org.university.upper(),
            "CERTIFIED EFFORT REPORT",
            "",
            f"Employee: {person.name}",
            f"Title: {title}",
            "Department: Earth and Ocean Sciences",
            f"Reporting period: {long_date(period[0])} to {long_date(period[1])}",
            "",
            "Distribution of effort for the reporting period",
            "",
            f"{'Fund or award':<56}Effort",
            f"Award {g.award_number}, {project_title}",
            f"{'':<56}100 percent",
            f"{'Total':<56}100 percent",
            "",
            f"Salary charged to award {g.award_number} for the reporting period:",
            *rows,
            "  Total".ljust(20) + f"{money(total):>14}",
            "",
            "Certification",
            "I certify that the distribution of effort above is a reasonable estimate of",
            "the work performed by the employee during the reporting period.",
            "",
            f"Certified by: {pi.name}, Principal Investigator",
            f"Email: {pi.email}",
            f"Date certified: {long_date(certified)}",
        ]
    )
    put(
        g,
        name,
        text + "\n",
        f"Certified effort report, {person.name}",
        arrives,
        "upload",
        note=f"The certified effort report for {person.name}, {long_date(period[0])} to "
        f"{long_date(period[1])}.",
    )
    g.record("note", name)


def half_year(d: date) -> tuple[date, date]:
    if d.month <= 6:
        return date(d.year, 1, 1), date(d.year, 6, 30)
    return date(d.year, 7, 1), date(d.year, 12, 31)


def salary_series(
    g: Grant,
    rng: random.Random,
    *,
    person: Person,
    title: str,
    salary_account: str,
    monthly_cents: int,
    first: date,
    last: date,
    budget_line: str,
    appointments: list[tuple[str, date, date]],
    pi: Person,
    project_title: str,
    horizon: datetime,
) -> list[Line]:
    """Monthly salary lines, with effort reports twice a year.

    `appointments` are (file, start, end): the appointment letters already
    added, each covering its months. The seed has no benefit lines for now
    (see the README).
    """
    month_ends = months(first, last)
    # Effort reports, one per half year that has salary in it.
    reports: dict[tuple[date, date], str] = {}
    for me in month_ends:
        period = half_year(me)
        if period in reports:
            continue
        certified = business_day(period[1] + timedelta(days=rng.randint(40, 75)))
        arrives = utc_hour(rng, certified + timedelta(days=rng.randint(1, 3)))
        if arrives > horizon:
            continue
        name = paper(g, f"effort_report_{person.name.split()[1].lower()}_{period[0]:%Y_%m}")
        in_period = [m for m in month_ends if period[0] <= m <= period[1]]
        effort_report(
            g,
            name=name,
            person=person,
            title=title,
            pi=pi,
            period=period,
            salary=[(m, monthly_cents) for m in in_period],
            certified=certified,
            arrives=arrives,
            project_title=project_title,
        )
        reports[period] = name
    lines = []
    for me in month_ends:
        posting = business_day(me + timedelta(days=3))
        if posting > horizon.date():
            continue
        label = f"{me:%b %Y}"
        sal = g.line(
            me,
            posting,
            monthly_cents,
            f"Salary - {person.last_first} - {title} - {label}",
            salary_account,
            reference=f"PAY-{me:%Y-%m}",
        )
        appt = next(f for f, s, e in appointments if s <= me <= e)
        report = reports.get(half_year(me))
        g.link(appt, sal)
        if report:
            g.link(report, sal)
        g.budget(sal, budget_line)
        g.answer(sal, "allowable", "supports")
        g.ordinary.append(Ordinary(sal, [appt, report or "(not on file yet)"]))
        lines.append(sal)
    return lines


# ---------------------------------------------------------------- supplies


def supplies(
    g: Grant,
    rng: random.Random,
    *,
    vendors: list[Vendor],
    dates: list[date],
    attn: Person,
    project_ref: str,
    account: str,
    budget_line: str = "Materials and Supplies",
    forwarder: Person,
    lines_for: dict[str, list[tuple]] | None = None,
) -> list[Line]:
    """One purchase per date: an invoice and a ledger line.

    The invoice arrives as an uploaded file, as an email the professor forwards,
    or as a PDF found in Drive, before or after the line posts. `lines_for` gives
    an invoice's lines by its number, in place of the ones drawn for it: they have
    to come to the same subtotal, so the charge is the same, and the ledger line
    keeps the description drawn for it.
    """
    out = []
    for txn in dates:
        v = rng.choice(vendors)
        count = rng.choice([1, 1, 2, 2, 3])
        picks = rng.sample(v.catalog, count)
        items = [(desc, rng.choice([1, 1, 2, 3, 4, 5]), unit) for desc, unit in picks]
        shipping = rng.choice([0, 0, 0, 1250, 1875, 2400])
        number = f"{v.prefix}-{rng.randint(10000, 99999)}"
        described = short(", ".join(d for d, _, _ in items))
        if lines_for and number in lines_for:
            drawn = sum(q * u for _, q, u in items)
            items = lines_for[number]
            assert sum(i[1] * i[2] for i in items) == drawn, f"{number}: a different subtotal"
        text, total = invoice(
            vendor=v.name,
            vendor_address=v.address,
            vendor_email=v.email,
            number=number,
            dated=txn,
            attn=attn.name,
            department=DEPARTMENT,
            project_ref=project_ref,
            items=items,
            shipping_cents=shipping,
            po=f"PO-{txn:%y}-{rng.randint(1000, 9999)}",
            org=g.org,
            account=v.account,
        )
        posting = business_day(txn + timedelta(days=rng.randint(5, 12)))
        mode = rng.choice(["upload", "upload", "upload", "gmail", "gmail", "drive"])
        if mode == "upload":
            name = paper(g, f"invoice_{number}")
            arrives = utc_hour(rng, txn + timedelta(days=rng.randint(1, 4)))
            put(
                g,
                name,
                text,
                f"Invoice {number}",
                arrives,
                "upload",
                look=v.look,
                note=sentence(f"Invoice {number} from {v.name}"),
            )
        elif mode == "gmail":
            name = f"invoice_{number}.eml"
            arrives = utc_hour(rng, txn + timedelta(days=rng.randint(1, 16)))
            sent = utc_hour(rng, txn, 15, 18)
            body = (
                f"Invoice {number} for {project_ref}, for the files.\n\n"
                f"{forwarder.first}\n\n"
                + forwarded(
                    sender=(f"{v.name} Billing", v.email),
                    at=min(sent, arrives - timedelta(minutes=30)),
                    subject=f"Invoice {number}",
                    to=forwarder.email,
                    body=text,
                )
            )
            g.doc(
                name,
                eml(
                    sender=(forwarder.name, forwarder.email),
                    to=g.org.grants_inbox,
                    at=arrives,
                    subject=f"Fwd: Invoice {number}",
                    message_id=f"fwd-{number.lower()}@{mail_domain(g)}",
                    body=body,
                ),
                arrives,
                "gmail",
                sender=forwarder.email,
                note=f"{forwarder.name} forwards invoice {number}.",
            )
        else:
            name = f"invoice_{number}.pdf"
            arrives = utc_hour(rng, posting + timedelta(days=rng.randint(3, 25)))
            put(
                g,
                name,
                text,
                f"Invoice {number}",
                arrives,
                "drive",
                look=v.look,
                note=f"Invoice {number}, saved to the lab's Drive folder.",
            )
        ln = g.line(
            txn,
            posting,
            total,
            described,
            account,
            vendor=v.name,
            reference=number,
        )
        g.record("bill", name, total=str(total), dated=txn.isoformat(), vendor=v.name)
        g.link(name, ln, total)
        g.budget(ln, budget_line)
        g.answer(ln, "allowable", "supports")
        g.ordinary.append(Ordinary(ln, [name]))
        out.append(ln)
    return out


# ---------------------------------------------------------------- travel


@dataclass(frozen=True)
class Trip:
    slug: str
    purpose: str
    destination: str
    airport: str
    depart: date
    nights: int
    fare_cents: int
    taxes_cents: int
    hotel: str
    nightly_cents: int
    booked: date
    confirmation: str
    extra: tuple[str, int, Doc | None] | None = None  # (description, cents, its doc)
    # The fare's lines as an airline itemizes them, the base fare first, coming to
    # the fare and its taxes; and the receipt's ticket number.
    fare_lines: tuple[tuple[str, int], ...] = ()
    ticket: str = ""
    # Each night's lines on the folio, the room first, coming to the nightly rate.
    night_lines: tuple[tuple[str, int], ...] = ()


def trip(
    g: Grant,
    rng: random.Random,
    t: Trip,
    *,
    traveler: Person,
    account: str = "57210 Domestic Travel",
    budget_line: str = "Domestic",
) -> Line:
    """A trip: an airline receipt by email, a hotel folio and an expense report."""
    ret = t.depart + timedelta(days=t.nights)
    fare_total = t.fare_cents + t.taxes_cents
    hotel_total = t.nightly_cents * t.nights
    # Airline receipt, forwarded by the traveler soon after booking.
    air_name = f"airfare_receipt_{t.slug}.eml"
    sent = utc_hour(rng, t.booked, 16, 19)
    air_at = sent + timedelta(hours=rng.randint(1, 30))
    org = g.org
    code, home = org.flight_code, org.home_airport
    fare_lines = t.fare_lines or (
        ("Base fare", t.fare_cents),
        ("Taxes, fees and charges", t.taxes_cents),
    )
    assert sum(c for _, c in fare_lines) == fare_total, f"{t.slug}: the fare's lines"
    night_lines = t.night_lines or (("Room, standard queen", t.nightly_cents),)
    assert sum(c for _, c in night_lines) == t.nightly_cents, f"{t.slug}: a night's lines"
    receipt = "\n".join(
        [
            org.airline.upper(),
            "Electronic ticket receipt",
            "",
            f"Receipt date: {long_date(t.booked)}",
            f"Confirmation: {t.confirmation}",
            *([f"Ticket number: {t.ticket}"] if t.ticket else []),
            f"Passenger: {traveler.name}",
            "",
            "Itinerary",
            f"  {long_date(t.depart):<18}Flight {code} {rng.randint(100, 899)}   {home} to "
            f"{t.airport}   Economy, fare class V",
            f"  {long_date(ret):<18}Flight {code} {rng.randint(100, 899)}   {t.airport} to "
            f"{home}   Economy, fare class V",
            "",
            "Charges",
            *[f"  {label:<36}{money(cents):>12}" for label, cents in fare_lines],
            f"  {'Total':<36}{money(fare_total):>12}",
            "",
            "Form of payment: personal card ending 4417",
            "Fare rules: nonrefundable economy fare. Changes allowed for a fee.",
        ]
    )
    body = (
        f"Airfare receipt for {t.purpose} on {g.award_number}.\n"
        "The expense report will follow after the trip.\n\n"
        f"{traveler.first}\n\n"
        + forwarded(
            sender=(org.airline, org.airline_email),
            at=sent,
            subject=f"Your {org.airline} receipt, confirmation {t.confirmation}",
            to=traveler.email,
            body=receipt,
        )
    )
    g.doc(
        air_name,
        eml(
            sender=(traveler.name, traveler.email),
            to=org.grants_inbox,
            at=air_at,
            subject=f"Fwd: Your {org.airline} receipt, confirmation {t.confirmation}",
            message_id=f"fwd-{t.confirmation.lower()}@{mail_domain(g)}",
            body=body,
        ),
        air_at,
        "gmail",
        sender=traveler.email,
        note=f"{traveler.name} forwards the airline receipt for {t.purpose}.",
    )
    # Hotel folio.
    folio_no = f"F{rng.randint(100000, 999999)}"
    folio_name = f"hotel_folio_{t.slug}.pdf"
    nights = [
        f"  {long_date(t.depart + timedelta(days=i)):<22}{label:<28}{money(cents):>8}"
        for i in range(t.nights)
        for label, cents in night_lines
    ]
    folio = "\n".join(
        [
            t.hotel.upper(),
            f"{t.destination}",
            "",
            "GUEST FOLIO",
            "",
            f"Folio number: {folio_no}",
            f"Guest: {traveler.name}",
            f"Arrival: {long_date(t.depart)}",
            f"Departure: {long_date(ret)}",
            "",
            *nights,
            "",
            f"  {'Total charges':<42}{money(hotel_total):>12}",
            f"  {'Payment, card ending 4417':<42}{money(-hotel_total):>12}",
            f"  {'Balance due':<42}{money(0):>12}",
            "",
            f"Date: {long_date(ret)}",
        ]
    )
    folio_at = utc_hour(rng, ret + timedelta(days=rng.randint(2, 4)))
    put(
        g,
        folio_name,
        folio,
        f"Folio {folio_no}",
        folio_at,
        "upload",
        note=f"The hotel folio for {t.purpose}.",
    )
    # Expense report.
    total = fare_total + hotel_total + (t.extra[1] if t.extra else 0)
    report_no = f"ER-{ret:%y}-{rng.randint(1000, 9999)}"
    report_name = paper(g, f"expense_report_{t.slug}")
    claimed = [
        f"  Airfare, {org.airline}, confirmation {t.confirmation}".ljust(60)
        + f"{money(fare_total):>12}",
        f"  Lodging, {t.hotel}, {t.nights} nights".ljust(60) + f"{money(hotel_total):>12}",
    ]
    if t.extra:
        claimed.append(f"  {t.extra[0]}".ljust(60) + f"{money(t.extra[1]):>12}")
    submitted = ret + timedelta(days=rng.randint(2, 5))
    approved = submitted + timedelta(days=1)
    report = "\n".join(
        [
            org.university.upper(),
            "TRAVEL EXPENSE REPORT",
            "",
            f"Report number: {report_no}",
            f"Traveler: {traveler.name}, {traveler.role or 'Principal Investigator'}",
            f"Email: {traveler.email}",
            f"Award charged: {g.award_number}",
            "",
            f"Purpose of trip: {t.purpose}",
            f"Destination: {t.destination}",
            f"Departure: {long_date(t.depart)}",
            f"Return: {long_date(ret)}",
            "",
            "Expenses claimed",
            *claimed,
            "  Total reimbursement".ljust(60) + f"{money(total):>12}",
            "",
            "Meals are not claimed on this report.",
            "",
            f"Submitted by traveler: {long_date(submitted)}",
            f"Approved by department: {long_date(approved)}, Earth and Ocean Sciences business"
            " office",
        ]
    )
    report_at = utc_hour(rng, approved + timedelta(days=rng.randint(0, 2)))
    put(
        g,
        report_name,
        report + "\n",
        f"Expense report {report_no}",
        report_at,
        "upload",
        note=f"The department's approved expense report for {t.purpose}.",
    )
    posting = business_day(approved + timedelta(days=rng.randint(6, 10)))
    ln = g.line(
        ret,
        posting,
        total,
        f"Travel reimbursement - {traveler.last_first} - {short(t.purpose, 40)}",
        account,
        vendor=traveler.name,
        reference=report_no,
    )
    g.record(
        "bill", air_name, total=str(fare_total), dated=t.booked.isoformat(), vendor=org.airline
    )
    g.record("bill", folio_name, total=str(hotel_total), dated=ret.isoformat(), vendor=t.hotel)
    g.record("note", report_name)
    g.link(air_name, ln, fare_total)
    g.link(folio_name, ln, hotel_total)
    g.link(report_name, ln)
    needs = [air_name, folio_name, report_name]
    if t.extra and t.extra[2] is not None:
        g.link(t.extra[2].name, ln, t.extra[1])
        needs.append(t.extra[2].name)
    g.budget(ln, budget_line)
    g.answer(ln, "allowable", "supports")
    g.ordinary.append(Ordinary(ln, needs))
    return ln


# ---------------------------------------------------------------- recharges


def recharges(
    g: Grant,
    rng: random.Random,
    *,
    facility: str,
    unit: str,
    prefix: str,
    service_months: list[date],
    services: list[tuple[str, int]],
    qty: tuple[int, int],
    pi: Person,
    account: str = "59009 Recharge-Other Expenses",
    budget_line: str = "Other",
    as_pdf_every: int = 3,
    rows_for: dict[str, list[tuple[str, int, int]]] | None = None,
) -> list[Line]:
    """A campus facility's monthly usage statements and their recharge lines.

    `rows_for` gives a statement's service rows by its number, in place of the one
    drawn for it: they have to come to the same total."""
    out = []
    for i, me in enumerate(service_months):
        stmt_date = business_day(me + timedelta(days=1))
        rows = [(desc, rng.randint(*qty), rate) for desc, rate in rng.sample(services, 1)]
        number = f"{prefix}-{me:%y%m}-{rng.randint(10, 99)}"
        if rows_for and number in rows_for:
            drawn = sum(q * r for _, q, r in rows)
            rows = rows_for[number]
            assert sum(q * r for _, q, r in rows) == drawn, f"{number}: a different total"
        text, total = usage_statement(
            facility=facility,
            unit=unit,
            number=number,
            dated=stmt_date,
            period=f"{long_date(me.replace(day=1))} to {long_date(me)}",
            pi=pi.name,
            award_number=g.award_number,
            rows=rows,
            org=g.org,
        )
        arrives = utc_hour(rng, stmt_date + timedelta(days=rng.randint(0, 3)))
        if as_pdf_every and i % as_pdf_every == as_pdf_every - 1:
            name = f"usage_statement_{number}.pdf"
        else:
            name = paper(g, f"usage_statement_{number}")
        put(
            g,
            name,
            text,
            f"Usage statement {number}",
            arrives,
            "drive",
            note=f"{facility} usage statement {number}, from the lab's Drive folder.",
        )
        posting = business_day(stmt_date + timedelta(days=rng.randint(2, 6)))
        ln = g.line(
            me,
            posting,
            total,
            f"{facility} - {me:%b %Y}",
            account,
            vendor=facility,
            reference=number,
        )
        g.record("bill", name, total=str(total), dated=stmt_date.isoformat())
        g.link(name, ln, total)
        g.budget(ln, budget_line)
        g.answer(ln, "allowable", "supports")
        g.ordinary.append(Ordinary(ln, [name]))
        out.append(ln)
    return out


def spread(rng: random.Random, first: date, last: date, n: int) -> list[date]:
    """n weekday dates spread over a span, sorted."""
    span = (last - first).days
    out = set()
    while len(out) < n:
        d = first + timedelta(days=rng.randint(0, span))
        if d.weekday() < 5:
            out.add(d)
    return sorted(out)
