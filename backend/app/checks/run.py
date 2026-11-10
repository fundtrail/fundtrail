"""run_checks: rerun every check on a workspace (contracts.md section 8).

A pure function: no database, no model, no clock but the input's `now`. The
caller passes everything in the workspace visible at `now`, records in the order
they were written, including replaced, waiting and rejected ones.

    from app.checks.run import run_checks
"""

from app.checks.charge_checks import evaluate_charge, suggestions_by_charge
from app.checks.checklist import default_items
from app.checks.decisions import Decisions, Marked, SubjectKey
from app.checks.grant_checks import grant_notes, grant_problems
from app.checks.record_checks import over_linked_bills, record_problems
from app.checks.view import GrantView
from app.contracts.checks import (
    ChargeStatus,
    ChecksInput,
    ChecksOutput,
    GrantNote,
    GrantStatus,
    OpenQuestion,
    Problem,
    Reason,
    RecordStatus,
    most_serious,
)
from app.contracts.rules import RecordState

__all__ = ["run_checks", "default_items"]


def _reason(m: Marked) -> Reason:
    f = m.finding
    return Reason(
        check=f.check,
        problem=f.problem,
        text=f.text,
        record_ids=tuple(dict.fromkeys(f.record_ids)),
        bucket=f.bucket,
        expected_by=f.expected_by,
        accepted_by=m.accepted_by,
        offered_note_id=m.offered_note_id,
    )


def _problem(m: Marked) -> Problem:
    f = m.finding
    return Problem(
        check=f.check, problem=f.problem, text=f.text, record_ids=tuple(dict.fromkeys(f.record_ids))
    )


def run_checks(checks_input: ChecksInput) -> ChecksOutput:
    """Rerun every check.

    Returns each charge's status, the records and files with problems, the grant's
    problems, the open questions and the grant notes.
    """
    ci = checks_input
    state = RecordState(ci.records, ci.files)
    grant_ids = list(
        dict.fromkeys(
            [c.grant_id for c in ci.charges]
            + [f.grant_id for f in ci.files]
            + [r.grant_id for r in ci.records]
        )
    )
    views = {g: GrantView(g, state, ci.charges, ci.files) for g in grant_ids}
    decisions = {g: Decisions(v, ci.now) for g, v in views.items()}
    suggestions = {g: suggestions_by_charge(v) for g, v in views.items()}
    over_linked = {g: over_linked_bills(v) for g, v in views.items()}

    charges: list[ChargeStatus] = []
    questions: list[OpenQuestion] = []
    for charge in ci.charges:
        view, dec = views[charge.grant_id], decisions[charge.grant_id]
        found = evaluate_charge(
            charge,
            view,
            suggestions[charge.grant_id].get(charge.id, []),
            list(ci.failed_runs),
            over_linked[charge.grant_id],
        )
        marked = dec.mark_charge(charge, found.findings)
        failing = [m for m in marked if m.finding.failing]
        flagging = [
            m for m in failing if m.accepted_by is None and dec.due(m.finding, charge.posting_date)
        ]
        snoozed = dec.snoozed(SubjectKey(charge_id=charge.id), flagging)
        charges.append(
            ChargeStatus(
                grant_id=charge.grant_id,
                charge_id=charge.id,
                bucket=most_serious([m.finding.bucket for m in marked]),
                reasons=tuple(_reason(m) for m in marked),
                checklist=tuple(found.entries),
                flagged=bool(flagging) and not snoozed,
                rechecking=found.rechecking,
                accepted=bool(failing) and all(m.accepted_by is not None for m in failing),
                snoozed=snoozed,
            )
        )
        questions += found.questions

    records: list[RecordStatus] = []
    grants: list[GrantStatus] = []
    notes: list[GrantNote] = []
    for g, view in views.items():
        dec = decisions[g]
        by_subject: dict[SubjectKey, list[Marked]] = {}
        for sf in record_problems(view, ci.now, list(ci.failed_runs)):
            key = SubjectKey(record_id=sf.subject.record_id, file_id=sf.subject.file_id)
            by_subject.setdefault(key, [])
            by_subject[key] += dec.mark_other(key, [sf.finding])
        for key, marked in by_subject.items():
            open_ = [m for m in marked if m.accepted_by is None]
            snoozed = dec.snoozed(key, open_)
            records.append(
                RecordStatus(
                    grant_id=g,
                    record_id=key.record_id,
                    file_id=key.file_id,
                    problems=tuple(_problem(m) for m in marked),
                    flagged=bool(open_) and not snoozed,
                    accepted=not open_,
                    snoozed=snoozed,
                )
            )
        found = grant_problems(view)
        if found:
            key = SubjectKey()
            marked = dec.mark_other(key, found)
            open_ = [m for m in marked if m.accepted_by is None]
            snoozed = dec.snoozed(key, open_)
            grants.append(
                GrantStatus(
                    grant_id=g,
                    problems=tuple(_problem(m) for m in marked),
                    flagged=bool(open_) and not snoozed,
                    accepted=not open_,
                    snoozed=snoozed,
                )
            )
        notes += grant_notes(view)

    return ChecksOutput(
        charges=tuple(charges),
        records=tuple(records),
        grants=tuple(grants),
        questions=tuple(questions),
        notes=tuple(notes),
    )
