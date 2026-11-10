"""The report's inputs for the sample grant (docs/contracts.md section 15), written by hand.

The checks (#24) aren't built yet, so the checks' output here is hand-written
to match the expected buckets in section 15. The reason texts and check IDs
are stand-ins for code's own.
"""

from datetime import UTC, date, datetime
from typing import Any

import pypdfium2 as pdfium

from app.contracts.checks import (
    Bucket,
    ChargeStatus,
    ChecklistEntry,
    ChecksOutput,
    ItemSource,
    Problem,
    Reason,
    RecordStatus,
    StatusEntry,
)
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import Period, Record
from app.contracts.runs import Trigger, TriggerKind
from app.packet import BudgetFigure, ReportInputs, TermsInForce
from app.quotes import PDFIUM_LOCK

SAMPLE = load_sample_grant()
USER = SAMPLE.user
APRIL_9 = datetime(2026, 4, 9, 17, tzinfo=UTC)  # the extension arrived, not yet confirmed
APRIL_10 = datetime(2026, 4, 10, 17, tzinfo=UTC)  # the extension confirmed


def pdf_pages(data: bytes) -> list[str]:
    """Each page's text, read back with pypdfium2."""
    with PDFIUM_LOCK:
        pdf = pdfium.PdfDocument(data)
        try:
            pages: list[str] = []
            for i in range(len(pdf)):
                textpage = pdf[i].get_textpage()
                pages.append(textpage.get_text_range())
            return pages
        finally:
            pdf.close()


def flat(text: str) -> str:
    """Whitespace as single spaces, so wrapped lines read as one."""
    return " ".join(text.replace("\xa0", " ").split())


def _pass(check: str, text: str) -> Reason:
    return Reason(check=check, problem="passes", text=text, bucket=Bucket.EVIDENCE_COMPLETE)


def _l1001() -> ChargeStatus:
    return ChargeStatus(
        grant_id="grant-sample",
        charge_id="chg-l-1001",
        bucket=Bucket.EVIDENCE_COMPLETE,
        reasons=(
            _pass("period_of_performance", "Nov 12, 2025 is inside the period in force."),
            _pass("checklist", "Every checklist item is filled, and the amounts add up."),
            _pass("allowable", "The agent's answer supports the cost."),
        ),
        checklist=(
            ChecklistEntry(
                default_item="bill",
                added_by=ItemSource.DEFAULT,
                needed="A bill that adds up to the charge",
                amount_cents=124000,
                filled=True,
                link_ids=("rec-link-l-1001",),
            ),
        ),
        flagged=False,
    )


def _l1002(conflict: bool) -> ChargeStatus:
    period = (
        Reason(
            check="period_of_performance",
            problem="after_end_date",
            text="Feb 20, 2026 is after the end date in force, Jan 31, 2026.",
            bucket=Bucket.POSSIBLE_CONFLICT,
            record_ids=("rec-period",),
        )
        if conflict
        else _pass("period_of_performance", "Feb 20, 2026 is inside the period in force.")
    )
    return ChargeStatus(
        grant_id="grant-sample",
        charge_id="chg-l-1002",
        bucket=Bucket.POSSIBLE_CONFLICT if conflict else Bucket.EVIDENCE_COMPLETE,
        reasons=(
            period,
            _pass("checklist", "Every checklist item is filled, and the amounts add up."),
            _pass("allowable", "The agent's answer supports the cost."),
        ),
        checklist=(
            ChecklistEntry(
                default_item="usage_statement",
                added_by=ItemSource.DEFAULT,
                needed="The facility's usage statement",
                amount_cents=218000,
                filled=True,
                link_ids=("rec-link-l-1002",),
            ),
        ),
        flagged=conflict,
    )


def _history() -> tuple[StatusEntry, ...]:
    def at(y: int, m: int, d: int) -> datetime:
        return datetime(y, m, d, tzinfo=UTC)

    return (
        StatusEntry(
            changed_at=at(2025, 11, 14),
            trigger=Trigger(kind=TriggerKind.CHARGE, id="chg-l-1001"),
            status=_l1001(),
        ),
        StatusEntry(
            changed_at=at(2026, 2, 24),
            trigger=Trigger(kind=TriggerKind.CHARGE, id="chg-l-1002"),
            status=_l1002(conflict=True),
        ),
        StatusEntry(
            changed_at=at(2026, 4, 10),
            trigger=Trigger(kind=TriggerKind.RECORD, id="rec-confirm-extension"),
            status=_l1002(conflict=False),
        ),
    )


OTHER_TERMS = (
    "rec-person-pi",
    "rec-person-program-officer",
    "rec-person-grants-officer",
    "rec-approval-rule",
)


def _terms(confirmed_extension: bool) -> TermsInForce:
    return TermsInForce(
        period=Period(
            start=date(2023, 2, 1),
            end=date(2027, 1, 31) if confirmed_extension else date(2026, 1, 31),
        ),
        period_ids=("rec-period", "rec-period-extension")
        if confirmed_extension
        else ("rec-period",),
        limit_notice_id="rec-notice-000",
        spent_cents=342000,
        budget=(
            BudgetFigure(record_id="rec-budget-participant-support", spent_cents=0, over=False),
            BudgetFigure(record_id="rec-budget-other-direct-costs", spent_cents=342000, over=False),
            BudgetFigure(
                record_id="rec-budget-materials-and-supplies", spent_cents=124000, over=False
            ),
            BudgetFigure(record_id="rec-budget-other", spent_cents=218000, over=False),
        ),
        other_term_ids=OTHER_TERMS,
    )


def sample_inputs(now: datetime = APRIL_10, **changes: Any) -> ReportInputs:
    """The sample grant's report inputs at April 10 (everything ready) or April 9 (L-1002 open)."""
    confirmed = now >= APRIL_10
    records = tuple(r for r in SAMPLE.records if r.written_at <= now)
    files = tuple(f for f in SAMPLE.files if f.arrived_at <= now)
    checks = ChecksOutput(
        charges=(_l1001(), _l1002(conflict=not confirmed)),
        records=()
        if confirmed
        else (
            RecordStatus(
                grant_id="grant-sample",
                record_id="rec-period-extension",
                problems=(
                    Problem(
                        check="term_waiting",
                        problem="waiting",
                        text="A term read from extension_notice.txt waits to be confirmed.",
                        record_ids=("rec-period-extension",),
                    ),
                ),
                flagged=True,
            ),
        ),
        grants=(),
        questions=(),
        notes=(),
    )
    fields: dict[str, Any] = {
        "grant": SAMPLE.grant,
        "now": now,
        "preparer": USER,
        "charges": SAMPLE.charges,
        "files": files,
        "records": records,
        "checks": checks,
        "history": tuple(e for e in _history() if e.changed_at <= now),
        "terms": _terms(confirmed),
        "file_texts": {f.id: SAMPLE.document(f.id) for f in files},
    }
    fields.update(changes)
    return ReportInputs(**fields)


def user_record(id: str, now: datetime, data: dict[str, Any], **extra: Any) -> Record:
    return Record.model_validate(
        {
            "id": id,
            "workspace_id": "ws-sample",
            "grant_id": "grant-sample",
            "author": "user",
            "author_user_id": USER.id,
            "written_at": now,
            "data": data,
            **extra,
        }
    )
