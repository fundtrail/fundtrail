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
  charge and the reason's check and problem. When snoozes on the charge hide it on that
  date, it's held back to the first later date the charge isn't snoozed: a snooze ends, or
  a reason no running snooze names comes due. Only reasons that flag the charge count, as
  run_checks decides it: an accepted reason, or one shown on its term's row (the period or
  a budget line not yet confirmed), never ends a snooze. A missing approval is on the list
  right away, so it has no such date; a fully reversed charge never goes on the list.

Only dates after the grant's "now" are given, in date order.
"""

from dataclasses import dataclass
from datetime import date

from app.checks.charge_checks import evaluate_charge, suggestions_by_charge
from app.checks.decisions import Decisions
from app.checks.findings import Finding
from app.checks.record_checks import over_linked_bills
from app.checks.view import GrantView
from app.contracts.checks import Bucket, ChecksInput
from app.contracts.records import Record, Snooze
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


def _hidden(day: date, snoozes: list[tuple[Record, date]], due: list[tuple[Finding, date]]) -> bool:
    """Whether a charge is snoozed on a day: some snooze on it is still running, and the
    ones still running name every reason on the list that day (as Decisions.snoozed)."""
    running = [r for r, ends in snoozes if ends > day]
    if not running:
        return False
    named = {
        (x.check, x.problem) for r in running if isinstance(r.data, Snooze) for x in r.data.reasons
    }
    return all((f.check, f.problem) in named for f, on in due if on <= day)


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

    suggestions = suggestions_by_charge(view)
    over_linked = over_linked_bills(view)
    for charge in view.charges:
        found = view.nets.get(charge.id)
        if found is not None and found.reversed:
            continue  # a fully reversed charge never goes on the list
        evaluated = evaluate_charge(
            charge, view, suggestions.get(charge.id, []), list(ci.failed_runs), over_linked
        )
        marked = [m for m in dec.mark_charge(charge, evaluated.findings) if m.finding.failing]
        # When each failing reason first goes on the list, as run_checks decides it: an
        # accepted reason or one shown on its term's row never does.
        due: list[tuple[Finding, date]] = []
        for m in marked:
            on = dec.due_on(m.finding, charge.posting_date)
            if m.accepted_by is None and on is not None:
                due.append((m.finding, on))
        snoozes = [
            (r, dec.snooze_ends(r))
            for r in dec.snoozes
            if isinstance(r.data, Snooze) and r.data.charge_id == charge.id
        ]

        turning_points = sorted({on for _, on in due} | {ends for _, ends in snoozes})
        for finding, on in due:
            if finding.bucket != Bucket.MISSING_EVIDENCE or on <= today:
                continue  # already on the list, or not a missing item
            # The first day from its own date when the charge isn't snoozed.
            reaches = next(
                (d for d in turning_points if d >= on and not _hidden(d, snoozes, due)), on
            )
            out.append(
                UpcomingDate(
                    reaches,
                    MISSING_FLAGGED,
                    charge_id=charge.id,
                    check=finding.check,
                    problem=finding.problem,
                )
            )

    return sorted(out, key=lambda u: (u.on, u.kind, u.charge_id or "", u.record_id or ""))
