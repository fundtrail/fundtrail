"""The checks (W2): code's clear-cut rules, the buckets and the problem list.

What other areas call:

- run_checks: rerun every check on a workspace (contracts.md section 8)
- default_items: a charge's full default checklist, for the write check
- budget_figures: a grant's budget figures, as the grant notes compute them
- note_covers, note_limit, Coverage: how a reusable note stands toward a charge
- OVER_LIMIT, BUDGET: the award limit's problem ID and its check
- history_line: one line of status history
- period_in_force: the grant's period in force
- likely_duplicates: bills that look like a new one
- upcoming_dates: the dates the checks work out after a grant's now, for "Coming up"
"""

from app.checks.checklist import default_items
from app.checks.decisions import Coverage, note_covers, note_limit
from app.checks.duplicates import likely_duplicates
from app.checks.findings import BUDGET, OVER_LIMIT
from app.checks.grant_checks import BudgetFigures, CategoryFigure, LineFigure, budget_figures
from app.checks.history import history_line
from app.checks.run import run_checks
from app.checks.upcoming import UpcomingDate, upcoming_dates
from app.checks.view import period_in_force

__all__ = [
    "BUDGET",
    "OVER_LIMIT",
    "BudgetFigures",
    "CategoryFigure",
    "Coverage",
    "LineFigure",
    "budget_figures",
    "default_items",
    "history_line",
    "likely_duplicates",
    "note_covers",
    "note_limit",
    "period_in_force",
    "run_checks",
    "UpcomingDate",
    "upcoming_dates",
]
