"""What a run is handed, and what it gives back, in the agent's own terms.

`run_once(inputs)` in graph.py takes these. The platform calls `run_agent` in platform.py, which
builds them from its AgentInput. The agent never touches the database.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .adapter import (
    Charge,
    DefaultItems,
    EvidenceFile,
    Grant,
    OpenQuestion,
    Record,
    RunChecks,
    ThreadMessage,
    Trigger,
)
from .model import ModelClient

# Charges that arrive together on one grant are handled in one run, or in batches of this many on
# a large upload, each batch its own run saved on its own (answer 8, and the coordinator's
# ruling; see platform.charges_for_run). The size is provisional.
CHARGE_BATCH_SIZE = 25


# Finds the IDs of the bills on file that look like the same one as a new bill, strongest first.
# The checks own the search (app.checks.duplicates.likely_duplicates, the default); a run can
# pass its own with the same signature.
LikelyDuplicates = Callable[[Record, Sequence[Record], Sequence[EvidenceFile]], list[str]]


@dataclass
class RunInputs:
    """Everything one run works from. Records, charges and files are those visible at `now`."""

    run_id: str
    grant: Grant
    now: datetime  # the workspace clock's "now": every record the run writes carries it
    trigger: Trigger
    records: Sequence[Record]  # every record in the workspace, in the order written
    charges: Sequence[Charge]
    files: Sequence[EvidenceFile]
    read_file: Callable[[EvidenceFile], bytes]  # the stored original
    default_items: DefaultItems  # W2's default checklist items
    run_checks: RunChecks  # W2's checks
    # For a charge run: every charge in the batch (answer 8). The trigger names the first.
    charge_ids: Sequence[str] = ()
    # Thread messages on the grant, oldest first. For a thread run, the trigger names the message.
    thread_messages: Sequence[ThreadMessage] = ()
    funder: str = "NSF"
    likely_duplicates: LikelyDuplicates | None = None
    # The model the second look on photos and scans calls; None uses the run's own model.
    second_look: ModelClient | None = None
    new_id: Callable[[], str] = field(default_factory=lambda: lambda: f"rec-{uuid.uuid4()}")
    # The run's read point (AgentRun.read_through_seq, call 40): every record it
    # writes carries it, and the write check refuses an agent record without one.
    read_through_seq: int | None = None
    # A sample grant (issue 165, point 4): a live email's Date header is read as the grant's
    # now when it arrived. to_run_inputs sets it when the grant has a clock_now.
    channel_times_from_grant_now: bool = False


class AgentRunFailed(Exception):
    """The run failed and saves nothing.

    `retryable` says whether trying again could help (a rate limit, an overload, a network
    error); a refusal, a run that went on too long, or a write that no longer passes is not.
    After the last retry the platform records the run as failed, and the checks raise a problem
    on the file or charge that triggered it (answer 7). `log` is the debug log, kept even then.
    """

    def __init__(self, error: str, retryable: bool, log: bytes):
        super().__init__(error)
        self.error = error
        self.retryable = retryable
        self.log = log


@dataclass
class RunSaved:
    """A run that finished: everything to save together, in order, in one transaction."""

    records: list[Record]
    messages: list[ThreadMessage]
    summary: str
    # Open questions for the agent that a thread run's gate left alone (answer 3). W4 queues an
    # ordinary run for them.
    other_open_questions: list[OpenQuestion]
    log: dict[str, Any]  # the run's debug log, for private storage at log_path (answer 5)
    log_path: str


@dataclass
class RunFailed:
    """A run that saved nothing.

    `retryable` says whether trying again could help (a rate limit, an overload, a network
    error). A run that fails for good is recorded as a failed AgentRun, and the checks raise a
    problem on the file or charge that triggered it (answer 7). How many retries: W4 with W1.
    """

    error: str
    retryable: bool
    trigger: Trigger
    log: dict[str, Any]
    log_path: str


RunResult = RunSaved | RunFailed
