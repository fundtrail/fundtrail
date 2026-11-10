"""The evidence report: a PDF per grant, built from its records and the checks' output.

    from app.packet import ReportInputs, build_report

    pdf_bytes = build_report(ReportInputs(...))

Decision 0022 sets the seven sections and their order. The report only
selects, groups, counts and formats: buckets, reasons and status text come from
the checks. The terms in force and budget figures the checks don't report yet are
stand-ins in pending.py.
"""

from .inputs import ReportInputs, Signing
from .pending import BudgetFigure, TermsInForce
from .report import build_report

__all__ = [
    "BudgetFigure",
    "ReportInputs",
    "Signing",
    "TermsInForce",
    "build_report",
]
