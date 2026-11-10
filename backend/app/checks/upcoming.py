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
  charge and the reason's check and problem. When a snooze names the reason before it's
  due, it's held back to the snooze's end, or to the first date a reason the snooze
  doesn't name comes due on the same charge, whichever is first. A missing approval is on the
  list right away, so it has no such date; a fully reversed charge never goes on the list.

Only dates after the grant's "now" are given, in date order.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.checks.decisions import Decisions
from app.checks.findings import APPROVAL
from app.checks.run import run_checks
from app.checks.view import GrantView
from app.contracts.checks import MISSING_EVIDENCE_DAYS, Bucket, ChecksInput, Reason
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
    # For a snooze on a record (such as a bill): the record it's about.
    about_record_id: str | None = None
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
                    about_record_id=data.record_id,
                )
            )

    for status in run_checks(ci).charges:
        if status.grant_id != grant_id or status.reversed:
            continue

        def due(reason: Reason) -> date | None:
            """When a failing reason goes on the problem list, before any snooze."""
            if reason.accepted_by is not None:
                return None
            if reason.bucket in (Bucket.POSSIBLE_CONFLICT, Bucket.NEEDS_HUMAN):
                return today
            if reason.bucket != Bucket.MISSING_EVIDENCE:
                return None
            if reason.check == APPROVAL or reason.expected_by is None:
                return today  # a missing approval is on the list right away
            on = reason.expected_by + timedelta(days=MISSING_EVIDENCE_DAYS)
            return min(on, window) if window is not None else on

        # A snooze hides a charge only while every reason on the list is one it names.
        snoozes = [
            r
            for r in dec.snoozes
            if isinstance(r.data, Snooze) and r.data.charge_id == status.charge_id
        ]
        covered: dict[tuple[str, str], date] = {}  # a reason a snooze names -> its latest end
        for r in snoozes:
            snooze = r.data
            assert isinstance(snooze, Snooze)
            for x in snooze.reasons:
                key = (x.check, x.problem)
                covered[key] = max(covered.get(key, date.min), dec.snooze_ends(r))
        # A snooze hides the charge only while every reason on the list is one it names,
        # so the first uncovered reason to come due ends the hiding for the covered ones.
        uncovered = [
            d
            for reason in status.reasons
            if (reason.check, reason.problem) not in covered and (d := due(reason)) is not None
        ]
        first_uncovered = min(uncovered, default=None)

        for reason in status.reasons:
            if reason.bucket != Bucket.MISSING_EVIDENCE:
                continue
            on = due(reason)
            if on is None or on <= today:
                continue  # accepted, or already on the list
            key = (reason.check, reason.problem)
            if key in covered:
                # Held back until the snooze ends, or until an uncovered reason on the same
                # charge comes due and the charge is no longer snoozed.
                held = covered[key]
                if first_uncovered is not None:
                    held = min(held, first_uncovered)
                on = max(on, held)
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
