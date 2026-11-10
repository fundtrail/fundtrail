"""The one place the checks read the account groups table (account_groups.py, issue #20).

The table names NSF budget lines by name, with a parent for a sub-line. The
contracts compare categories as records.BudgetCategory with CATEGORY_PARENT and
categories_match(). This module translates the table into those types, so when
the table moves to the contract's category type only this file changes.

It also gives each default item a key, the stable name a link or a removal uses.
A default's key is its table ID without the group prefix ("supplies.bill" is
"bill"), which is what the sample grant's links use. Keys are unique within one
charge, because a charge's defaults come from one group.
"""

from dataclasses import dataclass

from app.checks import account_groups
from app.contracts.records import BudgetCategory

# The sixth sub-line of Other Direct Costs, "Other".
ODC_OTHER = BudgetCategory.OTHER_DIRECT_COSTS_OTHER

_CATEGORY_BY_LINE: dict[tuple[str, str | None], BudgetCategory] = {
    ("Senior Personnel", None): BudgetCategory.SENIOR_PERSONNEL,
    ("Other Personnel", None): BudgetCategory.OTHER_PERSONNEL,
    ("Fringe Benefits", None): BudgetCategory.FRINGE_BENEFITS,
    ("Equipment", None): BudgetCategory.EQUIPMENT,
    ("Travel", None): BudgetCategory.TRAVEL,
    ("Participant Support Costs", None): BudgetCategory.PARTICIPANT_SUPPORT,
    ("Other Direct Costs", None): BudgetCategory.OTHER_DIRECT_COSTS,
    ("Materials and Supplies", "Other Direct Costs"): BudgetCategory.MATERIALS_AND_SUPPLIES,
    ("Publication Costs", "Other Direct Costs"): BudgetCategory.PUBLICATION,
    ("Consultant Services", "Other Direct Costs"): BudgetCategory.CONSULTANT_SERVICES,
    ("Computer Services", "Other Direct Costs"): BudgetCategory.COMPUTER_SERVICES,
    ("Subawards", "Other Direct Costs"): BudgetCategory.SUBAWARDS,
    ("Other", "Other Direct Costs"): ODC_OTHER,
}


def _category(line: account_groups.NsfLine) -> BudgetCategory:
    try:
        return _CATEGORY_BY_LINE[(line.name, line.parent)]
    except KeyError:
        raise ValueError(f"the account groups table names an unknown NSF line: {line}") from None


@dataclass(frozen=True)
class GroupItem:
    """One default item from the charge's account group."""

    key: str
    needed: str
    bill_like: bool  # covers whatever the charge's other amount-carrying items don't
    covers_month: bool  # the linked document has to cover the charge's month


@dataclass(frozen=True)
class AccountView:
    group_id: str
    group_name: str
    categories: tuple[BudgetCategory, ...]
    items: tuple[GroupItem, ...]


def lookup(account: str) -> AccountView | None:
    """What the table says about a ledger account, or None when it's in no group."""
    found = account_groups.lookup_account(account)
    if found is None:
        return None
    return AccountView(
        group_id=found.group.id,
        group_name=found.group.name,
        categories=tuple(_category(line) for line in found.nsf_categories),
        items=tuple(
            GroupItem(
                key=item.id.split(".", 1)[-1],
                needed=item.text,
                bill_like=item.carries_charge_amount,
                covers_month=item.covers_charge_month,
            )
            for item in found.default_items
        ),
    )


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
