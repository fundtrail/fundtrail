"""Inputs the report needs that no contract carries yet.

Each type here is a stand-in, kept small and in one place so it can be swapped
for the contract's own type when it lands:

- the terms in force and the budget figures: the checks' output, which reports
  them for the grant page too (issue #39)

The report reads these as given. It never works any of them out itself.
"""

from app.contracts.base import Cents, Id, Model
from app.contracts.records import Period


class BudgetFigure(Model):
    """Spending against one budget line in force. Stand-in for the checks' output (#39)."""

    record_id: Id  # the budget_line term in force
    spent_cents: Cents
    over: bool


class TermsInForce(Model):
    """The grant's terms in force at "now", as the checks report them. Stand-in for #39."""

    period: Period | None = None  # the dates in force
    # The period_of_performance terms they come from: an amendment may state only
    # a new end date, so the start can come from an earlier term.
    period_ids: tuple[Id, ...] = ()
    limit_notice_id: Id | None = None  # the latest confirmed notice: the award's limit
    spent_cents: Cents = 0  # spending against the award's limit
    over_limit: bool = False
    budget: tuple[BudgetFigure, ...] = ()
    # Every other term in force: people, approval rules, rates and other terms.
    other_term_ids: tuple[Id, ...] = ()
