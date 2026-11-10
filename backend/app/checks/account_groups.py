"""Account groups: which ledger accounts share a default evidence checklist.

A default checklist hangs on a group of ledger accounts, not on each account
(decision 0016). This module is the small table that says which Berkeley account
codes belong to which group, and gives each group its default checklist items and
its National Science Foundation (NSF) budget categories. The starting table is in
docs/domain.md, "Default checklists by account group". The changes from it, and
every category, are the main coordinator's provisional answers on issue #20.

Each row was checked against Berkeley's public account list, the BFS (Berkeley
Financial System) General Ledger Chart of Accounts Tree Report, run on 2026-08-01:
https://controller.berkeley.edu/sites/default/files/bfs_coa_tree_report.pdf

Rules the table follows:

- A Berkeley account is a 5-digit code. A table entry is an account code prefix,
  so "538" covers 53800 to 53899, or a whole code, such as "59006". Where two
  entries overlap, the longer one, the more specific, wins: 538xx is tuition and
  fee remission, not benefits.
- An account in no group gets no default items and no NSF category.
- A group can carry more than one NSF category. The ledger's account and the
  budget line the agent assigned agree when that line's category matches one of
  them (`categories_match` in the contracts). Comparing them is the checks' job.
- Reversals and cost transfers are not a group, and their two correction items
  (the line it corrects, a written justification) aren't in this table. Under
  decision 0020 (provisional), a line that takes money off the grant gets only
  those two items, so `account_group_items` gives it none. A line
  that adds money gets its account group's default plus the two. Either way,
  its NSF category comes from its account.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field

from app.contracts.charges import Charge
from app.contracts.records import BudgetCategory, DefaultItem, Period


@dataclass(frozen=True)
class GroupItem:
    """One of a group's default checklist items, as domain.md words it.

    The table's own form of an item. `account_group_items` turns it into the
    contract's `DefaultItem` for one charge. `key` is stable, so a link or a
    removal can name the item. `carries_charge_amount` marks the item that
    stands for the bill-like document: it carries the charge's amount, and
    covers whatever the charge's other amount-carrying items don't (the checks
    work that out). `covers_charge_month` means the document has to cover the
    month of the charge.
    """

    key: str
    needed: str
    carries_charge_amount: bool = False
    covers_charge_month: bool = False


@dataclass(frozen=True)
class AccountGroup:
    """A group of accounts with one default checklist.

    `accounts` are code prefixes or whole codes. `nsf_categories` holds for every
    account in the group, except an account named in `categories_by_account`,
    which carries its own.
    """

    id: str
    name: str
    accounts: tuple[str, ...]
    items: tuple[GroupItem, ...]
    nsf_categories: tuple[BudgetCategory, ...]
    categories_by_account: dict[str, tuple[BudgetCategory, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountDefaults:
    """What the table gives one ledger account."""

    account_code: str
    group: AccountGroup
    items: tuple[GroupItem, ...]
    nsf_categories: tuple[BudgetCategory, ...]


_BILL = GroupItem(
    key="bill", needed="A bill that adds up to the charge", carries_charge_amount=True
)

ACCOUNT_GROUPS: tuple[AccountGroup, ...] = (
    AccountGroup(
        id="salaries",
        name="Salaries",
        accounts=("50", "51"),
        items=(
            GroupItem(key="appointment_letter", needed="Appointment letter"),
            GroupItem(
                key="effort_report",
                needed="Certified effort report covering the month",
                covers_charge_month=True,
            ),
        ),
        # The account doesn't say whether the person is senior or other personnel.
        nsf_categories=(BudgetCategory.SENIOR_PERSONNEL, BudgetCategory.OTHER_PERSONNEL),
    ),
    AccountGroup(
        id="benefits",
        name="Benefits",
        accounts=("53",),
        items=(GroupItem(key="benefit_rate", needed="Benefit rate"),),
        nsf_categories=(BudgetCategory.FRINGE_BENEFITS,),
    ),
    AccountGroup(
        id="tuition",
        name="Tuition and fee remission",
        # 538xx is fee remission, inside Berkeley's benefits range 53xxx.
        accounts=("538", "5742"),
        items=(GroupItem(key="appointment_letter", needed="The student's appointment letter"),),
        # Unverified: which NSF category budgets tuition and fee remission.
        # Berkeley keeps fee remission in its benefits tree.
        nsf_categories=(BudgetCategory.FRINGE_BENEFITS, BudgetCategory.OTHER_DIRECT_COSTS_OTHER),
    ),
    AccountGroup(
        id="travel",
        name="Travel",
        accounts=("5721", "5722"),
        items=(
            GroupItem(key="expense_report", needed="Expense report"),
            GroupItem(
                key="bills", needed="Bills that add up to the charge", carries_charge_amount=True
            ),
        ),
        nsf_categories=(BudgetCategory.TRAVEL,),
    ),
    AccountGroup(
        id="supplies",
        name="Supplies",
        # 551xx is computing supplies and 552xx computer equipment under $5,000.
        # NSF's line reads "Materials and Supplies (including Costs of Computing
        # Devices)".
        accounts=("550", "551", "552", "553"),
        items=(_BILL,),
        nsf_categories=(BudgetCategory.MATERIALS_AND_SUPPLIES,),
    ),
    AccountGroup(
        id="equipment",
        name="Equipment",
        # 541xx is computer equipment at $5,000 or more.
        accounts=("541", "542"),
        items=(_BILL,),
        nsf_categories=(BudgetCategory.EQUIPMENT,),
    ),
    AccountGroup(
        id="participant_support",
        name="Participant support",
        accounts=("5671",),
        items=(
            GroupItem(key="participant_list", needed="Participant list"),
            GroupItem(key="payment_record", needed="Payment record", carries_charge_amount=True),
        ),
        nsf_categories=(BudgetCategory.PARTICIPANT_SUPPORT,),
    ),
    AccountGroup(
        id="subawards",
        name="Subawards",
        # 5781x is subawards outside the University of California (UC).
        # 57820 to 57899 and 925xx are subawards to other UC campuses.
        accounts=("5781", "5782", "5783", "5784", "5785", "5786", "5787", "5788", "5789", "925"),
        items=(
            GroupItem(
                key="partner_invoice", needed="The partner's invoice", carries_charge_amount=True
            ),
            GroupItem(key="professor_approval", needed="The professor's approval to pay"),
            GroupItem(key="subaward_agreement", needed="The subaward agreement"),
        ),
        nsf_categories=(BudgetCategory.SUBAWARDS,),
    ),
    AccountGroup(
        id="consultants",
        name="Consultants and services",
        accounts=("5672",),
        items=(_BILL, GroupItem(key="agreement_or_rate", needed="The agreement or rate")),
        # The parent, not Consultant Services: 5672x also holds honoraria,
        # temporary labor and other payments to non-employees.
        nsf_categories=(BudgetCategory.OTHER_DIRECT_COSTS,),
    ),
    AccountGroup(
        id="printing",
        name="Printing",
        accounts=("564",),
        items=(_BILL,),
        # The parent, so any of its six sub-lines agrees.
        nsf_categories=(BudgetCategory.OTHER_DIRECT_COSTS,),
    ),
    AccountGroup(
        id="recharges",
        name="Internal recharges",
        accounts=("590",),
        items=(
            GroupItem(
                key="usage_statement",
                needed="The facility's usage statement",
                carries_charge_amount=True,
            ),
        ),
        # The parent, so the sample grant's Other sub-line agrees.
        nsf_categories=(BudgetCategory.OTHER_DIRECT_COSTS,),
        # A recharge account that names what was bought carries that category.
        categories_by_account={
            # Under $5,000, like other equipment under the threshold.
            "59005": (BudgetCategory.MATERIALS_AND_SUPPLIES,),  # Rechg-Fabricated Equip (OH)<5k
            "59006": (BudgetCategory.MATERIALS_AND_SUPPLIES,),  # Recharge-Supplies
            "59007": (BudgetCategory.PARTICIPANT_SUPPORT,),  # Recharge-Participant Support
            "59008": (BudgetCategory.TRAVEL,),  # Recharge-Travel
            "59012": (BudgetCategory.EQUIPMENT,),  # Rechg-Fabricated Equip (OH)>5k
            "59013": (BudgetCategory.EQUIPMENT,),  # Rechg-Fabrctd Equip(Non OH)>5k
        },
    ),
)

# Accounts inside a group's range that belong to no group.
NOT_IN_ANY_GROUP: tuple[str, ...] = (
    "56710",  # Payments to Patients or Human [Subjects]: not NSF participants
    "59000",  # Internal Recharge Income: income, not an expense
)

# Longest entry first, so the more specific one wins.
_ENTRIES: tuple[tuple[str, AccountGroup | None], ...] = tuple(
    sorted(
        [(entry, group) for group in ACCOUNT_GROUPS for entry in group.accounts]
        + [(code, None) for code in NOT_IN_ANY_GROUP],
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)

_ACCOUNT_CODE = re.compile(r"\s*(\d{5})(?!\d)")


def account_code(account: str) -> str | None:
    """The 5-digit account code at the start of a ledger account, or None.

    The ledger gives an account as a code, optionally followed by its name,
    for example "55016 Lab Instruments and Supplies".
    """
    match = _ACCOUNT_CODE.match(account)
    return match.group(1) if match else None


def lookup_account(account: str) -> AccountDefaults | None:
    """The group, default items and NSF categories for a ledger account.

    None when the account is in no group.
    """
    code = account_code(account)
    if code is None:
        return None
    for entry, group in _ENTRIES:
        if code.startswith(entry):
            if group is None:
                return None
            return AccountDefaults(
                account_code=code,
                group=group,
                items=group.items,
                nsf_categories=group.categories_by_account.get(code, group.nsf_categories),
            )
    return None


def _month_of(charge: Charge) -> Period:
    """The calendar month the cost happened in."""
    start = charge.transaction_date.replace(day=1)
    last = calendar.monthrange(start.year, start.month)[1]
    return Period(start=start, end=start.replace(day=last))


def account_group_items(charge: Charge) -> list[DefaultItem]:
    """The default checklist items a charge gets from its account group, and no others.

    In the contract's `DefaultItem` form. A line that takes money off the grant
    gets none (decision 0020). A charge's full defaults, with required
    approvals, the pre-award item and a correcting line's two items, are
    `default_items` in checklist.py, which calls this.
    """
    found = lookup_account(charge.account)
    if found is None or charge.amount_cents < 0:
        return []
    return [
        DefaultItem(
            key=item.key,
            needed=item.needed,
            amount_cents=charge.amount_cents if item.carries_charge_amount else None,
            period=_month_of(charge) if item.covers_charge_month else None,
        )
        for item in found.items
    ]
