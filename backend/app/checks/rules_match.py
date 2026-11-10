"""Which of the grant's approval rules apply to a charge.

How code matches an approval rule's applies_to, as the award letter words it, to
the charge's assigned budget line is a builder choice (contracts.md, "Not decided
yet"). Provisional rule:

1. applies_to is compared with the names of the grant's budget lines, then with
   NSF's own category names, after dropping case, punctuation, a leading line
   letter ("F. ") and a trailing "Costs". It has to name exactly one category.
2. A rule applies when either side says so (contracts.md section 2): the
   assigned line is the rule's category or sits inside it, or one of the ledger
   account's categories is the rule's category or sits inside it.
3. A confirmed rule that names no category code can recognize can't be applied
   safely, so every charge on the grant gets a Needs a human reason for it.
"""

import re
from dataclasses import dataclass

from app.checks.ledger_accounts import CATEGORY_NAMES, categories
from app.checks.text import norm
from app.checks.view import GrantView
from app.contracts.charges import Charge
from app.contracts.records import (
    CATEGORY_PARENT,
    ApprovalRule,
    BudgetCategory,
    BudgetLine,
    Record,
    RecordKind,
)


def name_key(text: str) -> str:
    """A budget line name for comparing.

    No case or punctuation, no leading line letter ("F. "), no trailing "Costs".
    """
    words = norm(text)
    words = re.sub(r"^[a-m] ", "", words)
    return re.sub(r" costs$", "", words)


def rule_category(view: GrantView, rule: Record) -> BudgetCategory | None:
    """The NSF category an approval rule's applies_to names, or None when code can't tell."""
    assert isinstance(rule.data, ApprovalRule)
    target = name_key(rule.data.applies_to.value)
    lines = view.budget_lines() + [
        r for r in view.waiting_terms if r.kind == RecordKind.BUDGET_LINE
    ]
    found = {
        r.data.category
        for r in lines
        if isinstance(r.data, BudgetLine) and name_key(r.data.name.value) == target
    }
    if not found:
        found = {
            cat
            for cat, names in CATEGORY_NAMES.items()
            if any(name_key(n) == target for n in names)
        }
    return found.pop() if len(found) == 1 else None


def _within(category: BudgetCategory, rule_category: BudgetCategory) -> bool:
    return category == rule_category or CATEGORY_PARENT.get(category) == rule_category


def rule_applies(view: GrantView, charge: Charge, category: BudgetCategory) -> bool:
    assigned = view.assigned_line(charge.id)
    if assigned is not None and assigned[1] is not None:
        line = assigned[1].data
        assert isinstance(line, BudgetLine)
        if _within(line.category, category):
            return True
    return any(_within(c, category) for c in categories(charge.account))


@dataclass(frozen=True)
class RulesForCharge:
    applying: list[Record]  # confirmed rules that apply
    unmatched: list[Record]  # confirmed rules code can't place
    waiting: list[Record]  # rules still waiting for the accountant that would apply


def rules_for(view: GrantView, charge: Charge) -> RulesForCharge:
    applying: list[Record] = []
    unmatched: list[Record] = []
    for rule in view.approval_rules():
        category = rule_category(view, rule)
        if category is None:
            unmatched.append(rule)
        elif rule_applies(view, charge, category):
            applying.append(rule)
    waiting: list[Record] = []
    for rule in view.waiting_terms:
        if rule.kind != RecordKind.APPROVAL_RULE:
            continue
        if rule.replaces_id is not None and view.state.is_current(rule.replaces_id):
            continue  # a correction waits, and the older confirmed rule stays in force
        category = rule_category(view, rule)
        if category is not None and rule_applies(view, charge, category):
            waiting.append(rule)
    return RulesForCharge(applying, unmatched, waiting)
