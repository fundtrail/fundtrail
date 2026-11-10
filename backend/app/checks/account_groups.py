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
  budget line the agent assigned agree when that line is one of the categories,
  or sits inside one of them. Comparing them is the checks' job, not this table's.
- Reversals and cost transfers are not a group. Their default items apply to any
  line that corrects another, whatever its account, and are left out here until
  decision 0020 settles them. Such a line's NSF category still comes from its
  account.

The types here are plain and local on purpose. The contract models for checklist
items aren't written yet, and these will be aligned with them once they are.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NsfLine:
    """One of NSF's standard budget categories, or a sub-line of one.

    Named as domain.md's budget lines table prints them. `parent` is the
    category a sub-line sits in, from NSF's fixed list: Other Direct Costs
    contains Materials and Supplies, Publication Costs, Consultant Services,
    Computer Services, Subawards and Other.
    """

    name: str
    parent: str | None = None


SENIOR_PERSONNEL = NsfLine("Senior Personnel")
OTHER_PERSONNEL = NsfLine("Other Personnel")
FRINGE_BENEFITS = NsfLine("Fringe Benefits")
EQUIPMENT = NsfLine("Equipment")
TRAVEL = NsfLine("Travel")
PARTICIPANT_SUPPORT_COSTS = NsfLine("Participant Support Costs")
OTHER_DIRECT_COSTS = NsfLine("Other Direct Costs")

MATERIALS_AND_SUPPLIES = NsfLine("Materials and Supplies", parent=OTHER_DIRECT_COSTS.name)
PUBLICATION_COSTS = NsfLine("Publication Costs", parent=OTHER_DIRECT_COSTS.name)
CONSULTANT_SERVICES = NsfLine("Consultant Services", parent=OTHER_DIRECT_COSTS.name)
COMPUTER_SERVICES = NsfLine("Computer Services", parent=OTHER_DIRECT_COSTS.name)
SUBAWARDS = NsfLine("Subawards", parent=OTHER_DIRECT_COSTS.name)
OTHER_DIRECT_COSTS_OTHER = NsfLine("Other", parent=OTHER_DIRECT_COSTS.name)

OTHER_DIRECT_COSTS_SUB_LINES: tuple[NsfLine, ...] = (
    MATERIALS_AND_SUPPLIES,
    PUBLICATION_COSTS,
    CONSULTANT_SERVICES,
    COMPUTER_SERVICES,
    SUBAWARDS,
    OTHER_DIRECT_COSTS_OTHER,
)


@dataclass(frozen=True)
class DefaultItem:
    """One default checklist item, as domain.md words it.

    `id` is stable, so a link or a removal can name a default item that isn't
    stored. `carries_charge_amount` marks the item that stands for the bill-like
    document: it carries the charge's amount, and covers whatever the charge's
    other amount-carrying items don't (the checks work that out).
    `covers_charge_month` means the document has to cover the month of the charge.
    """

    id: str
    text: str
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
    default_items: tuple[DefaultItem, ...]
    nsf_categories: tuple[NsfLine, ...]
    categories_by_account: dict[str, tuple[NsfLine, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountDefaults:
    """What the table gives one ledger account."""

    account_code: str
    group: AccountGroup
    default_items: tuple[DefaultItem, ...]
    nsf_categories: tuple[NsfLine, ...]


def _bill(group_id: str) -> DefaultItem:
    return DefaultItem(
        id=f"{group_id}.bill",
        text="A bill that adds up to the charge",
        carries_charge_amount=True,
    )


ACCOUNT_GROUPS: tuple[AccountGroup, ...] = (
    AccountGroup(
        id="salaries",
        name="Salaries",
        accounts=("50", "51"),
        default_items=(
            DefaultItem(id="salaries.appointment_letter", text="Appointment letter"),
            DefaultItem(
                id="salaries.effort_report",
                text="Certified effort report covering the month",
                covers_charge_month=True,
            ),
        ),
        # The account doesn't say whether the person is senior or other personnel.
        nsf_categories=(SENIOR_PERSONNEL, OTHER_PERSONNEL),
    ),
    AccountGroup(
        id="benefits",
        name="Benefits",
        accounts=("53",),
        default_items=(DefaultItem(id="benefits.rate", text="Benefit rate"),),
        nsf_categories=(FRINGE_BENEFITS,),
    ),
    AccountGroup(
        id="tuition",
        name="Tuition and fee remission",
        # 538xx is fee remission, inside Berkeley's benefits range 53xxx.
        accounts=("538", "5742"),
        default_items=(
            DefaultItem(id="tuition.appointment_letter", text="The student's appointment letter"),
        ),
        # Unverified: which NSF category budgets tuition and fee remission.
        # Berkeley keeps fee remission in its benefits tree.
        nsf_categories=(FRINGE_BENEFITS, OTHER_DIRECT_COSTS_OTHER),
    ),
    AccountGroup(
        id="travel",
        name="Travel",
        accounts=("5721", "5722"),
        default_items=(
            DefaultItem(id="travel.expense_report", text="Expense report"),
            DefaultItem(
                id="travel.bills",
                text="Bills that add up to the charge",
                carries_charge_amount=True,
            ),
        ),
        nsf_categories=(TRAVEL,),
    ),
    AccountGroup(
        id="supplies",
        name="Supplies",
        # 551xx is computing supplies and 552xx computer equipment under $5,000.
        # NSF's line reads "Materials and Supplies (including Costs of Computing
        # Devices)".
        accounts=("550", "551", "552", "553"),
        default_items=(_bill("supplies"),),
        nsf_categories=(MATERIALS_AND_SUPPLIES,),
    ),
    AccountGroup(
        id="equipment",
        name="Equipment",
        # 541xx is computer equipment at $5,000 or more.
        accounts=("541", "542"),
        default_items=(_bill("equipment"),),
        nsf_categories=(EQUIPMENT,),
    ),
    AccountGroup(
        id="participant_support",
        name="Participant support",
        accounts=("5671",),
        default_items=(
            DefaultItem(id="participant_support.participant_list", text="Participant list"),
            DefaultItem(
                id="participant_support.payment_record",
                text="Payment record",
                carries_charge_amount=True,
            ),
        ),
        nsf_categories=(PARTICIPANT_SUPPORT_COSTS,),
    ),
    AccountGroup(
        id="subawards",
        name="Subawards",
        # 5781x is subawards outside the University of California (UC).
        # 57820 to 57899 and 925xx are subawards to other UC campuses.
        accounts=("5781", "5782", "5783", "5784", "5785", "5786", "5787", "5788", "5789", "925"),
        default_items=(
            DefaultItem(
                id="subawards.partner_invoice",
                text="The partner's invoice",
                carries_charge_amount=True,
            ),
            DefaultItem(id="subawards.professor_approval", text="The professor's approval to pay"),
            DefaultItem(id="subawards.agreement", text="The subaward agreement"),
        ),
        nsf_categories=(SUBAWARDS,),
    ),
    AccountGroup(
        id="consultants",
        name="Consultants and services",
        accounts=("5672",),
        default_items=(
            _bill("consultants"),
            DefaultItem(id="consultants.agreement_or_rate", text="The agreement or rate"),
        ),
        # The parent, not Consultant Services: 5672x also holds honoraria,
        # temporary labor and other payments to non-employees.
        nsf_categories=(OTHER_DIRECT_COSTS,),
    ),
    AccountGroup(
        id="printing",
        name="Printing",
        accounts=("564",),
        default_items=(_bill("printing"),),
        # The parent, so any of its six sub-lines agrees.
        nsf_categories=(OTHER_DIRECT_COSTS,),
    ),
    AccountGroup(
        id="recharges",
        name="Internal recharges",
        accounts=("590",),
        default_items=(
            DefaultItem(
                id="recharges.usage_statement",
                text="The facility's usage statement",
                carries_charge_amount=True,
            ),
        ),
        # The parent, so the sample grant's Other sub-line agrees.
        nsf_categories=(OTHER_DIRECT_COSTS,),
        # A recharge account that names what was bought carries that category.
        categories_by_account={
            "59005": (EQUIPMENT,),  # Rechg-Fabricated Equip (OH)<5k
            "59006": (MATERIALS_AND_SUPPLIES,),  # Recharge-Supplies
            "59007": (PARTICIPANT_SUPPORT_COSTS,),  # Recharge-Participant Support
            "59008": (TRAVEL,),  # Recharge-Travel
            "59012": (EQUIPMENT,),  # Rechg-Fabricated Equip (OH)>5k
            "59013": (EQUIPMENT,),  # Rechg-Fabrctd Equip(Non OH)>5k
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
                default_items=group.default_items,
                nsf_categories=group.categories_by_account.get(code, group.nsf_categories),
            )
    return None
