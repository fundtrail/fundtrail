"""The one place the checks read the account groups table (account_groups.py, #30).

- A charge's items from its account group come from `account_group_items`,
  which applies decision 0020's sign rule (a line that takes money off the
  grant gets none). The checks don't apply that rule again. The table gives the
  bill-like item the charge's amount, the month-covering item the charge's
  month, and the effort report its due date; the checks then work out the
  bill-like item's amount each time (checklist.py).
- The account's NSF categories, for the comparison with the assigned budget
  line, come from `lookup_account`.
"""

from dataclasses import dataclass
from datetime import date

from app.checks import account_groups
from app.contracts.charges import Charge
from app.contracts.records import BudgetCategory, Period

# The sixth sub-line of Other Direct Costs, "Other".
ODC_OTHER = BudgetCategory.OTHER_DIRECT_COSTS_OTHER


@dataclass(frozen=True)
class GroupItem:
    """One default item from the charge's account group."""

    key: str  # stable, so a link or a removal can name it
    needed: str
    bill_like: bool  # covers whatever the charge's other amount-carrying items don't
    period: Period | None  # the month the linked document has to cover, if any
    expected_by: date | None  # when it's due, if not the posting date


def group_items(charge: Charge) -> list[GroupItem]:
    """The charge's items from its account group (none for a line that takes money off)."""
    return [
        GroupItem(
            key=item.key,
            needed=item.needed,
            # Only the bill-like item carries an amount in the table.
            bill_like=item.amount_cents is not None,
            period=item.period,
            expected_by=item.expected_by,
        )
        for item in account_groups.account_group_items(charge)
    ]


def categories(account: str) -> tuple[BudgetCategory, ...]:
    """The ledger account's NSF categories; none when it's in no group."""
    found = account_groups.lookup_account(account)
    return tuple(found.nsf_categories) if found is not None else ()


# How NSF prints each category, for naming one in text and for matching an
# approval rule's applies_to when no budget line on the grant has that name.
CATEGORY_NAMES: dict[BudgetCategory, tuple[str, ...]] = {
    BudgetCategory.SENIOR_PERSONNEL: ("Senior Personnel",),
    BudgetCategory.OTHER_PERSONNEL: ("Other Personnel",),
    BudgetCategory.FRINGE_BENEFITS: ("Fringe Benefits",),
    BudgetCategory.EQUIPMENT: ("Equipment",),
    BudgetCategory.TRAVEL: ("Travel",),
    BudgetCategory.PARTICIPANT_SUPPORT: ("Participant Support Costs", "Participant Support"),
    BudgetCategory.OTHER_DIRECT_COSTS: ("Other Direct Costs",),
    BudgetCategory.MATERIALS_AND_SUPPLIES: ("Materials and Supplies",),
    BudgetCategory.PUBLICATION: ("Publication Costs",),
    BudgetCategory.CONSULTANT_SERVICES: ("Consultant Services",),
    BudgetCategory.COMPUTER_SERVICES: ("Computer Services",),
    BudgetCategory.SUBAWARDS: ("Subawards",),
    ODC_OTHER: ("Other",),
}


def category_name(category: BudgetCategory) -> str:
    return CATEGORY_NAMES[category][0]


def account_code(account: str) -> str | None:
    """The 5-digit account code at the start of a ledger account, or None."""
    return account_groups.account_code(account)
