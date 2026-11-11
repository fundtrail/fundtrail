"""Benefit charges, recalculated from the grant's salary lines and its confirmed rates (ruling 61).

Berkeley charges most benefits as a composite benefit rate: one percentage per employee
group, set for each fiscal year (July 1 to June 30) by the rate agreement. The rate
agreement is a document on the grant, and the agent reads each of its rates as a rate
term naming its group and the dates it covers (`Rate.applies_to`, `effective_from`,
`effective_to`). The accountant confirms each one once.

- The benefit charge's ledger account tells its group (`BENEFIT_ACCOUNTS`). A charge on
  any other benefits account keeps its "Benefit rate" item as before, filled by a link.
- Code recalculates month by month and group by group. One cell is the benefit charges
  of one group whose transaction date falls in one calendar month, against the salary
  lines of that group in the same month. The salary of a month is counted net of the
  lines that correct it (decision 0020), on the month of the line they correct; a line
  that nets into another is counted there, not on its own.
- The rate is the confirmed rate of that group in force on the first day of the month.
  A confirmed rate stays in force until a later confirmed one for the same group
  starts, whatever its own end date says (product answer to ruling 61's first
  question; the citation shows the agreement's own wording). Change `rate_in_force` to
  change that.
- The cell's benefit charges match when they add up to the rate times the salary within
  rounding: a cent for each salary line counted (`tolerance`). Each one's "Benefit rate"
  item is then filled, citing the rate term and the salary lines (`ChecklistEntry.rate_id`
  and `charge_ids`), with no links. A mismatch is Needs a human, showing the amount
  expected and the amount charged. No confirmed rate is Needs a human: shown on the rate
  term's row when one waits for the accountant, its own problem otherwise.
- A benefit charge isn't Evidence complete until its salary lines are. While any of them
  isn't (not Evidence complete, not accepted, not reversed), it has a Missing evidence
  reason, "waits on its salary lines". That reason never puts the charge on the problem
  list as its own row: the salary line's row carries it (ruling 62), and it clears when
  that row does. The problem list builder reads `waiting_on` for that.

Which salary accounts belong to which group isn't verified (`SALARY_ACCOUNTS`). A group no
salary account is known for can't be recalculated, and says so.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.checks.findings import CHECKLIST, Finding
from app.checks.ledger_accounts import account_code
from app.checks.text import money
from app.checks.view import GrantView, net_of
from app.contracts.charges import Charge
from app.contracts.checks import Bucket, ChargeStatus
from app.contracts.records import BenefitGroup, Rate, Record, RecordKind

# The "Benefit rate" item's key in the account groups table.
BENEFIT_RATE = "benefit_rate"
WAITS_ON_SALARY = "waits_on_salary"

GROUP_NAMES: dict[BenefitGroup, str] = {
    BenefitGroup.ACADEMIC: "Academic",
    BenefitGroup.STAFF: "Staff",
    BenefitGroup.LIMITED: "Limited",
    BenefitGroup.NO_BENEFIT_ELIGIBILITY: "No Benefit Eligibility",
    BenefitGroup.STUDENT: "Student",
}

# Berkeley's composite benefit rate assessment accounts, one per group. Verified: the
# names as Berkeley's Composite Benefit Rates page lists them
# (cfo.berkeley.edu/about-us/financial-planning-analysis/central-resource-management/
# composite-benefit-rates-cbr). 53090 "Benefit Assessment - Contra" belongs to no group.
BENEFIT_ACCOUNTS: dict[str, BenefitGroup] = {
    "53060": BenefitGroup.ACADEMIC,  # Benefit Assess-Acad Regular
    "53070": BenefitGroup.STAFF,  # Benefit Assess-Staff Regular
    "53080": BenefitGroup.LIMITED,  # Benefit Assessment - Limited
    "53085": BenefitGroup.NO_BENEFIT_ELIGIBILITY,  # Benefit Assess - No Eligibility
    "53086": BenefitGroup.STUDENT,  # Benefit Assessment - Student
}

# UNVERIFIED: which salary accounts carry each group's pay. From Berkeley's BFS chart of
# accounts report as of September 2020 (controller.berkeley.edu, "BFS General Ledger
# Chart of Accounts Reports", page 4), read only through a search engine's summary: the
# page itself answers 403. The account alone may not tell the group: postdocs and
# faculty summer salary are in the Limited group but may be paid on an academic wage
# account, and no account was found for Student pay. So no account is mapped to Limited
# from the academic range, and none to Student.
SALARY_ACCOUNTS: dict[str, BenefitGroup] = {
    "50211": BenefitGroup.ACADEMIC,  # academic, non-teaching
    "50212": BenefitGroup.ACADEMIC,  # academic, non-teaching
    "50215": BenefitGroup.ACADEMIC,  # Academic Wages, the regular default
    "50240": BenefitGroup.ACADEMIC,  # academic, teaching
    "50241": BenefitGroup.ACADEMIC,  # academic, teaching
    "50242": BenefitGroup.ACADEMIC,  # academic, teaching
    "51210": BenefitGroup.STAFF,  # staff wages, the regular default
    "51231": BenefitGroup.NO_BENEFIT_ELIGIBILITY,  # staff exempt from the benefit rate
    "51232": BenefitGroup.LIMITED,  # limited-benefit staff
}


def benefit_group(charge: Charge) -> BenefitGroup | None:
    """The group a benefit charge's account tells, or None for any other account."""
    code = account_code(charge.account)
    return BENEFIT_ACCOUNTS.get(code) if code is not None else None


def salary_group(charge: Charge) -> BenefitGroup | None:
    """The group a salary line's account tells (unverified table), or None."""
    code = account_code(charge.account)
    return SALARY_ACCOUNTS.get(code) if code is not None else None


def month_of(d: date) -> date:
    return d.replace(day=1)


def month_name(month: date) -> str:
    return f"{month:%B %Y}"


@dataclass
class Cell:
    """One group's benefit charges and salary lines in one month, on one grant."""

    group: BenefitGroup
    month: date  # its first day
    benefit_ids: list[str] = field(default_factory=list[str])
    salary_ids: list[str] = field(default_factory=list[str])
    benefit_cents: int = 0
    salary_cents: int = 0


def _counted(view: GrantView, charge: Charge) -> bool:
    """A line that nets into another is counted inside that line's net (decision 0020)."""
    found = view.nets.get(charge.id)
    return found is None or found.nets_into is None


def cells(view: GrantView) -> dict[tuple[BenefitGroup, date], Cell]:
    """The grant's cells, by group and month, for every group with a benefit charge.

    Worked out once per view: read them from `GrantView.benefit_cells`.
    """
    out: dict[tuple[BenefitGroup, date], Cell] = {}
    for c in view.charges:
        group = benefit_group(c)
        if group is None or not _counted(view, c):
            continue
        cell = out.setdefault(
            (group, month_of(c.transaction_date)), Cell(group, month_of(c.transaction_date))
        )
        cell.benefit_ids.append(c.id)
        cell.benefit_cents += net_of(view, c)
    for c in view.charges:
        group = salary_group(c)
        if group is None or not _counted(view, c):
            continue
        cell = out.get((group, month_of(c.transaction_date)))
        if cell is not None:
            cell.salary_ids.append(c.id)
            cell.salary_cents += net_of(view, c)
    return out


def cell_of(view: GrantView, charge: Charge) -> Cell | None:
    """The cell a benefit charge is recalculated in, or None when it isn't."""
    group = benefit_group(charge)
    if group is None or not _counted(view, charge):
        return None
    return view.benefit_cells.get((group, month_of(charge.transaction_date)))


def _rates(terms: Sequence[Record], group: BenefitGroup, on: date) -> list[Record]:
    """The rate terms for a group that start on or before a day, the one in force last."""
    found = [
        r
        for r in terms
        if isinstance(r.data, Rate)
        and r.data.applies_to is not None
        and r.data.applies_to.value == group
        and (r.data.effective_from is None or r.data.effective_from.value <= on)
    ]

    def order(r: Record) -> tuple[date, date]:
        assert isinstance(r.data, Rate)
        start = r.data.effective_from.value if r.data.effective_from else date.min
        return (start, r.data.dated.value)

    return sorted(found, key=order)  # stable: the order the records were written breaks a tie


def rate_in_force(view: GrantView, group: BenefitGroup, on: date) -> Record | None:
    """The confirmed rate for a group in force on a day: the latest to start on or before it.

    A confirmed rate stays in force until a later confirmed one starts, whatever its own
    end date says (product answer to ruling 61's first question).
    """
    found = _rates(view.terms[RecordKind.RATE], group, on)
    return found[-1] if found else None


def waiting_rate(view: GrantView, group: BenefitGroup, on: date) -> Record | None:
    """A rate term for the group, waiting for the accountant, that would cover the day."""
    found = _rates([r for r in view.waiting_terms if r.kind == RecordKind.RATE], group, on)
    return found[-1] if found else None


def tolerance(cell: Cell) -> int:
    """Rounding: a cent for each salary line counted, at least one."""
    return max(1, len(cell.salary_ids))


@dataclass
class Recalculation:
    """What a benefit charge's recalculation found, for its "Benefit rate" item."""

    filled: bool
    rate_id: str | None = None
    charge_ids: tuple[str, ...] = ()  # the salary lines counted
    findings: list[Finding] = field(default_factory=list[Finding])


def recalculate(charge: Charge, view: GrantView, needed: str) -> Recalculation | None:
    """Recalculate a benefit charge's cell. None when its account isn't a group's."""
    cell = cell_of(view, charge)
    if cell is None:
        return None
    name = GROUP_NAMES[cell.group]
    month = month_name(cell.month)
    problem = BENEFIT_RATE
    if cell.group not in SALARY_ACCOUNTS.values():
        return Recalculation(
            filled=False,
            findings=[
                Finding(
                    CHECKLIST,
                    f"salary_group_unknown:{problem}",
                    Bucket.NEEDS_HUMAN,
                    f"{needed}: code can't tell which salary lines are {name} pay, so the "
                    f"{name} benefits for {month} can't be recalculated.",
                )
            ],
        )
    if not cell.salary_ids:
        # Nothing to recalculate from: never filled, whatever the benefits add up to
        # (PR 219's review). Not "$0 expected", which a reversed benefit would match.
        return Recalculation(
            filled=False,
            findings=[
                Finding(
                    CHECKLIST,
                    f"no_salary:{problem}",
                    Bucket.NEEDS_HUMAN,
                    f"{needed}: there are no {name} salary lines on this grant in {month}, "
                    f"so the {name} benefits charged that month can't be recalculated.",
                )
            ],
        )
    rate = rate_in_force(view, cell.group, cell.month)
    if rate is None:
        waiting = waiting_rate(view, cell.group, cell.month)
        if waiting is not None:
            return Recalculation(
                filled=False,
                findings=[
                    Finding(
                        CHECKLIST,
                        f"rate_not_confirmed:{problem}",
                        Bucket.NEEDS_HUMAN,
                        f"{needed}: the {name} benefit rate for {month} isn't confirmed yet.",
                        [waiting.id],
                        shown_on_term=True,
                    )
                ],
                charge_ids=tuple(cell.salary_ids),
            )
        return Recalculation(
            filled=False,
            charge_ids=tuple(cell.salary_ids),
            findings=[
                Finding(
                    CHECKLIST,
                    f"no_rate:{problem}",
                    Bucket.NEEDS_HUMAN,
                    f"{needed}: no confirmed {name} benefit rate covers {month}.",
                )
            ],
        )
    assert isinstance(rate.data, Rate)
    value = rate.data.rate.value
    expected = int(
        (Decimal(cell.salary_cents) * value).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    )
    salary = tuple(cell.salary_ids)
    if abs(cell.benefit_cents - expected) <= tolerance(cell):
        return Recalculation(filled=True, rate_id=rate.id, charge_ids=salary)
    percent = f"{(value * 100).normalize():f}%"
    return Recalculation(
        filled=False,
        rate_id=rate.id,
        charge_ids=salary,
        findings=[
            Finding(
                CHECKLIST,
                f"rate_math:{problem}",
                Bucket.NEEDS_HUMAN,
                f"{needed}: the {name} benefits charged for {month} add up to "
                f"{money(cell.benefit_cents)}, but {percent} of the {money(cell.salary_cents)} "
                f"of {name} salary that month is {money(expected)}.",
                [rate.id],
                expected_cents=expected,
            )
        ],
    )


def salary_done(status: ChargeStatus) -> bool:
    """A salary line a benefit charge no longer waits on."""
    return status.bucket == Bucket.EVIDENCE_COMPLETE or status.accepted or status.reversed


def waits_on_salary(charge: Charge, view: GrantView, done: Mapping[str, bool]) -> list[Finding]:
    """The "waits on its salary lines" reason, while any of its salary lines isn't done."""
    cell = cell_of(view, charge)
    if cell is None:
        return []
    waiting = [s for s in cell.salary_ids if not done.get(s, False)]
    if not waiting:
        return []
    lines = ", ".join(
        f"ledger line {c.ledger_line_id}" for c in view.charges if c.id in set(waiting)
    )
    return [
        Finding(
            CHECKLIST,
            WAITS_ON_SALARY,
            Bucket.MISSING_EVIDENCE,
            f"Waits on its salary lines ({lines}): a benefit charge isn't complete until "
            "the salary it's charged on is.",
            # The salary line's row on the problem list stands for it (ruling 62).
            shown_on_term=True,
        )
    ]


def waiting_on(statuses: Sequence[ChargeStatus]) -> dict[str, tuple[str, ...]]:
    """Ruling 62: for each salary line, the benefit charges whose only problem is that they
    wait on it, for its row on the problem list (ChargeProblemRow.waiting_charge_ids).

    Pure over run_checks' charge statuses. A benefit charge counts when every failing
    reason not accepted is "waits on its salary lines"; it waits on the salary lines its
    "Benefit rate" item counted that aren't done yet.
    """
    by_id = {s.charge_id: s for s in statuses}
    out: dict[str, list[str]] = {}
    for s in statuses:
        open_ = [
            r for r in s.reasons if r.bucket != Bucket.EVIDENCE_COMPLETE and r.accepted_by is None
        ]
        if not open_ or any(r.problem != WAITS_ON_SALARY for r in open_):
            continue
        entry = next((e for e in s.checklist if e.default_item == BENEFIT_RATE), None)
        for salary_id in entry.charge_ids if entry is not None else ():
            found = by_id.get(salary_id)
            if found is not None and not salary_done(found):
                out.setdefault(salary_id, []).append(s.charge_id)
    return {k: tuple(v) for k, v in out.items()}
