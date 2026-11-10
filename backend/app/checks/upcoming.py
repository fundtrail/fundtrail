"""The dates the checks work out after a grant's "now", for a timeline's "Coming up" (#165).

Pure, like run_checks. It gives each date, a short kind, and what it belongs to, with no
wording: the screens word it. The kinds:

- `snooze_ends`: a snooze stops hiding its problems (its own date, or earlier when the
  closeout window opens). It belongs to the snooze and its subject.
- `closeout_window_opens`: the 90 days before the end date start, when every missing item
  goes on the problem list and every snooze ends.
- `grant_ends`: the end date in force.
- `missing_flagged`: a missing item goes on the problem list, 60 days past the date it
  was expected or when the closeout window opens, whichever is first. It belongs to the
  charge and the reason's check and problem. A missing approval is on the list right
  away, so it has no such date; a fully reversed charge never goes on the list.

Only dates after the grant's "now" are given, in date order.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.checks.decisions import Decisions
from app.checks.findings import APPROVAL
from app.checks.run import run_checks
from app.checks.view import GrantView
from app.contracts.checks import MISSING_EVIDENCE_DAYS, Bucket, ChecksInput
from app.contracts.records import Snooze
from app.contracts.rules import RecordState

SNOOZE_ENDS = "snooze_ends"
CLOSEOUT_WINDOW_OPENS = "closeout_window_opens"
GRANT_ENDS = "grant_ends"
MISSING_FLAGGED = "missing_flagged"


@dataclass(frozen=True)
class UpcomingDate:
    on: date
    kind: str  # one of the kinds above
    charge_id: str | None = None
    record_id: str | None = None  # the snooze, for snooze_ends
    file_id: str | None = None
    check: str | None = None  # for missing_flagged: the reason's check and problem
    problem: str | None = None


def upcoming_dates(checks_input: ChecksInput, grant_id: str) -> list[UpcomingDate]:
    """The dates the checks work out on one grant after `checks_input.now`, in date order.

    `checks_input` is what run_checks takes: everything visible at the grant's "now".
    """
    ci = checks_input
    today = ci.now.date()
    view = GrantView(grant_id, RecordState(ci.records, ci.files), ci.charges, ci.files)
    dec = Decisions(view, ci.now)
    out: list[UpcomingDate] = []

    window = dec.window_opens()
    if window is not None and window > today:
        out.append(UpcomingDate(window, CLOSEOUT_WINDOW_OPENS))
    if view.period is not None and not view.period.disagree and view.period.end > today:
        out.append(UpcomingDate(view.period.end, GRANT_ENDS))

    for r in dec.snoozes:
        data = r.data
        assert isinstance(data, Snooze)
        ends = dec.snooze_ends(r)
        if ends > today:
            out.append(
                UpcomingDate(
                    ends,
                    SNOOZE_ENDS,
                    charge_id=data.charge_id,
                    record_id=r.id,
                    file_id=data.file_id,
                )
            )

    for status in run_checks(ci).charges:
        if status.grant_id != grant_id or status.reversed:
            continue
        for reason in status.reasons:
            if reason.bucket != Bucket.MISSING_EVIDENCE or reason.accepted_by is not None:
                continue
            if reason.expected_by is None or reason.check == APPROVAL:
                continue  # a missing approval is on the list right away
            on = reason.expected_by + timedelta(days=MISSING_EVIDENCE_DAYS)
            if window is not None:
                on = min(on, window)
            if on > today:
                out.append(
                    UpcomingDate(
                        on,
                        MISSING_FLAGGED,
                        charge_id=status.charge_id,
                        check=reason.check,
                        problem=reason.problem,
                    )
                )

    return sorted(out, key=lambda u: (u.on, u.kind, u.charge_id or "", u.record_id or ""))
