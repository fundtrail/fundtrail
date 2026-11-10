"""What a run is handed, and what it gives back.

The agent exposes one function, `run_agent(inputs)` in graph.py. W4 loads the inputs from the
database, calls it, and saves the result in one transaction (or records the failure). The agent
never touches the database.
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
from .citations import SecondLook

# Charges that arrive together on one grant are handled in one run, or in batches of this many on
# a large upload, each batch its own run saved on its own (answer 8). Provisional.
CHARGE_BATCH_SIZE = 25


def batch_charge_ids(charge_ids: Sequence[str], size: int = CHARGE_BATCH_SIZE) -> list[list[str]]:
    """Split charges that arrived together into the batches W4 queues as runs, in arrival order."""
    ids = list(charge_ids)
    return [ids[i : i + size] for i in range(0, len(ids), size)]


# Finds the bills on file that look like the same one as a new bill. W2 owns the search rule;
# until it exists, a default in tools.py matches on document number, or on total and vendor.
LikelyDuplicates = Callable[[Record, Sequence[Record]], list[Record]]


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
    second_look: SecondLook | None = None
    new_id: Callable[[], str] = field(default_factory=lambda: lambda: f"rec-{uuid.uuid4()}")


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
