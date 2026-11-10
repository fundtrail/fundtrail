"""A finding: one reason or problem as the checks work it out, before acceptances and flagging."""

from dataclasses import dataclass, field
from datetime import date

from app.contracts.checks import Bucket


@dataclass
class Finding:
    check: str  # the check's stable ID
    problem: str  # names the problem within the check, stable from run to run
    bucket: Bucket
    text: str  # built by code
    record_ids: list[str] = field(default_factory=list[str])
    expected_by: date | None = None  # for a missing item: when it's expected
    flag_now: bool = False  # a missing approval goes on the problem list right away
    # The reason rests only on a term whose own problem (waiting, disagreeing, or a
    # rule code can't place) stands for it on the problem list, so it doesn't put
    # the charge there as its own row.
    shown_on_term: bool = False
    dispute_id: str | None = None  # the agent's dispute of it, while it waits
    # Issue 83: the award limit's over_limit problem carries the amount over.
    amount_cents: int | None = None

    @property
    def failing(self) -> bool:
        return self.bucket != Bucket.EVIDENCE_COMPLETE


def passed(check: str, text: str, record_ids: list[str] | None = None) -> Finding:
    return Finding(check, "pass", Bucket.EVIDENCE_COMPLETE, text, list(record_ids or []))


# The checks' stable IDs. The first five are the numbered checks about a charge
# (check 6, reversals, has no ID of its own: the checklist reports its items).
PERIOD = "period_of_performance"  # 1
CHECKLIST = "checklist"  # 2
APPROVAL = "approval"  # 3
VALUES = "values_confirmed"  # 5
BUDGET = "budget"  # 4, on the grant
# Reasons on a charge that belong to none of the numbered checks.
BUDGET_LINE = "budget_line"  # the ledger account's category against the assigned line
SUGGESTION = "suggestion"  # one of the agent's suggestions waits for the accountant
AGENT_RUN = "agent_run"  # an agent run failed for good
# Problems on records, files and the grant.
TERMS = "terms"
BILL = "bill"
SAME_FILE = "same_file"
NOTICE = "notice"
GRANT_TERMS = "grant_terms"
SKIPPED_FILES = "skipped_files"
