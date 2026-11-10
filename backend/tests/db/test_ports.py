"""The real seams to the other areas, so a name that doesn't match fails here, not as a 500."""

import pytest

from app.contracts.records import BudgetCategory
from app.db.ports import ModuleChecks


def test_account_categories_come_from_the_account_groups_table() -> None:
    checks = ModuleChecks()
    assert BudgetCategory.MATERIALS_AND_SUPPLIES in checks.account_categories(
        "55016 Lab Instruments and Supplies"
    )
    assert tuple(checks.account_categories("99999 Nothing like it")) == ()


def test_a_missing_seam_says_which_issue_delivers_it() -> None:
    from app import checks

    if hasattr(checks, "run_checks"):
        pytest.skip("#24's run_checks is on main")
    with pytest.raises(NotImplementedError, match="#24"):
        ModuleChecks().default_items(None, [])  # pyright: ignore[reportArgumentType]
