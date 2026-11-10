"""build_report: one grant's evidence report as PDF bytes.

The draft route (GET /grants/{grant_id}/report) and the sign-off both call it,
at the workspace's "now". Same inputs, same bytes, so a stored copy's checksum
can be checked against a rebuild from the same inputs.
"""

from .content import report_view
from .inputs import ReportInputs
from .pdf import render


def build_report(inputs: ReportInputs) -> bytes:
    """The evidence report (decision 0022). A draft when inputs.sign_off is None."""
    p = inputs.preparer
    return render(report_view(inputs), inputs.now, p.name or p.email)
