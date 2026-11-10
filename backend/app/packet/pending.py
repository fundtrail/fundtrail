"""Inputs the report needs that no contract carries yet.

Each type here is a stand-in, kept small and in one place so it can be swapped
for the contract's own type when it lands:

- the reversed state, the net amount and how corrections are grouped
  (decisions 0020 and 0022), held mail (0025), and "ready for closeout" (0022):
  the second contract change, issue #39
- the terms in force and the budget figures: the checks' output, which reports
  them for the grant page too (issue #39)

The report reads these as given. It never works any of them out itself.
"""

from app.contracts.base import Cents, Id, Model, Text, UtcDatetime
from app.contracts.records import Period


class ChargeLedgerState(Model):
    """One charge read together with the lines that correct it (0020). Stand-in for #39."""

    charge_id: Id
    net_cents: Cents  # the charge's amount netted with its corrections
    reversed: bool = False  # fully corrected: the net is zero
    # The correcting charges shown under this one, in the order to show them.
    corrections: tuple[Id, ...] = ()
    # Evidence complete, accepted or fully reversed (0022). Never true for a snoozed charge.
    ready: bool


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


class HeldMessage(Model):
    """Mail held from a sender nobody knows (0025). Stand-in for #39."""

    id: Id
    sender: Text
    arrived_at: UtcDatetime
    subject: str | None = None
