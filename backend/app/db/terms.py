"""The grant's end date and closeout dates, as the checks (W2) see them.

The screens, the clock and the evidence report need the same answers the checks use, so
this module asks the checks: `period_in_force` for the end date. The budget figures come
from the checks' public `budget_figures` directly. Nothing here decides a term's force
on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.checks.view import period_in_force
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
