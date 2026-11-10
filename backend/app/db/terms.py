"""The grant's end date, budget figures and closeout dates, as the checks (W2) see them.

The screens, the clock and the evidence report need the same answers the checks use, so
this module asks the checks: `period_in_force` for the end date, and the checks' own
budget grouping (by category, per notice) for each line's amount, its spending and the
award's limit, so the figures agree with the checks' grant notes. Nothing here decides a
term's force on its own.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.checks.grant_checks import _limit, _notice_budget, _notice_of  # pyright: ignore[reportPrivateUsage]
from app.checks.view import GrantView, period_in_force
from app.contracts.charges import Charge
from app.contracts.evidence import EvidenceFile
from app.contracts.records import CATEGORY_PARENT, BudgetCategory, BudgetLine, Record
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


def end_date(state: RecordState, grant_id: str) -> date | None:
    """The end date in force, the same one the checks use. None while no dates are confirmed."""
    found = period_in_force(grant_id, state.records)
    return found.end if found is not None else None


@dataclass(frozen=True)
class BudgetFigure:
    category: BudgetCategory
    line: Record  # the latest budget_line term in force in the category
    amount_cents: int  # each notice's budget for the category, added up
    spent_cents: int  # charges assigned to the category, or to one of its sub-lines


@dataclass(frozen=True)
class BudgetFigures:
    lines: list[BudgetFigure]
    limit_cents: int | None  # Total Amount Obligated to Date on the latest confirmed notice
    spent_cents: int  # the sum of the grant's charges


def budget_figures(
    grant_id: str,
    state: RecordState,
    charges: Sequence[Charge],
    files: Sequence[EvidenceFile],
) -> BudgetFigures:
    """The budget the way the checks' budget check works it out (grant_checks.grant_notes):
    one figure per NSF category, a category's amount added up per notice, its spending
    counting its sub-lines, and the limit chosen by date, amendment number, then position.

    It reads the checks' own helpers in app/checks/grant_checks.py, which are private;
    issue #105 adds a public function there to replace them and this loop."""
    view = GrantView(grant_id, state, charges, files)
    by_notice: dict[tuple[BudgetCategory, tuple[str, str]], list[Record]] = defaultdict(list)
    lines: dict[BudgetCategory, list[Record]] = defaultdict(list)
    for r in view.budget_lines():
        assert isinstance(r.data, BudgetLine)
        by_notice[(r.data.category, _notice_of(view, r))].append(r)
        lines[r.data.category].append(r)
    amount: dict[BudgetCategory, int] = defaultdict(int)
    for (category, _), members in by_notice.items():
        amount[category] += _notice_budget(category, members)
    spent: dict[BudgetCategory, int] = defaultdict(int)
    for c in view.charges:
        assigned = view.assigned_line(c.id)
        if assigned is None or assigned[1] is None:
            continue
        line = assigned[1].data
        assert isinstance(line, BudgetLine)
        spent[line.category] += c.amount_cents
        parent = CATEGORY_PARENT.get(line.category)
        if parent is not None:
            spent[parent] += c.amount_cents
    limit = _limit(view)
    return BudgetFigures(
        lines=[
            BudgetFigure(category, lines[category][-1], amount[category], spent[category])
            for category in lines
        ],
        limit_cents=limit[0] if limit else None,
        spent_cents=sum(c.amount_cents for c in view.charges),
    )


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
