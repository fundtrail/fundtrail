from datetime import UTC, date, datetime

import pytest

from app.checks.account_groups import (
    ACCOUNT_GROUPS,
    NOT_IN_ANY_GROUP,
    account_code,
    account_group_items,
    lookup_account,
)
from app.contracts.charges import Charge
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import BudgetCategory, Period, categories_match
from app.contracts.rules import check_new_record

B = BudgetCategory


def group_id(account: str) -> str | None:
    found = lookup_account(account)
    return found.group.id if found else None


def categories(account: str) -> tuple[BudgetCategory, ...]:
    found = lookup_account(account)
    assert found is not None, account
    return found.nsf_categories


def charge(account: str, amount_cents: int = 50000, day: date = date(2026, 2, 17)) -> Charge:
    return Charge(
        id="c1",
        workspace_id="w",
        grant_id="g",
        ledger_line_id="L-1",
        transaction_date=day,
        posting_date=day,
        arrived_at=datetime(day.year, day.month, day.day, tzinfo=UTC),
        amount_cents=amount_cents,
        description="Synthetic charge",
        account=account,
    )


# Real account codes from Berkeley's chart of accounts tree report (2026-08-01).
@pytest.mark.parametrize(
    ("account", "expected"),
    [
        ("50200", "salaries"),  # Academic Salaries & Wages
        ("51200", "salaries"),  # Staff Salaries & Wages
        ("53100", "benefits"),  # OASDI
        ("53700", "benefits"),  # Employer UCRP Contribution-UC
        ("53800", "tuition"),  # Graduate Full Fee Remission
        ("53803", "tuition"),  # U/G Partial Fee Remission
        ("57423", "tuition"),  # Grad Fellowships-Tuition/Fees
        ("57211", "travel"),  # In-State Travel - Air Fare
        ("57221", "travel"),  # Foreign Travel - Air Fare
        ("55016", "supplies"),  # Lab Instruments and Supplies
        ("55101", "supplies"),  # Computer Supplies
        ("55221", "supplies"),  # Computer Equip <$5K per Item
        ("55319", "supplies"),  # Equipment<$5K per Item
        ("54110", "equipment"),  # Equip Computer =>$5K per Item
        ("54210", "equipment"),  # Cap Equipment=>$5k per Item
        ("56711", "participant_support"),  # Participant Support-Other
        ("56712", "participant_support"),  # Participant Support-Stipends
        ("56715", "participant_support"),  # Participant Sppt-TravelAirfare
        ("57810", "subawards"),  # Cum Exp>$25k per Subaward
        ("57820", "subawards"),  # C&G Intercampus Expenditures range
        ("57899", "subawards"),
        ("92502", "subawards"),  # C&G Subaward expense - UCSF
        ("56720", "consultants"),  # Consultant Fees
        ("56726", "consultants"),  # Honoraria
        ("56410", "printing"),  # Printing
        ("59001", "recharges"),  # Recharge-IT/Phone/Data Svcs
        ("59009", "recharges"),  # Recharge-Other Expenses
    ],
)
def test_berkeley_accounts_land_in_their_group(account: str, expected: str) -> None:
    assert group_id(account) == expected


@pytest.mark.parametrize(
    "account",
    [
        "52010",  # Vacation Accrual
        "56110",  # Mailing Services/Postage
        "56710",  # Payments to Patients or Human [Subjects]
        "57232",  # Moving Costs
        "57413",  # Grad Fellowships-Stipends
        "59000",  # Internal Recharge Income
        "10000",  # an asset account, not an expense
    ],
)
def test_account_in_no_group(account: str) -> None:
    assert lookup_account(account) is None
    assert account_group_items(charge(account)) == []


def test_fee_remission_is_tuition_not_benefits() -> None:
    # 538xx sits inside 53xxx. The more specific range wins.
    assert group_id("53801 Graduate Partial Fee Remission") == "tuition"
    assert group_id("53799") == "benefits"
    assert group_id("53900") == "benefits"


def test_excluded_accounts_beat_their_range() -> None:
    assert group_id("56711") == "participant_support"
    assert lookup_account("56710") is None
    assert group_id("59001") == "recharges"
    assert lookup_account("59000") is None


def test_ledger_account_with_its_name() -> None:
    assert group_id("55016 Lab Instruments and Supplies") == "supplies"
    assert group_id("  59009 Recharge-Other Expenses") == "recharges"


@pytest.mark.parametrize("account", ["", "Lab supplies", "5501", "550160", "5501x", "x55016"])
def test_account_without_a_five_digit_code(account: str) -> None:
    assert account_code(account) is None
    assert lookup_account(account) is None


def test_sample_grant_defaults_match_the_fixture() -> None:
    # contracts.md section 15: L-1001 on 55016, L-1002 on 59009.
    sample = load_sample_grant()
    for c in sample.charges:
        assert account_group_items(c) == list(sample.default_items[c.ledger_line_id])


def test_sample_grant_passes_the_write_check_with_these_defaults() -> None:
    sample = load_sample_grant()
    written = []
    for r in sample.records:
        charges = [c for c in sample.charges if c.arrived_at <= r.written_at]
        files = [f for f in sample.files if f.arrived_at <= r.written_at]
        assert (
            check_new_record(
                r, written, charges, files, default_items=lambda c, _records: account_group_items(c)
            )
            == []
        ), r.id
        written.append(r)


def test_sample_grant_categories_agree_with_the_assigned_lines() -> None:
    # L-1001 is assigned Materials and Supplies, L-1002 Other in Other Direct Costs.
    assert any(categories_match(c, B.MATERIALS_AND_SUPPLIES) for c in categories("55016"))
    assert any(categories_match(c, B.OTHER_DIRECT_COSTS_OTHER) for c in categories("59009"))


def test_misfiled_laptop_on_stipends_disagrees() -> None:
    # domain.md: a laptop on 56712, assigned Materials and Supplies, is a likely misfiling.
    assert categories("56712") == (B.PARTICIPANT_SUPPORT,)
    assert not any(categories_match(c, B.MATERIALS_AND_SUPPLIES) for c in categories("56712"))


@pytest.mark.parametrize(
    ("account", "expected"),
    [
        ("59005", B.MATERIALS_AND_SUPPLIES),  # fabricated equipment under $5,000
        ("59006", B.MATERIALS_AND_SUPPLIES),
        ("59007", B.PARTICIPANT_SUPPORT),
        ("59008", B.TRAVEL),
        ("59012", B.EQUIPMENT),
        ("59013", B.EQUIPMENT),
    ],
)
def test_recharge_that_names_what_was_bought(account: str, expected: BudgetCategory) -> None:
    found = lookup_account(account)
    assert found is not None
    assert found.group.id == "recharges"
    assert found.nsf_categories == (expected,)
    assert [item.key for item in found.items] == ["usage_statement"]


@pytest.mark.parametrize("account", ["59001", "59002", "59003", "59004", "59009", "59011"])
def test_other_recharges_stay_at_other_direct_costs(account: str) -> None:
    assert categories(account) == (B.OTHER_DIRECT_COSTS,)


def test_group_categories() -> None:
    assert categories("50200") == (B.SENIOR_PERSONNEL, B.OTHER_PERSONNEL)
    assert categories("53100") == (B.FRINGE_BENEFITS,)
    assert categories("53800") == (B.FRINGE_BENEFITS, B.OTHER_DIRECT_COSTS_OTHER)
    assert categories("57211") == (B.TRAVEL,)
    assert categories("54210") == (B.EQUIPMENT,)
    assert categories("57810") == (B.SUBAWARDS,)
    assert categories("56720") == (B.OTHER_DIRECT_COSTS,)
    assert categories("56410") == (B.OTHER_DIRECT_COSTS,)


def test_salary_items_name_the_charge_month() -> None:
    items = account_group_items(charge("50200", day=date(2024, 2, 10)))
    assert [i.key for i in items] == ["appointment_letter", "effort_report"]
    assert items[0].period is None
    assert items[1].period == Period(start=date(2024, 2, 1), end=date(2024, 2, 29))
    assert all(i.amount_cents is None for i in items)


def test_amount_goes_on_the_bill_like_item_only() -> None:
    items = account_group_items(charge("56712", amount_cents=50000))
    assert [(i.key, i.amount_cents) for i in items] == [
        ("participant_list", None),
        ("payment_record", 50000),
    ]
    items = account_group_items(charge("57811", amount_cents=900000))
    assert [(i.key, i.amount_cents) for i in items] == [
        ("partner_invoice", 900000),
        ("professor_approval", None),
        ("subaward_agreement", None),
    ]


def test_line_taking_money_off_gets_no_group_items() -> None:
    # Decision 0020: such a line gets only the two correction items.
    assert account_group_items(charge("55016", amount_cents=-1240)) == []


def test_line_adding_money_keeps_its_group_items() -> None:
    moved_on = charge("55016", amount_cents=1240).model_copy(update={"original_line_id": "L-9"})
    assert [i.key for i in account_group_items(moved_on)] == ["bill"]


def test_reversals_are_not_a_group() -> None:
    names = " ".join(group.name.lower() for group in ACCOUNT_GROUPS)
    assert "reversal" not in names
    assert "transfer" not in names


def test_entries_are_codes_or_prefixes_and_never_repeat() -> None:
    seen: set[str] = set(NOT_IN_ANY_GROUP)
    assert len(seen) == len(NOT_IN_ANY_GROUP)
    for group in ACCOUNT_GROUPS:
        for entry in group.accounts:
            assert entry.isdigit() and 1 <= len(entry) <= 5
            assert entry not in seen
            seen.add(entry)
        for code in group.categories_by_account:
            assert len(code) == 5
            assert group_id(code) == group.id


def test_every_group_has_items_and_categories() -> None:
    for group in ACCOUNT_GROUPS:
        keys = [item.key for item in group.items]
        assert keys and len(keys) == len(set(keys)), group.id
        assert group.nsf_categories, group.id
        assert sum(item.carries_charge_amount for item in group.items) <= 1, group.id
