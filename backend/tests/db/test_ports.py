"""The real seams to the other areas, so a name or a shape that doesn't match fails here, not
as a 500."""

from datetime import UTC, datetime

from app.contracts.checks import Bucket, ChecksInput
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import BudgetCategory
from app.db.ports import ModuleChecks


def test_account_categories_come_from_the_account_groups_table() -> None:
    checks = ModuleChecks()
    assert BudgetCategory.MATERIALS_AND_SUPPLIES in checks.account_categories(
        "55016 Lab Instruments and Supplies"
    )
    assert tuple(checks.account_categories("99999 Nothing like it")) == ()


def test_the_real_checks_give_the_sample_grant_its_buckets() -> None:
    """contracts.md section 15: after the extension is confirmed, both lines are complete."""
    sample = load_sample_grant()
    now = datetime(2026, 4, 10, 17, tzinfo=UTC)
    output = ModuleChecks().run_checks(
        ChecksInput(
            now=now,
            charges=tuple(c for c in sample.charges if c.arrived_at <= now),
            files=tuple(f for f in sample.files if f.arrived_at <= now),
            records=tuple(r for r in sample.records if r.written_at <= now),
        )
    )
    lines = {c.id: c.ledger_line_id for c in sample.charges}
    buckets = {lines[s.charge_id]: s.bucket for s in output.charges}
    assert buckets == {"L-1001": Bucket.EVIDENCE_COMPLETE, "L-1002": Bucket.EVIDENCE_COMPLETE}


def test_the_real_default_items_take_a_charge_and_its_records() -> None:
    sample = load_sample_grant()
    l1001 = next(c for c in sample.charges if c.ledger_line_id == "L-1001")
    items = ModuleChecks().default_items(l1001, sample.records)
    assert items and all(i.key for i in items)
