"""Benefit charges (rulings 61 and 62): a benefit rate's group and dates, an item code
fills by recalculating, the expected amount on a mismatch, and benefit charges that
wait on their salary line."""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts import api
from app.contracts.buckets import Bucket
from app.contracts.checks import ChargeStatus, ChecklistEntry, ItemSource, Problem
from app.contracts.records import BenefitGroup, Rate, Record
from tests.contracts.factory import CHARGE, agent, cited, problems

PASSAGE = "Staff 41.2% effective July 1, 2025 through June 30, 2026"


def benefit_rate(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "kind": "rate",
        "dated": cited("2025-06-01", "June 1, 2025", file_id="f3"),
        "name": cited("Staff", "Staff", PASSAGE, "f3"),
        "rate": cited(Decimal("0.412"), "41.2%", PASSAGE, "f3"),
        "applies_to": cited("staff", "Staff", PASSAGE, "f3"),
        "effective_from": cited("2025-07-01", "July 1, 2025", PASSAGE, "f3"),
        "effective_to": cited("2026-06-30", "June 30, 2026", PASSAGE, "f3"),
    }
    return data | changes


def test_a_benefit_rate_names_its_group_and_when_its_in_effect():
    r = agent("r1", benefit_rate())
    assert isinstance(r.data, Rate) and r.data.applies_to is not None
    assert r.data.applies_to.value == BenefitGroup.STAFF
    assert Record.model_validate_json(r.model_dump_json()) == r
    assert problems(r, []) == []  # each value's text is in its passage


def test_todays_rate_terms_stay_valid_and_a_benefit_rate_may_run_until_amended():
    plain = {k: v for k, v in benefit_rate().items() if k in {"kind", "dated", "name", "rate"}}
    r = agent("r1", plain)
    assert isinstance(r.data, Rate)
    assert (r.data.applies_to, r.data.effective_from, r.data.effective_to) == (None, None, None)
    open_ended = agent("r2", {k: v for k, v in benefit_rate().items() if k != "effective_to"})
    assert isinstance(open_ended.data, Rate) and open_ended.data.effective_to is None


def test_a_benefit_rate_refuses_an_unknown_group_and_an_end_before_its_start():
    with pytest.raises(ValidationError):
        agent("r1", benefit_rate(applies_to=cited("faculty", "Faculty", PASSAGE, "f3")))
    with pytest.raises(ValidationError):
        agent("r1", benefit_rate(effective_to=cited("2025-06-30", "June 30, 2026", PASSAGE, "f3")))


def entry(**changes: Any) -> ChecklistEntry:
    fields: dict[str, Any] = {
        "default_item": "benefit_rate",
        "added_by": ItemSource.DEFAULT,
        "needed": "The benefit rate times the salary lines",
        "filled": True,
        "rate_id": "r1",
        "charge_ids": ("c-salary",),
    }
    return ChecklistEntry.model_validate(fields | changes)


def test_an_item_code_recalculates_names_what_it_used_and_has_no_links():
    filled = entry()
    assert filled.rate_id == "r1" and filled.charge_ids == ("c-salary",)
    assert ChecklistEntry.model_validate_json(filled.model_dump_json()) == filled
    entry(filled=False, charge_ids=())  # not filled yet: the salary lines aren't in
    with pytest.raises(ValidationError):  # filled by recalculation, never by links
        entry(link_ids=("l1",))
    with pytest.raises(ValidationError):  # a filled one names its salary lines
        entry(charge_ids=())
    with pytest.raises(ValidationError):  # and its rate term
        entry(rate_id=None)
    plain = entry(rate_id=None, charge_ids=(), link_ids=("l1",))  # an ordinary item
    assert plain.rate_id is None and plain.charge_ids == ()


def test_a_recalculation_that_doesnt_match_carries_the_expected_amount():
    p = Problem(
        check="checklist",
        problem="benefit_rate",
        text="The benefit is $412.00 short of 41.2% of salary lines L-2001 and L-2002.",
        record_ids=("r1",),
        expected_cents=82400,
    )
    assert Problem.model_validate_json(p.model_dump_json()).expected_cents == 82400
    assert Problem(check="c", problem="p", text="t").expected_cents is None


def test_benefit_charges_waiting_on_a_salary_line_show_with_its_row():
    status = ChargeStatus(
        grant_id="g",
        charge_id=CHARGE.id,
        bucket=Bucket.MISSING_EVIDENCE,
        reasons=(),
        checklist=(),
        flagged=True,
    )
    row = api.ChargeProblemRow(charge=CHARGE, status=status, waiting_charge_ids=("c-benefit",))
    back = api.ChargeProblemRow.model_validate_json(row.model_dump_json())
    assert back.waiting_charge_ids == ("c-benefit",)
    assert api.ChargeProblemRow(charge=CHARGE, status=status).waiting_charge_ids == ()
