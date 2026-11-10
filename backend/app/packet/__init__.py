"""The evidence report: a PDF per grant, built from its records and the checks' output.

    from app.packet import ReportInputs, build_report

    pdf_bytes = build_report(ReportInputs(...))

Decision 0022 sets the seven sections and their order. The report only
selects, groups, counts and formats: buckets, reasons and status text come from
the checks. The stand-ins for what the second contract change (#39) adds are in
pending.py.
"""

from .inputs import ReportInputs
from .pending import BudgetFigure, ChargeLedgerState, HeldMessage, TermsInForce
from .report import build_report

__all__ = [
    "BudgetFigure",
    "ChargeLedgerState",
    "HeldMessage",
    "ReportInputs",
    "TermsInForce",
    "build_report",
]
