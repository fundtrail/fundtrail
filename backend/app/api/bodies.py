"""A response body the API needs that the contracts don't have yet.

GET /grants/{grant_id}/runs leaves out the debug log's path, which is never shown to the
accountant. RunRow can move into `app/contracts/api.py` under the same name.
"""

from app.contracts.base import Id, Model, UtcDatetime
from app.contracts.runs import RunStatus, Trigger


class RunRow(Model):
    """One row of GET /grants/{grant_id}/runs: the run as section 9 describes it, without the
    debug log's path, which is never shown to the accountant."""

    id: Id
    workspace_id: Id
    grant_id: Id
    trigger: Trigger
    status: RunStatus
    clock_now: UtcDatetime
    queued_at: UtcDatetime
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    summary: str | None = None
    error: str | None = None
    # A run a thread message started: the thread's charge or record.
    thread_charge_id: Id | None = None
    thread_record_id: Id | None = None
