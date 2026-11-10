"""Ruling 61: a benefit charge is recalculated from its group's salary lines and rate."""

from datetime import date
from typing import Any

from app.checks.benefits import waiting_on
from app.contracts.checks import Bucket, ChargeStatus
from tests.checks.grant_builder import Grant, at, cited, failing, problems

STAFF_PAY = "51210 Staff Wages"
STAFF_BENEFITS = "53070 Benefit Assess-Staff Regular"
ACADEMIC_PAY = "50215 Academic Wages"
ACADEMIC_BENEFITS = "53060 Benefit Assess-Acad Regular"
STUDENT_BENEFITS = "53086 Benefit Assessment - Student"
NOW = at(2024, 4, 2)


def rate(
    g: Grant,
    group: str,
    value: str,
    start: date,
    end: date | None,
    confirm: bool = True,
    name: str = "Composite benefit rate",
) -> str:
    """A rate term the agent read from the rate agreement, confirmed by the accountant."""
    data: dict[str, Any] = {
        "kind": "rate",
        "dated": cited(date(2023, 6, 1), file_id="f-rates"),
        "name": cited(name, file_id="f-rates"),
        "rate": cited(value, f"{value}", "f-rates"),
        "applies_to": cited(group, group.title(), "f-rates"),
        "effective_from": cited(start, f"{start}", "f-rates"),
    }
    if end is not None:
        data["effective_to"] = cited(end, f"{end}", "f-rates")
    r = g.agent(data, at(2023, 6, 2))
    if confirm:
        g.confirm(r, when=at(2023, 6, 3))
    return r


def grant() -> tuple[Grant, dict[str, str]]:
    g = Grant()
    g.standard_terms()
    lines = {
        "fringe": g.confirmed_line("Fringe Benefits", "fringe_benefits", at(2023, 1, 12)),
        "pay": g.confirmed_line("Other Personnel", "other_personnel", at(2023, 1, 12)),
    }
    return g, lines


def pay(g: Grant, lines: dict[str, str], id: str, on: date, cents: int, account: str = STAFF_PAY):
    g.charge(id, on, cents, account=account, vendor=None)
    g.assign(id, lines["pay"], at(on.year, on.month, on.day))


def benefit(
    g: Grant, lines: dict[str, str], id: str, on: date, cents: int, account: str = STAFF_BENEFITS
):
    g.charge(id, on, cents, account=account, vendor=None)
    g.assign(id, lines["fringe"], at(on.year, on.month, on.day))


def complete(g: Grant, salary_id: str, on: date) -> None:
    """Fill a salary line's appointment letter and its month's effort report."""
    f = g.file(f"f-{salary_id}", at(on.year, on.month, on.day))
    letter = g.note(f, at(on.year, on.month, on.day))
    g.link(letter, salary_id, at(on.year, on.month, on.day), default="appointment_letter")
    report = g.note(f, at(on.year, on.month, on.day), on.replace(day=1), on)
    g.link(report, salary_id, at(on.year, on.month, on.day), default="effort_report")
    g.answer(salary_id, "supports", at(on.year, on.month, on.day), rests_on=[letter])


def entry(status: ChargeStatus):
    return next(e for e in status.checklist if e.default_item == "benefit_rate")


def status(g: Grant, charge_id: str) -> ChargeStatus:
    return g.status(charge_id, NOW)


def test_a_matching_benefit_charge_fills_its_item_from_the_rate_and_the_salary() -> None:
    g, lines = grant()
    r = rate(g, "staff", "0.428", date(2023, 7, 1), date(2024, 6, 30))
    pay(g, lines, "sal", date(2024, 3, 31), 1_000_000)
    benefit(g, lines, "ben", date(2024, 3, 31), 428_000)
    e = entry(status(g, "ben"))
    assert (e.filled, e.rate_id, e.charge_ids, e.link_ids) == (True, r, ("sal",), ())


def test_it_waits_on_its_salary_lines_without_a_row_of_its_own() -> None:
    g, lines = grant()
    rate(g, "staff", "0.428", date(2023, 7, 1), date(2024, 6, 30))
    pay(g, lines, "sal", date(2024, 3, 31), 1_000_000)
    benefit(g, lines, "ben", date(2024, 3, 31), 428_000)
    out = g.run(NOW)
    ben = next(s for s in out.charges if s.charge_id == "ben")
    assert problems(ben) == {("checklist", "waits_on_salary")}
    assert ben.bucket == Bucket.MISSING_EVIDENCE
    assert "ledger line L-sal" in failing(ben)[0].text
    assert not ben.flagged  # long after its posting date, still not a row of its own
    assert not g.status("ben", at(2025, 6, 1)).flagged
    # Ruling 62: the salary line's row carries it.
    assert waiting_on(out.charges) == {"sal": ("ben",)}


def test_it_is_complete_once_its_salary_lines_are() -> None:
    g, lines = grant()
    rate(g, "staff", "0.428", date(2023, 7, 1), date(2024, 6, 30))
    pay(g, lines, "sal", date(2024, 3, 31), 1_000_000)
    benefit(g, lines, "ben", date(2024, 3, 31), 428_000)
    complete(g, "sal", date(2024, 3, 31))
    out = g.run(NOW)
    assert [s.bucket for s in out.charges] == [Bucket.EVIDENCE_COMPLETE] * 2
    assert waiting_on(out.charges) == {}


def test_a_mismatch_is_needs_a_human_with_the_amount_expected() -> None:
    g, lines = grant()
    r = rate(g, "staff", "0.428", date(2023, 7, 1), date(2024, 6, 30))
    pay(g, lines, "sal", date(2024, 3, 31), 1_000_000)
    benefit(g, lines, "ben", date(2024, 3, 31), 440_000)  # 44.0%, next year's rate
    s = status(g, "ben")
    reason = next(x for x in s.reasons if x.problem == "rate_math:benefit_rate")
    assert (reason.bucket, reason.expected_cents, reason.record_ids) == (
        Bucket.NEEDS_HUMAN,
        428_000,
        (r,),
    )
    assert "$4,400.00" in reason.text and "$4,280.00" in reason.text
    assert s.flagged  # its own problem: its own row
    e = entry(s)
    assert (e.filled, e.rate_id, e.charge_ids) == (False, r, ("sal",))
    assert waiting_on(g.run(NOW).charges) == {}  # not its only problem


def test_a_month_adds_up_every_line_of_the_group_within_rounding() -> None:
    """Two paychecks: each rounded on its own, so the month is off by a cent."""
    g, lines = grant()
    rate(g, "staff", "0.428", date(2023, 7, 1), date(2024, 6, 30))
    pay(g, lines, "s1", date(2024, 3, 15), 123_457)
    pay(g, lines, "s2", date(2024, 3, 31), 123_457)
    benefit(g, lines, "b1", date(2024, 3, 15), 52_840)  # 52,839.6 rounded
    benefit(g, lines, "b2", date(2024, 3, 31), 52_840)
    pay(g, lines, "other_month", date(2024, 4, 1), 900_000)
    pay(g, lines, "academic", date(2024, 3, 31), 500_000, account=ACADEMIC_PAY)
    assert 105_680 - round(246_914 * 0.428) == 1
    for b in ("b1", "b2"):
        e = entry(status(g, b))
        assert (e.filled, e.charge_ids) == (True, ("s1", "s2"))
    g2, lines2 = grant()
    rate(g2, "staff", "0.428", date(2023, 7, 1), date(2024, 6, 30))
    pay(g2, lines2, "s1", date(2024, 3, 15), 123_457)
    benefit(g2, lines2, "b1", date(2024, 3, 15), 52_842)  # 2 cents off one line: too far
    assert "rate_math:benefit_rate" in {p for _, p in problems(status(g2, "b1"))}


def test_the_salary_counts_net_of_the_lines_that_correct_it() -> None:
    """Decision 0020: half the salary moved off the grant, counted in the month it was paid."""
    g, lines = grant()
    rate(g, "staff", "0.428", date(2023, 7, 1), date(2024, 6, 30))
    pay(g, lines, "sal", date(2024, 3, 31), 1_000_000)
    g.charge(
        "moved",
        date(2024, 5, 10),
        -500_000,
        account=STAFF_PAY,
        vendor=None,
        original_line_id="L-sal",
    )
    benefit(g, lines, "ben", date(2024, 3, 31), 214_000)
    e = entry(g.status("ben", at(2024, 5, 11)))
    assert (e.filled, e.charge_ids) == (True, ("sal",))


def test_the_rate_is_the_one_for_the_fiscal_year_the_salary_falls_in() -> None:
    g, lines = grant()
    fy24 = rate(g, "staff", "0.428", date(2023, 7, 1), date(2024, 6, 30))
    fy25 = rate(g, "staff", "0.44", date(2024, 7, 1), date(2025, 6, 30))
    pay(g, lines, "june", date(2024, 6, 30), 1_000_000)
    benefit(g, lines, "b-june", date(2024, 6, 30), 428_000)
    pay(g, lines, "july", date(2024, 7, 31), 1_000_000)
    benefit(g, lines, "b-july", date(2024, 7, 31), 440_000)
    now = at(2024, 8, 1)
    assert entry(g.status("b-june", now)).rate_id == fy24
    assert entry(g.status("b-july", now)).rate_id == fy25


def test_a_confirmed_rate_stays_in_force_until_a_later_one_starts() -> None:
    """Product answer: no provisional state. Past its own end date, with no later rate
    confirmed, the rate still applies; a charge at another rate simply mismatches."""
    g, lines = grant()
    fy24 = rate(g, "staff", "0.428", date(2023, 7, 1), date(2024, 6, 30))
    pay(g, lines, "july", date(2024, 7, 31), 1_000_000)
    benefit(g, lines, "b-july", date(2024, 7, 31), 428_000)
    e = entry(g.status("b-july", at(2024, 8, 1)))
    assert (e.filled, e.rate_id) == (True, fy24)


def test_a_rate_with_no_end_date_covers_until_amended() -> None:
    g, lines = grant()
    r = rate(g, "staff", "0.44", date(2024, 7, 1), None)
    pay(g, lines, "sal", date(2026, 3, 31), 1_000_000)
    benefit(g, lines, "ben", date(2026, 3, 31), 440_000)
    e = entry(g.status("ben", at(2026, 4, 1)))
    assert (e.filled, e.rate_id) == (True, r)


def test_no_confirmed_rate_is_needs_a_human() -> None:
    g, lines = grant()
    rate(g, "academic", "0.344", date(2023, 7, 1), date(2024, 6, 30))  # another group
    pay(g, lines, "sal", date(2024, 3, 31), 1_000_000)
    benefit(g, lines, "ben", date(2024, 3, 31), 428_000)
    s = status(g, "ben")
    reason = next(x for x in s.reasons if x.problem == "no_rate:benefit_rate")
    assert reason.bucket == Bucket.NEEDS_HUMAN
    assert "no confirmed Staff benefit rate covers March 2024" in reason.text
    assert s.flagged
    assert entry(s).charge_ids == ("sal",)  # the salary lines it would be recalculated from


def test_a_rate_waiting_for_the_accountant_shows_on_the_term_row() -> None:
    g, lines = grant()
    waiting = rate(g, "staff", "0.428", date(2023, 7, 1), date(2024, 6, 30), confirm=False)
    pay(g, lines, "sal", date(2024, 3, 31), 1_000_000)
    benefit(g, lines, "ben", date(2024, 3, 31), 428_000)
    s = status(g, "ben")
    reason = next(x for x in s.reasons if x.problem == "rate_not_confirmed:benefit_rate")
    assert (reason.bucket, reason.record_ids) == (Bucket.NEEDS_HUMAN, (waiting,))
    assert not s.flagged  # the rate term's own row stands for it


def test_a_group_with_no_known_salary_account_says_it_cant_be_recalculated() -> None:
    g, lines = grant()
    rate(g, "student", "0.023", date(2023, 7, 1), date(2024, 6, 30))
    benefit(g, lines, "ben", date(2024, 3, 31), 2_300, account=STUDENT_BENEFITS)
    s = status(g, "ben")
    assert ("checklist", "salary_group_unknown:benefit_rate") in problems(s)
    assert s.flagged


def test_another_benefits_account_keeps_its_linked_item() -> None:
    g, lines = grant()
    g.charge("oasdi", date(2024, 3, 31), 10_000, account="53100 OASDI", vendor=None)
    g.assign("oasdi", lines["fringe"], at(2024, 3, 31))
    s = status(g, "oasdi")
    assert ("checklist", "missing:benefit_rate") in problems(s)
    assert (entry(s).rate_id, entry(s).charge_ids) == (None, ())


def test_rates_for_several_groups_from_one_agreement_dont_disagree() -> None:
    g, lines = grant()
    rate(g, "staff", "0.428", date(2023, 7, 1), date(2024, 6, 30))
    rate(g, "academic", "0.344", date(2023, 7, 1), date(2024, 6, 30))
    rate(g, "staff", "0.44", date(2024, 7, 1), date(2025, 6, 30))
    out = g.run(NOW)
    assert not [r for r in out.records for p in r.problems if "disagree" in p.problem]


def test_an_accepted_salary_line_is_no_longer_waited_on() -> None:
    g, lines = grant()
    rate(g, "staff", "0.428", date(2023, 7, 1), date(2024, 6, 30))
    pay(g, lines, "sal", date(2024, 3, 31), 1_000_000)
    benefit(g, lines, "ben", date(2024, 3, 31), 428_000)
    for problem in ("missing:appointment_letter", "missing:effort_report"):
        g.user(
            {
                "kind": "accepted_reason",
                "charge_id": "sal",
                "reason": {"check": "checklist", "problem": problem},
                "note": "Covered by the department's records.",
            },
            at(2024, 4, 1),
        )
    out = g.run(NOW)
    sal = next(s for s in out.charges if s.charge_id == "sal")
    assert sal.accepted
    ben = next(s for s in out.charges if s.charge_id == "ben")
    assert ben.bucket == Bucket.EVIDENCE_COMPLETE
