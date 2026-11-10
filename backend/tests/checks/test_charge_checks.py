"""Each check about a charge, passing and failing: checks 1, 2, 3, 5 and 6, and the budget line."""

from datetime import date
from decimal import Decimal

from app.contracts.checks import Bucket, most_serious

from .grant_builder import (
    NO_GROUP,
    PI_EMAIL,
    SALARY,
    STIPENDS,
    TRAVEL,
    Grant,
    at,
    cited,
    failing,
    problems,
)

# The cost's date (check 1).


def test_a_cost_inside_the_period_passes() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2024, 5, 1), 10000, at(2024, 5, 1), line=t["ms"])
    status = g.status("c1", at(2024, 5, 2))
    assert status.bucket == Bucket.EVIDENCE_COMPLETE
    assert failing(status) == []
    assert not status.flagged


def test_a_cost_after_the_end_date_is_possible_conflict() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2026, 2, 20), 10000, at(2026, 2, 20), line=t["ms"])
    status = g.status("c1", at(2026, 2, 21))
    assert status.bucket == Bucket.POSSIBLE_CONFLICT
    assert problems(status) == {("period_of_performance", "after_end_date")}
    assert status.flagged


def test_a_cost_up_to_90_days_before_the_start_asks_for_the_universitys_pre_award_approval() -> (
    None
):
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2023, 1, 2), 10000, at(2023, 1, 2), line=t["ms"])
    status = g.status("c1", at(2023, 1, 13))
    date_reason = next(r for r in status.reasons if r.check == "period_of_performance")
    assert date_reason.bucket == Bucket.EVIDENCE_COMPLETE
    assert status.bucket == Bucket.MISSING_EVIDENCE
    assert problems(status) == {("approval", "missing:pre_award_approval")}
    assert status.flagged  # a missing approval goes on the list right away
    assert "pre_award_approval" in [e.default_item for e in status.checklist]


def test_a_cost_more_than_90_days_before_the_start_is_possible_conflict() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2022, 10, 1), 10000, at(2023, 1, 13), line=t["ms"])
    status = g.status("c1", at(2023, 1, 14))
    assert status.bucket == Bucket.POSSIBLE_CONFLICT
    assert ("period_of_performance", "before_start") in problems(status)
    # Code asks whether an approval covers it only once one is linked.
    assert "pre_award_approval" not in [e.default_item for e in status.checklist]


def test_nsf_approval_on_file_clears_a_cost_more_than_90_days_before_the_start() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2022, 10, 1), 10000, at(2023, 1, 13), line=t["ms"])
    f = g.file("f-approval", at(2023, 1, 13))
    a = g.approval(f, at(2023, 1, 13), on=date(2022, 9, 1))
    g.link(a, "c1", at(2023, 1, 13))
    out = g.run(at(2023, 1, 13, 13))
    status = next(c for c in out.charges if c.charge_id == "c1")
    assert ("covers", "not_answered") in problems(status)
    assert [(q.question, q.record_id) for q in out.questions if q.charge_id == "c1"] == [
        ("allowable", None),
        ("covers", a),
    ]

    g.answer("c1", "supports", at(2023, 1, 13, 14), question="covers", record_id=a, rests_on=[a])
    g.answer("c1", "supports", at(2023, 1, 13, 14))  # a fresh Allowable answer after the new link
    status = g.status("c1", at(2023, 1, 13, 15))
    assert ("period_of_performance", "before_start") not in problems(status)
    assert status.bucket == Bucket.EVIDENCE_COMPLETE


def test_with_no_confirmed_dates_each_charge_is_needs_a_human_and_other_checks_still_run() -> None:
    g = Grant()
    t = g.standard_terms(confirm=False)
    g.supplies_charge("c1", date(2023, 5, 1), 10000, at(2023, 5, 1), line=t["ms"])
    status = g.status("c1", at(2023, 5, 2))
    assert status.bucket == Bucket.NEEDS_HUMAN
    date_reason = next(r for r in status.reasons if r.check == "period_of_performance")
    assert date_reason.text == "The grant's dates aren't confirmed yet."
    assert ("budget_line", "line_not_confirmed") in problems(status)
    checklist = next(r for r in status.reasons if r.check == "checklist")
    assert checklist.bucket == Bucket.EVIDENCE_COMPLETE  # the checklist and amounts still run


def test_an_older_confirmed_period_stays_in_force_while_a_correction_waits() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2026, 3, 1), 10000, at(2026, 3, 1), line=t["ms"])
    fixed = {
        "kind": "period_of_performance",
        "dated": cited(date(2023, 1, 10)),
        "start": cited(date(2023, 2, 1)),
        "end": cited(date(2027, 1, 31)),
    }
    g.agent(fixed, at(2026, 3, 2), replaces=t["period"])
    assert g.status("c1", at(2026, 3, 3)).bucket == Bucket.POSSIBLE_CONFLICT


def test_confirmed_periods_that_disagree_put_the_date_check_in_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms()
    other = g.period(date(2023, 2, 1), date(2025, 1, 31), date(2023, 1, 10), at(2023, 2, 1))
    g.confirm(other, when=at(2023, 2, 1, 13))
    g.supplies_charge("c1", date(2024, 5, 1), 10000, at(2024, 5, 1), line=t["ms"])
    out = g.run(at(2024, 5, 2))
    status = out.charges[0]
    assert ("period_of_performance", "terms_disagree") in problems(status)
    assert {r.record_id for r in out.records if r.problems[0].problem == "disagree"} == {
        t["period"],
        other,
    }


# The checklist and its sums (check 2).


def test_a_missing_bill_is_missing_evidence_expected_on_the_posting_date() -> None:
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2024, 3, 1), 10000, posted=date(2024, 3, 2))
    g.assign("c1", t["ms"], at(2024, 3, 2))
    status = g.status("c1", at(2024, 3, 3))
    assert status.bucket == Bucket.MISSING_EVIDENCE
    (reason,) = failing(status)
    assert (reason.check, reason.problem, reason.expected_by) == (
        "checklist",
        "missing:bill",
        date(2024, 3, 2),
    )
    assert reason.text == "Missing: A bill that adds up to the charge."
    assert [(e.default_item, e.amount_cents, e.filled) for e in status.checklist] == [
        ("bill", 10000, False)
    ]


def test_bills_under_the_item_are_missing_evidence_and_over_is_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms()
    for cid, linked in (("under", 6000), ("over", 12000)):
        g.charge(cid, date(2024, 3, 1), 10000)
        f = g.file(f"f-{cid}", at(2024, 3, 1))
        b = g.bill(12000, f, at(2024, 3, 1))
        g.link(b, cid, at(2024, 3, 1), amount=linked, default="bill")
        g.assign(cid, t["ms"], at(2024, 3, 1))
        g.answer(cid, "supports", at(2024, 3, 1), rests_on=[b])
    under = g.status("under", at(2024, 3, 2))
    assert under.bucket == Bucket.MISSING_EVIDENCE
    assert (
        failing(under)[0].text
        == "A bill that adds up to the charge: the bills linked add up to $60.00 of $100.00."
    )
    over = g.status("over", at(2024, 3, 2))
    assert over.bucket == Bucket.NEEDS_HUMAN
    assert problems(over) == {("checklist", "over:bill")}


def _trip(g: Grant, t: dict[str, str], per_diem_amount: int = 50000, airfare: int = 180000) -> None:
    """A $2,300 trip: airfare receipt $1,800 and per diem, 5 days at $100 a day."""
    g.charge("trip", date(2024, 4, 1), 230000, account=g_travel())
    when = at(2024, 4, 2)
    f = g.file("f-trip", when)
    air = g.item("trip", "Airfare receipt", when, amount_cents=airfare)
    g.item(
        "trip",
        "Per diem, 5 days at $100 a day",
        when,
        amount_cents=per_diem_amount,
        rate={
            "quantity": cited(Decimal("5"), "5 days", f),
            "rate": cited(Decimal("10000"), "$100 a day", f),
        },
    )
    receipt = g.bill(airfare, f, when)
    g.link(receipt, "trip", when, amount=airfare, item=air)
    report = g.note(f, when)
    g.link(report, "trip", when, default="expense_report")
    g.answer("trip", "supports", when, rests_on=[receipt])


def g_travel() -> str:
    return TRAVEL


def test_a_trip_with_a_receipt_and_a_per_diem_rate_adds_up() -> None:
    g = Grant()
    t = g.standard_terms()
    _trip(g, t)
    status = g.status("trip", at(2024, 4, 3))
    assert status.bucket == Bucket.EVIDENCE_COMPLETE
    bills = next(e for e in status.checklist if e.default_item == "bills")
    # The bill-like default covers what the other items don't: nothing, so it isn't missing.
    assert (bills.amount_cents, bills.filled) == (0, True)


def test_a_rate_whose_math_doesnt_check_is_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms()
    _trip(g, t, per_diem_amount=48000)
    status = g.status("trip", at(2024, 4, 3))
    assert ("checklist", "rate_math:item:per_diem_5_days_at_100_a_day") in problems(status)
    assert status.bucket == Bucket.NEEDS_HUMAN


def test_items_that_add_up_to_more_than_the_charge_are_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms()
    _trip(g, t, airfare=200000)
    status = g.status("trip", at(2024, 4, 3))
    assert ("checklist", "items_over_charge") in problems(status)
    assert status.bucket == Bucket.NEEDS_HUMAN


def test_a_salary_line_has_no_amounts_and_its_effort_report_must_cover_the_month() -> None:
    g = Grant()
    g.standard_terms()
    g.charge("sal", date(2024, 1, 31), 600000, account=SALARY, vendor=None)
    f = g.file("f-effort", at(2024, 10, 1))
    letter = g.note(f, at(2024, 10, 1))
    g.link(letter, "sal", at(2024, 10, 1), default="appointment_letter")
    wrong = g.note(f, at(2024, 10, 1), start=date(2024, 2, 1), end=date(2024, 6, 30))
    g.link(wrong, "sal", at(2024, 10, 1), default="effort_report")
    status = g.status("sal", at(2024, 10, 2))
    effort = next(e for e in status.checklist if e.default_item == "effort_report")
    assert not effort.filled
    assert effort.expected_by == date(2024, 10, 28)  # 120 days after the half-year ends

    right = g.note(f, at(2024, 10, 3), start=date(2024, 1, 1), end=date(2024, 6, 30))
    g.link(right, "sal", at(2024, 10, 3), default="effort_report")
    status = g.status("sal", at(2024, 10, 4))
    assert all(e.filled for e in status.checklist)
    # No item carries an amount, so the sum check passes.
    assert not any(r.problem.startswith("items_") for r in status.reasons)


def test_an_empty_checklist_is_needs_a_human() -> None:
    g = Grant()
    g.standard_terms()
    g.charge("c1", date(2024, 3, 1), 10000, account=NO_GROUP)
    status = g.status("c1", at(2024, 3, 2))
    assert status.checklist == ()
    assert problems(status) == {("checklist", "empty")}
    assert status.bucket == Bucket.NEEDS_HUMAN


def test_the_agents_removal_waits_and_the_accountants_takes_effect() -> None:
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2024, 3, 1), 10000)
    g.assign("c1", t["ms"], at(2024, 3, 1))
    removal = g.agent(
        {"kind": "checklist_removal", "charge_id": "c1", "default_item": "bill"}, at(2024, 3, 2)
    )
    status = g.status("c1", at(2024, 3, 3))
    (entry,) = status.checklist
    assert entry.removal_waiting_id == removal
    assert ("suggestion", f"waiting:{removal}") in problems(status)
    assert status.bucket == Bucket.NEEDS_HUMAN

    g.user({"kind": "checklist_removal", "charge_id": "c1", "default_item": "bill"}, at(2024, 3, 4))
    assert g.status("c1", at(2024, 3, 5)).checklist == ()


def test_a_reversal_gets_its_two_default_items_in_place_of_the_groups() -> None:
    g = Grant()
    g.standard_terms()
    g.charge("rev", date(2024, 3, 1), -40000, original_line_id="L-orig")
    status = g.status("rev", at(2024, 3, 2))
    assert [e.default_item for e in status.checklist] == ["corrected_line", "justification"]
    assert problems(status) == {
        ("checklist", "missing:corrected_line"),
        ("checklist", "missing:justification"),
    }


# Required approvals (check 3).


def _stipend(g: Grant, t: dict[str, str], line: str = "psc", when=None) -> None:  # type: ignore[no-untyped-def]
    when = when or at(2024, 6, 2)
    g.charge("stip", date(2024, 6, 1), 50000, account=STIPENDS, vendor=None)
    f = g.file("f-stip", when)
    roster = g.note(f, when)
    g.link(roster, "stip", when, default="participant_list")
    paid = g.bill(50000, f, when)
    g.link(paid, "stip", when, amount=50000, default="payment_record")
    g.assign("stip", t[line], when)
    g.answer("stip", "supports", when, rests_on=[paid])


def _approve(g: Grant, t: dict[str, str], **kw) -> str:  # type: ignore[no-untyped-def]
    when = at(2024, 6, 3)
    source = kw.pop("source", "upload")
    f = g.file(
        "f-ok",
        when,
        source=source,
        media_type="message/rfc822" if source == "gmail" else "text/plain",
    )
    a = g.approval(f, when, **kw)
    g.link(a, "stip", when, default=f"approval:{t['rule']}")
    g.answer("stip", "supports", when, question="covers", record_id=a, rests_on=[a])
    g.answer("stip", "supports", when)
    return a


def test_a_required_approval_that_is_missing_is_missing_evidence_flagged_right_away() -> None:
    g = Grant()
    t = g.standard_terms()
    _stipend(g, t)
    status = g.status("stip", at(2024, 6, 2, 13))
    assert status.bucket == Bucket.MISSING_EVIDENCE
    assert problems(status) == {("approval", f"missing:approval:{t['rule']}")}
    assert status.flagged
    entry = next(e for e in status.checklist if e.default_item == f"approval:{t['rule']}")
    assert entry.needed == "The Program Officer's approval through Research.gov"


def test_an_approval_from_the_right_person_through_researchgov_before_the_cost_passes() -> None:
    g = Grant()
    t = g.standard_terms()
    _stipend(g, t)
    _approve(g, t)
    status = g.status("stip", at(2024, 6, 4))
    assert failing(status) == []
    assert status.bucket == Bucket.EVIDENCE_COMPLETE


def test_an_email_approval_from_the_program_officer_stays_in_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms()
    _stipend(g, t)
    _approve(g, t, channel=None, source="gmail")
    status = g.status("stip", at(2024, 6, 4))
    assert problems(status) == {("approval", "email_approval")}
    assert status.bucket == Bucket.NEEDS_HUMAN


def test_an_approval_from_the_wrong_person_or_too_late_is_possible_conflict() -> None:
    g = Grant()
    t = g.standard_terms()
    _stipend(g, t)
    _approve(g, t, email=PI_EMAIL, on=date(2024, 7, 1))
    status = g.status("stip", at(2024, 6, 4))
    assert problems(status) == {("approval", "wrong_approver"), ("approval", "approval_late")}
    assert status.bucket == Bucket.POSSIBLE_CONFLICT


def test_an_approver_nobody_named_on_the_grant_is_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms()
    _stipend(g, t)
    _approve(g, t, email="someone@elsewhere.example")
    assert problems(g.status("stip", at(2024, 6, 4))) == {("approval", "approver_unknown")}


def test_the_rule_applies_when_the_ledger_account_says_so_even_if_the_line_doesnt() -> None:
    """A laptop filed on a stipend account, assigned to Materials and Supplies: a misfiling."""
    g = Grant()
    t = g.standard_terms()
    _stipend(g, t, line="ms")
    status = g.status("stip", at(2024, 6, 2, 13))
    assert ("budget_line", "disagrees") in problems(status)
    assert ("approval", f"missing:approval:{t['rule']}") in problems(status)
    assert status.bucket == Bucket.NEEDS_HUMAN


def test_guest_speaker_ends_in_needs_a_human() -> None:
    """Ruling: a flag, a ledger and budget line disagreement, and a missing NSF approval item."""
    g = Grant()
    t = g.standard_terms(with_rule=False)
    _stipend(g, t, line="other")
    when = at(2024, 6, 3)
    g.item(
        "stip", "NSF approval", when, nsf_standing_list="moving money out of participant support"
    )
    g.answer("stip", "unsure", when, question="flag")
    status = g.status("stip", at(2024, 6, 4))
    assert problems(status) >= {
        ("budget_line", "disagrees"),
        ("approval", "missing:item:nsf_approval"),
    }
    assert any(r.check == "flag" for r in failing(status))
    assert status.bucket == Bucket.NEEDS_HUMAN
    assert status.flagged


def test_a_rule_code_cant_place_is_needs_a_human_on_every_charge() -> None:
    g = Grant()
    t = g.standard_terms(with_rule=False)
    rule = g.approval_rule("Field safety gear", "Grants Officer", None, at(2023, 1, 12, 15))
    g.confirm(rule, when=at(2023, 1, 12, 17))
    g.supplies_charge("c1", date(2024, 5, 1), 10000, at(2024, 5, 1), line=t["ms"])
    assert problems(g.status("c1", at(2024, 5, 2))) == {("approval", f"rule_unmatched:{rule}")}


def test_a_waiting_approval_rule_that_would_apply_is_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms(with_rule=False)
    rule = g.approval_rule(
        "Participant Support Costs", "Program Officer", "Research.gov", at(2024, 6, 1)
    )
    _stipend(g, t)
    assert ("approval", f"rule_not_confirmed:{rule}") in problems(
        g.status("stip", at(2024, 6, 2, 13))
    )


# Every value confirmed (check 5).


def test_a_bill_total_that_couldnt_be_found_is_needs_a_human_until_the_accountant_confirms_it() -> (
    None
):
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2024, 3, 1), 10000)
    f = g.file("f-scan", at(2024, 3, 1))
    b = g.bill(10000, f, at(2024, 3, 1), match="not_found")
    g.link(b, "c1", at(2024, 3, 1), amount=10000, default="bill")
    g.assign("c1", t["ms"], at(2024, 3, 1))
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b])
    status = g.status("c1", at(2024, 3, 2))
    assert problems(status) == {("values_confirmed", "unconfirmed")}
    assert failing(status)[0].text == "The bill: total couldn't be confirmed in its file."
    g.confirm(b, when=at(2024, 3, 3))
    assert g.status("c1", at(2024, 3, 4)).bucket == Bucket.EVIDENCE_COMPLETE


# The bucket order.


def test_the_bucket_is_the_most_serious_among_the_reasons() -> None:
    order = [
        Bucket.POSSIBLE_CONFLICT,
        Bucket.NEEDS_HUMAN,
        Bucket.MISSING_EVIDENCE,
        Bucket.EVIDENCE_COMPLETE,
    ]
    for i, bucket in enumerate(order):
        assert most_serious(order[i:]) == bucket
        assert most_serious(list(reversed(order[i:]))) == bucket


def test_a_charge_with_a_conflict_a_human_question_and_missing_evidence_is_possible_conflict() -> (
    None
):
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2026, 3, 1), 10000)  # after the end date, no bill
    g.assign("c1", t["ms"], at(2026, 3, 1))
    g.answer("c1", "unsure", at(2026, 3, 1), question="flag")
    status = g.status("c1", at(2026, 3, 2))
    assert {r.bucket for r in failing(status)} == {
        Bucket.POSSIBLE_CONFLICT,
        Bucket.NEEDS_HUMAN,
        Bucket.MISSING_EVIDENCE,
    }
    assert status.bucket == Bucket.POSSIBLE_CONFLICT
