"""The evidence report (decision 0022): gathers #38's ReportInputs at a moment and builds the PDF.

The draft route builds it with no sign-off. Signing off builds it with the sign-off on it,
under the grant's lock (`actions.add_sign_off`), stores the PDF, and writes the sign_off
record with the report's path, checksum and snapshot.
"""

from __future__ import annotations

from datetime import datetime

from app.checks.grant_checks import _limit  # pyright: ignore[reportPrivateUsage]
from app.checks.view import GrantView, period_in_force
from app.contracts.checks import ChecksInput, StatusEntry
from app.contracts.records import Period, RecordKind
from app.contracts.rules import RecordState
from app.contracts.signoff import SignOffSnapshot
from app.contracts.workspaces import Grant, User
from app.db import store, terms
from app.db.platform import Platform
from app.db.store import Conn
from app.packet import BudgetFigure, ReportInputs, Signing, TermsInForce, build_report

from .views import load_snapshot, snapshot_now

# Files whose text the report quotes by line number.
_TEXT_TYPES = ("text/", "message/rfc822")
# Terms in force other than the dates, the budget and the notices.
_OTHER_TERMS = {RecordKind.PERSON, RecordKind.APPROVAL_RULE, RecordKind.RATE, RecordKind.OTHER_TERM}


def _terms_in_force(grant: Grant, state: RecordState, snap_charges, snap_files) -> TermsInForce:  # noqa: ANN001
    """The report's terms in force, from the checks' own answers (period_in_force, the budget
    check's figures and its award limit)."""
    period = period_in_force(grant.id, state.records)
    figures = terms.budget_figures(grant.id, state, snap_charges, snap_files)
    limit = _limit(GrantView(grant.id, state, snap_charges, snap_files))
    return TermsInForce(
        period=Period(start=period.start, end=period.end)
        if period is not None and period.start is not None
        else None,
        period_ids=tuple(period.record_ids) if period is not None else (),
        limit_notice_id=limit[1].id if limit else None,
        spent_cents=figures.spent_cents,
        over_limit=limit is not None and figures.spent_cents > limit[0],
        budget=tuple(
            BudgetFigure(
                record_id=f.line.id, spent_cents=f.spent_cents, over=f.spent_cents > f.amount_cents
            )
            for f in figures.lines
        ),
        other_term_ids=tuple(r.id for r in state.current() if r.kind in _OTHER_TERMS),
    )


def report_inputs(
    p: Platform, conn: Conn, grant: Grant, now: datetime, signing: Signing | None
) -> ReportInputs:
    workspace = store.workspace_by_id(conn, grant.workspace_id)
    preparer = store.get_user(conn, workspace.owner_id) or User(
        id=workspace.owner_id, email="unknown@university.example"
    )
    charges = store.list_charges(conn, grant.id, now)
    files = store.list_files(conn, grant.id, now)
    records = store.list_records(conn, grant.id, now)
    output = p.checks.run_checks(
        ChecksInput(
            now=now,
            charges=tuple(charges),
            files=tuple(files),
            records=tuple(records),
            failed_runs=tuple(store.failed_runs(conn, grant.id)),
        )
    )
    texts: dict[str, str] = {}
    for f in files:
        if f.media_type.startswith(_TEXT_TYPES):
            texts[f.id] = p.storage.get(f.storage_path).decode("utf-8", errors="replace")
    history = tuple(
        StatusEntry(changed_at=row.changed_at, trigger=row.trigger, status=row.status)
        for row in store.grant_status_history(conn, grant.id, now)
    )
    return ReportInputs(
        grant=grant,
        now=now,
        preparer=preparer,
        charges=tuple(charges),
        files=tuple(files),
        records=tuple(records),
        checks=output,
        history=history,
        terms=_terms_in_force(grant, RecordState(records, files), charges, files),
        sign_off=signing,
        file_texts=texts,
    )


def draft_report(p: Platform, conn: Conn, grant: Grant, now: datetime) -> bytes:
    """The current draft: the report as it would be signed now, with no sign-off on it."""
    return build_report(report_inputs(p, conn, grant, now, None))


def signed_report_maker(p: Platform, user_id: str):  # noqa: ANN201
    """What actions.add_sign_off calls under the grant's lock: the PDF with the sign-off on
    it, and the snapshot it stores (decision 0022)."""

    def make(
        conn: Conn, grant: Grant, now: datetime, note: str | None
    ) -> tuple[bytes, SignOffSnapshot]:
        signing = Signing(author_user_id=user_id, signed_at=now, note=note)
        pdf = build_report(report_inputs(p, conn, grant, now, signing))
        return pdf, snapshot_now(load_snapshot(p, conn, grant))

    return make
