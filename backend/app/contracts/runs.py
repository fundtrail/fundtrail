"""Agent runs (docs/contracts.md section 9).

A run is one background job. It's queued each time a charge or an evidence
file arrives, each time one of the accountant's records leaves a question open
for the agent, each time the accountant writes in a thread, and once per grant
when the closeout window opens. Everything a run wrote is saved together at the
end, so a run that fails saves nothing. Runs for one grant go one at a time.
"""

from enum import StrEnum

from pydantic import model_validator

from .base import Id, Model, UtcDatetime


class TriggerKind(StrEnum):
    RECORD = "record"  # a record was written
    CHARGE = "charge"  # a ledger line arrived
    FILE = "file"  # an evidence file arrived
    THREAD_MESSAGE = "thread_message"  # a message in a review thread
    CLOCK = "clock"  # only time passed, for example into the closeout window


class Trigger(Model):
    kind: TriggerKind
    id: Id | None = None  # the record, charge, file or message; None for the clock

    @model_validator(mode="after")
    def _id(self):
        if (self.kind == TriggerKind.CLOCK) != (self.id is None):
            raise ValueError(
                "a trigger names its record, charge, file or message, and only the clock has no ID"
            )
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
