"""Behavior pinned on purpose, and an approval rule's scope (39-rulings.md item 8).

The pins keep two edge cases as they are (main coordinator's ruling), so a
later change to them has to be deliberate. Both are open questions for Alex.
"""

from datetime import date
from decimal import Decimal

from app.contracts.checks import Bucket

from .grant_builder import TRAVEL, Grant, at, cited, failing
from .test_charge_checks import _stipend  # pyright: ignore[reportPrivateUsage]

# Known behavior.


def test_a_zero_dollar_charge_reaches_evidence_complete_with_no_evidence() -> None:
    """A $0 line puts no money on the grant: its bill item needs $0, so it's filled."""
    g = Grant()
    t = g.standard_terms()
    g.charge("zero", date(2024, 3, 1), 0)
    g.assign("zero", t["ms"], at(2024, 3, 1))
    out = g.run(at(2024, 3, 2))
    status = out.charges[0]
    assert status.bucket == Bucket.EVIDENCE_COMPLETE
    assert [(e.default_item, e.amount_cents, e.filled) for e in status.checklist] == [
        ("bill", 0, True)
    ]
    assert out.questions == ()  # nothing linked, so Allowable isn't asked


def test_a_charge_filled_only_by_rate_math_reaches_evidence_complete_with_no_answer() -> None:
    """Only after the accountant removes the expense report item: no link, so no Allowable."""
    g = Grant()
    g.standard_terms()
    when = at(2024, 4, 2)
    g.charge("diem", date(2024, 4, 1), 50000, account=TRAVEL)
    g.assign("diem", g.confirmed_line("Travel", "travel", when), when)
    f = g.file("f-diem", when)
    g.item(
        "diem",
        "Per diem, 5 days at $100 a day",
        when,
        amount_cents=50000,
        rate={
            "quantity": cited(Decimal("5"), "5 days", f),
            "rate": cited(Decimal("10000"), "$100 a day", f),
        },
    )
    g.user(
        {"kind": "checklist_removal", "charge_id": "diem", "default_item": "expense_report"}, when
    )
    out = g.run(at(2024, 4, 3))
    status = out.charges[0]
    assert status.bucket == Bucket.EVIDENCE_COMPLETE
    assert out.questions == ()


# Approval rule scope.


def _rule(g: Grant, applies_to: str, approver: str, scope: str) -> str:
    rule = g.approval_rule(applies_to, approver, "Research.gov", at(2023, 1, 12, 15), scope=scope)
    g.confirm(rule, when=at(2023, 1, 12, 17))
    return rule


def test_moved_out_doesnt_cover_an_ordinary_stipend() -> None:
    g = Grant()
    t = g.standard_terms(with_rule=False)
    _rule(g, "Participant Support Costs", "Program Officer", "moved_out")
    _stipend(g, t)
    status = g.status("stip", at(2024, 6, 2, 13))
    assert not any(
        e.default_item and e.default_item.startswith("approval:") for e in status.checklist
    )
    assert failing(status) == []


def test_moved_out_covers_a_laptop_on_a_participant_support_account() -> None:
    g = Grant()
    t = g.standard_terms(with_rule=False)
    rule = _rule(g, "Participant Support Costs", "Program Officer", "moved_out")
    _stipend(g, t, line="ms")
    status = g.status("stip", at(2024, 6, 2, 13))
    assert f"approval:{rule}" in [e.default_item for e in status.checklist]


def test_every_charge_covers_equipment_on_its_line() -> None:
    g = Grant()
    g.standard_terms(with_rule=False)
    rule = _rule(g, "Equipment", "Grants Officer", "every_charge")
    when = at(2024, 6, 2)
    g.charge("eq", date(2024, 6, 1), 1_200_000, account="54210 Cap Equipment=>$5k per Item")
    g.assign("eq", g.confirmed_line("Equipment", "equipment", when), when)
    status = g.status("eq", at(2024, 6, 2, 13))
    assert f"approval:{rule}" in [e.default_item for e in status.checklist]
