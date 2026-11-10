"""The sample grant gives the buckets contracts.md section 15 expects, at the times it lists."""

from datetime import UTC, datetime

import pytest

from app.checks.checklist import default_items
from app.checks.run import run_checks
from app.contracts.checks import Bucket, ChecksInput, ChecksOutput
from app.contracts.fixtures import load_sample_grant
from app.contracts.rules import check_new_record

NOV_14 = datetime(2025, 11, 14, 12, tzinfo=UTC)
FEB_24 = datetime(2026, 2, 24, 12, tzinfo=UTC)
APR_9 = datetime(2026, 4, 9, 17, tzinfo=UTC)  # the extension has arrived, not yet confirmed
APR_10 = datetime(2026, 4, 10, 17, tzinfo=UTC)


def run_at(now: datetime) -> ChecksOutput:
    s = load_sample_grant()
    return run_checks(
        ChecksInput(
            now=now,
            charges=[c for c in s.charges if c.arrived_at <= now],
            files=[f for f in s.files if f.arrived_at <= now],
            records=[r for r in s.records if r.written_at <= now],
        )
    )


def buckets(out: ChecksOutput) -> dict[str, Bucket]:
    return {c.charge_id: c.bucket for c in out.charges}


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (NOV_14, {"chg-l-1001": Bucket.EVIDENCE_COMPLETE}),
        (FEB_24, {"chg-l-1001": Bucket.EVIDENCE_COMPLETE, "chg-l-1002": Bucket.POSSIBLE_CONFLICT}),
        (APR_9, {"chg-l-1001": Bucket.EVIDENCE_COMPLETE, "chg-l-1002": Bucket.POSSIBLE_CONFLICT}),
        (APR_10, {"chg-l-1001": Bucket.EVIDENCE_COMPLETE, "chg-l-1002": Bucket.EVIDENCE_COMPLETE}),
    ],
)
def test_expected_buckets(now: datetime, expected: dict[str, Bucket]) -> None:
    assert buckets(run_at(now)) == expected


def test_l1002_rests_on_the_award_letter_then_on_the_extension() -> None:
    before = next(c for c in run_at(FEB_24).charges if c.charge_id == "chg-l-1002")
    date = next(r for r in before.reasons if r.check == "period_of_performance")
    assert (date.problem, date.bucket) == ("after_end_date", Bucket.POSSIBLE_CONFLICT)
    assert date.record_ids == ["rec-period"]
    assert date.text == "Dated Feb 20, 2026, after the grant's end date, Jan 31, 2026."
    assert before.flagged

    after = next(c for c in run_at(APR_10).charges if c.charge_id == "chg-l-1002")
    date = next(r for r in after.reasons if r.check == "period_of_performance")
    assert date.bucket == Bucket.EVIDENCE_COMPLETE
    assert "rec-period-extension" in date.record_ids
    assert not after.flagged
    assert not after.rechecking  # no agent call: the Allowable answer didn't rest on the end date


def test_the_only_failing_check_on_l1002_is_the_date() -> None:
    status = next(c for c in run_at(FEB_24).charges if c.charge_id == "chg-l-1002")
    assert [r.check for r in status.reasons if r.bucket != Bucket.EVIDENCE_COMPLETE] == ["period_of_performance"]
    checks = {r.check for r in status.reasons}
    assert {"checklist", "approval", "values_confirmed", "budget_line", "allowable"} <= checks


def test_checklists_have_their_one_default_item_filled() -> None:
    out = run_at(APR_10)
    by_charge = {c.charge_id: c.checklist for c in out.charges}
    assert [(e.default_item, e.amount_cents, e.filled) for e in by_charge["chg-l-1001"]] == [("bill", 124000, True)]
    assert [(e.default_item, e.amount_cents, e.filled) for e in by_charge["chg-l-1002"]] == [
        ("usage_statement", 218000, True)
    ]


@pytest.mark.parametrize("now", [NOV_14, FEB_24, APR_9, APR_10])
def test_the_grant_has_no_problem_of_its_own(now: datetime) -> None:
    out = run_at(now)
    assert out.grants == []
    assert out.notes == []
    assert out.questions == []


def test_the_waiting_extension_is_a_problem_on_its_record_until_confirmed() -> None:
    assert [(r.record_id, r.problems[0].problem) for r in run_at(APR_9).records] == [
        ("rec-period-extension", "waiting")
    ]
    assert run_at(APR_10).records == []


def test_default_items_satisfy_the_write_check_for_every_sample_record() -> None:
    s = load_sample_grant()
    for i, record in enumerate(s.records):
        visible = [f for f in s.files if f.arrived_at <= record.written_at]
        charges = [c for c in s.charges if c.arrived_at <= record.written_at]
        assert check_new_record(record, s.records[:i], charges, visible, default_items=default_items) == []


def test_default_items_match_the_samples_stand_in() -> None:
    s = load_sample_grant()
    for charge in s.charges:
        assert default_items(charge, s.records) == s.default_items[charge.ledger_line_id]
