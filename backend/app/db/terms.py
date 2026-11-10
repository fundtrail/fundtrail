"""The grant terms in force, and the dates that follow from the end date.

The checks (W2) decide which terms are in force for their own rules; the screens and the
clock need the same answer to show the end date, the budget and the closeout dates. This
follows the docs' rule: only terms that count (confirmed, for the agent's) are in force,
and among several of a kind the one with the latest `dated` wins. When the checks expose
their own answer, this module should read it instead.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.contracts.charges import Charge
from app.contracts.records import (
    CATEGORY_PARENT,
    BudgetAssignment,
    BudgetLine,
    Notice,
    PeriodOfPerformance,
    Record,
    RecordKind,
)
from app.contracts.rules import RecordState

# The closeout steps that follow from the end date (domain.md, Closeout: Berkeley's
# Notices of Expiration, then NSF's 90-day financial and 120-day report deadlines).
# The Award Closeout Certification depends on Berkeley's own ledger calendar, so it
# isn't worked out (decision 0022).
CLOSEOUT_STEPS: tuple[tuple[int, str], ...] = (
    (-90, "First Notice of Expiration"),
    (-60, "Second Notice of Expiration"),
    (-30, "Third Notice of Expiration"),
    (0, "End date"),
    (90, "Final financial report due"),
    (120, "Final reports due to NSF"),
)
CLOSEOUT_WINDOW_DAYS = 90


def _shared_period_in_force() -> Callable[..., Any] | None:
    try:
        module = importlib.import_module("app.checks.view")
    except ImportError:
        return None
    return getattr(module, "period_in_force", None)


def counting(state: RecordState, kind: RecordKind) -> list[Record]:
    """The current records of a kind, in the order written."""
    return [r for r in state.current() if r.kind == kind]


def _latest(records: Sequence[Record]) -> Record | None:
    best: Record | None = None
    for r in records:  # in the order written, so a later one wins a tie
        dated = getattr(r.data, "dated", None)
        best_dated = getattr(best.data, "dated", None) if best else None
        if best is None or (dated and best_dated and dated.value >= best_dated.value):
            best = r
    return best


def period_in_force(state: RecordState) -> Record | None:
    return _latest(counting(state, RecordKind.PERIOD_OF_PERFORMANCE))


def end_date(state: RecordState, grant_id: str | None = None) -> date | None:
    """The end date in force. Uses the checks' own `period_in_force` (#24) once it's there,
    so the screens and the checks agree; until then, the rule below."""
    shared = _shared_period_in_force()
    if shared is not None and grant_id is not None:
        found = shared(grant_id, state.records)
        return found.end if found is not None else None
    period = period_in_force(state)
    if period is None:
        return None
    assert isinstance(period.data, PeriodOfPerformance)
    return period.data.end.value


def budget_lines(state: RecordState) -> list[Record]:
    return counting(state, RecordKind.BUDGET_LINE)


def award_limit(state: RecordState) -> int | None:
    """ "Total Amount Obligated to Date" on the latest counting notice that prints it."""
    notices = [
        r
        for r in counting(state, RecordKind.NOTICE)
        if isinstance(r.data, Notice) and r.data.obligated_to_date is not None
    ]
    latest = _latest(notices)
    if latest is None:
        return None
    assert isinstance(latest.data, Notice) and latest.data.obligated_to_date is not None
    return latest.data.obligated_to_date.value


def assigned_lines(state: RecordState) -> dict[str, Record]:
    """Each charge's budget line: its current assignment's line, after corrections."""
    out: dict[str, Record] = {}
    for r in state.current():
        if isinstance(r.data, BudgetAssignment):
            line = state.current_version(r.data.record_id)
            if line is not None and line.kind == RecordKind.BUDGET_LINE:
                out[r.data.charge_id] = line
    return out


def spent_by_line(state: RecordState, charges: Sequence[Charge]) -> dict[str, int]:
    """Spending on each budget line in force. A sub-line's spending also counts toward the
    line whose category contains it, as Other Direct Costs contains its six sub-lines."""
    lines = budget_lines(state)
    assigned = assigned_lines(state)
    spent = {line.id: 0 for line in lines}
    for c in charges:
        line = assigned.get(c.id)
        if line is None:
            continue
        assert isinstance(line.data, BudgetLine)
        parent = CATEGORY_PARENT.get(line.data.category)
        for other in lines:
            assert isinstance(other.data, BudgetLine)
            if other.id == line.id or (parent is not None and other.data.category == parent):
                spent[other.id] += c.amount_cents
    return spent


@dataclass(frozen=True)
class CloseoutStep:
    date: date
    label: str


def closeout_steps(end: date) -> list[CloseoutStep]:
    return [CloseoutStep(end + timedelta(days=d), label) for d, label in CLOSEOUT_STEPS]


def next_closeout(end: date | None, today: date) -> CloseoutStep | None:
    if end is None:
        return None
    return next((s for s in closeout_steps(end) if s.date >= today), None)


def closeout_window_opens(end: date | None) -> date | None:
    return end - timedelta(days=CLOSEOUT_WINDOW_DAYS) if end else None
