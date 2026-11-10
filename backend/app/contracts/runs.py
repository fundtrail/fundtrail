"""Agent runs (docs/contracts.md section 9).

A run is one background job. It's queued each time a charge or an evidence
file arrives, each time one of the accountant's records leaves a question open
for the agent, each time the accountant writes in a thread, and once per grant
when the closeout window opens. Everything a run wrote is saved together at the
end, so a run that fails saves nothing. Runs for one grant go one at a time.

What a charge-triggered run covers: every charge on its grant that arrived at the
same moment and hasn't been handled yet, in batches of at most CHARGE_BATCH. Code
queues one run per batch, not one per charge, and the run's trigger names the
batch's first charge. See batch_for.
"""

from collections.abc import Collection, Sequence
from datetime import datetime
from enum import StrEnum

from pydantic import model_validator

from .base import Id, Model, UtcDatetime
from .charges import Charge

# A large upload is cut into batches of at most this many charges, each its own run.
CHARGE_BATCH = 25


class TriggerKind(StrEnum):
    RECORD = "record"  # a record was written
    CHARGE = "charge"  # a ledger line arrived
    FILE = "file"  # an evidence file arrived
    THREAD_MESSAGE = "thread_message"  # a message in a review thread
    # A question left open for the agent by a thread run: the run the platform
    # queues after it. The ID is the charge or record whose question is open. A
    # run started by one of the accountant's records stays a `record` trigger.
    OPEN_QUESTION = "open_question"
    CLOCK = "clock"  # only time passed, for example into the closeout window


class Trigger(Model):
    kind: TriggerKind
    id: Id | None = None  # the record, charge, file or message; None for the clock

    @model_validator(mode="after")
    def _id(self):
        if (self.kind == TriggerKind.CLOCK) != (self.id is None):
            raise ValueError("a trigger names what started it, and only the clock has no ID")
        return self


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class AgentRun(Model):
    id: Id
    workspace_id: Id
    grant_id: Id
    # The charge or file that arrived, the accountant's record that left a question
    # open, the thread message, or the clock for the closeout review.
    trigger: Trigger
    status: RunStatus
    clock_now: UtcDatetime  # the clock's "now" the run works at; its records carry it
    queued_at: UtcDatetime  # real time, like the two below
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    summary: str | None = None  # a short line on what it did
    error: str | None = None
    # The run's debug log: one file in private storage. Never shown to the
    # accountant, and removed by a workspace reset.
    log_path: str | None = None
    # A run started by a thread message: the thread's subject, exactly one of the
    # two, so a run that fails for good can be placed on its charge or record.
    # Neither is set for any other trigger.
    thread_charge_id: Id | None = None
    thread_record_id: Id | None = None

    @model_validator(mode="after")
    def _thread_subject(self):
        subjects = (self.thread_charge_id is not None) + (self.thread_record_id is not None)
        if self.trigger.kind == TriggerKind.THREAD_MESSAGE:
            if subjects != 1:
                raise ValueError("a run started in a thread names the thread's charge or record")
        elif subjects:
            raise ValueError("only a run started in a thread names a thread's subject")
        return self


def charge_batches(charges: Sequence[Charge], handled: Collection[str] = ()) -> list[list[Charge]]:
    """The charges not yet handled, grouped by grant and arrival moment, each group in
    ledger line ID order and cut into batches of CHARGE_BATCH.

    `handled` holds the IDs of charges an earlier run already covered. A batch's run
    is triggered by its first charge.
    """
    groups: dict[tuple[str, datetime], list[Charge]] = {}
    for c in charges:
        if c.id not in handled:
            groups.setdefault((c.grant_id, c.arrived_at), []).append(c)
    batches: list[list[Charge]] = []
    for key in sorted(groups, key=lambda k: (k[1], k[0])):
        group = sorted(groups[key], key=lambda c: (c.ledger_line_id, c.id))
        batches += [group[i : i + CHARGE_BATCH] for i in range(0, len(group), CHARGE_BATCH)]
    return batches


def batch_for(
    trigger_charge_id: str, charges: Sequence[Charge], handled: Collection[str] = ()
) -> list[Charge]:
    """The charges a run triggered by `trigger_charge_id` covers.

    Every charge on the trigger's grant that arrived at the same moment and isn't in
    `handled`, in the trigger's batch. Empty when the trigger isn't among `charges`
    or was handled already.
    """
    trigger = next((c for c in charges if c.id == trigger_charge_id), None)
    if trigger is None or trigger.id in handled:
        return []
    same = [
        c for c in charges if c.grant_id == trigger.grant_id and c.arrived_at == trigger.arrived_at
    ]
    for batch in charge_batches(same, handled):
        if any(c.id == trigger_charge_id for c in batch):
            return batch
    return []
