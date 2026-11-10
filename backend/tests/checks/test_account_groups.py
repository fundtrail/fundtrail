import pytest

from app.checks.account_groups import (
    ACCOUNT_GROUPS,
    EQUIPMENT,
    FRINGE_BENEFITS,
    MATERIALS_AND_SUPPLIES,
    NOT_IN_ANY_GROUP,
    OTHER_DIRECT_COSTS,
    OTHER_DIRECT_COSTS_OTHER,
    OTHER_DIRECT_COSTS_SUB_LINES,
    OTHER_PERSONNEL,
    PARTICIPANT_SUPPORT_COSTS,
    SENIOR_PERSONNEL,
    SUBAWARDS,
    TRAVEL,
    NsfLine,
    account_code,
    lookup_account,
)


def group_id(account: str) -> str | None:
    found = lookup_account(account)
    return found.group.id if found else None


def categories(account: str) -> tuple[NsfLine, ...]:
    found = lookup_account(account)
    assert found is not None, account
    return found.nsf_categories


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


def test_sample_grant_supplies_line() -> None:
    # L-1001 in contracts.md section 15, assigned to Materials and Supplies.
    found = lookup_account("55016 Lab Instruments and Supplies")
    assert found is not None
    assert found.group.name == "Supplies"
    assert found.account_code == "55016"
    assert found.nsf_categories == (MATERIALS_AND_SUPPLIES,)
    assert [item.text for item in found.default_items] == ["A bill that adds up to the charge"]
    assert found.default_items[0].carries_charge_amount


def test_sample_grant_recharge_line() -> None:
    # L-1002 in contracts.md section 15, assigned to Other, a sub-line of Other
    # Direct Costs, which the recharge category contains.
    found = lookup_account("59009 Recharge-Other Expenses")
    assert found is not None
    assert found.nsf_categories == (OTHER_DIRECT_COSTS,)
    assert OTHER_DIRECT_COSTS_OTHER.parent == OTHER_DIRECT_COSTS.name
    assert [item.text for item in found.default_items] == ["The facility's usage statement"]
    assert found.default_items[0].carries_charge_amount


@pytest.mark.parametrize(
    ("account", "expected"),
    [
        ("59005", EQUIPMENT),
        ("59006", MATERIALS_AND_SUPPLIES),
        ("59007", PARTICIPANT_SUPPORT_COSTS),
        ("59008", TRAVEL),
        ("59012", EQUIPMENT),
        ("59013", EQUIPMENT),
    ],
)
def test_recharge_that_names_what_was_bought(account: str, expected: NsfLine) -> None:
    found = lookup_account(account)
    assert found is not None
    assert found.group.id == "recharges"
    assert found.nsf_categories == (expected,)
    assert [item.id for item in found.default_items] == ["recharges.usage_statement"]


def test_participant_stipends_are_participant_support() -> None:
    # domain.md's misfiled laptop example: 56712 is not Materials and Supplies.
    found = lookup_account("56712 Participant Support-Stipends")
    assert found is not None
    assert found.nsf_categories == (PARTICIPANT_SUPPORT_COSTS,)
    assert [item.text for item in found.default_items] == ["Participant list", "Payment record"]
    assert [item.carries_charge_amount for item in found.default_items] == [False, True]


def test_salaries() -> None:
    found = lookup_account("50200")
    assert found is not None
    assert found.nsf_categories == (SENIOR_PERSONNEL, OTHER_PERSONNEL)
    texts = [item.text for item in found.default_items]
    assert texts == ["Appointment letter", "Certified effort report covering the month"]
    assert found.default_items[1].covers_charge_month


def test_group_categories() -> None:
    assert categories("53100") == (FRINGE_BENEFITS,)
    assert categories("53800") == (FRINGE_BENEFITS, OTHER_DIRECT_COSTS_OTHER)
    assert categories("57211") == (TRAVEL,)
    assert categories("54210") == (EQUIPMENT,)
    assert categories("57810") == (SUBAWARDS,)
    assert categories("56720") == (OTHER_DIRECT_COSTS,)
    assert categories("56410") == (OTHER_DIRECT_COSTS,)


def test_subaward_partner_invoice_carries_the_amount() -> None:
    found = lookup_account("57811")
    assert found is not None
    carrying = [item.id for item in found.default_items if item.carries_charge_amount]
    assert carrying == ["subawards.partner_invoice"]


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
    ids = [item.id for group in ACCOUNT_GROUPS for item in group.default_items]
    assert len(ids) == len(set(ids))
    for group in ACCOUNT_GROUPS:
        assert group.default_items, group.id
        assert group.nsf_categories, group.id
        amount_items = [item for item in group.default_items if item.carries_charge_amount]
        assert len(amount_items) <= 1, group.id


def test_sub_lines_name_a_parent_from_nsfs_list() -> None:
    every_line = {
        line
        for group in ACCOUNT_GROUPS
        for line in group.nsf_categories
        + tuple(c for cats in group.categories_by_account.values() for c in cats)
    }
    for line in every_line:
        if line.parent is not None:
            assert line.parent == OTHER_DIRECT_COSTS.name
            assert line in OTHER_DIRECT_COSTS_SUB_LINES
    assert len(OTHER_DIRECT_COSTS_SUB_LINES) == 6
