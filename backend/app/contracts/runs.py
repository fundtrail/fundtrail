"""Agent runs: one background job each time a charge or a source arrives, and one
per grant as closeout nears, to review all its links.

The agent works in a loop of actions: it looks at anything on the grant, opens
files, and writes records. Every write is checked with check_new_record as it
happens, and problems go back to the agent. A run can't finish while code has
an open question for the agent. Everything the run wrote is saved together at
the end, so a run that fails saves nothing. Runs for one grant go one at a time.
"""

from enum import StrEnum

from pydantic import AwareDatetime

from .base import Model
from .checks import Trigger


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class AgentRun(Model):
    id: str
    workspace_id: str
    grant_id: str
    trigger: Trigger  # the charge or file that arrived, or the clock for the closeout review
    status: RunStatus
    clock_now: AwareDatetime  # the workspace clock's "now" the run works at; its records carry it
    queued_at: AwareDatetime  # real time, like the timestamps below
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    summary: str | None = None  # one or two lines from the agent on what it did
    error: str | None = None
