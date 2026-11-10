"""The agent as the platform (#25, app/db/ports.py) calls it: run_agent(AgentInput).

The platform hands over the run, the grant, the charges, files and records visible at the run's
clock time, the thread for a thread run, a way to read a file, and the checks. The agent returns
the records and thread messages to save, a summary and its debug log, or raises to fail the run,
and nothing is saved.

The agent doesn't import the platform's module, so the input is read by its attribute names and
the result is a dataclass with the platform's field names, plus `other_open_questions` for the
thread gate (answer 3).

Charges (the main coordinator's ruling): a run started by a charge covers every charge on the
grant that arrived at the same moment and hasn't been handled yet, up to CHARGE_BATCH_SIZE. A
large upload is handled in batches, each its own run: a later run started by a charge that an
earlier batch already handled takes the next batch, or does nothing when none is left.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .adapter import TRIGGER_CHARGE, Author, Charge, OpenQuestion, Record, ThreadMessage
from .graph import run_once
from .inputs import CHARGE_BATCH_SIZE, RunFailed, RunInputs
from .model import ModelClient
from .no_tracing import check_no_tracing


@dataclass(frozen=True)
class AgentResult:
    """What a finished run saves, all together. Field for field the platform's AgentResult."""

    records: list[Record] = field(default_factory=list[Record])
    messages: list[ThreadMessage] = field(default_factory=list[ThreadMessage])
    summary: str | None = None
    log: bytes | None = None  # the run's debug log, JSON, for private storage (answer 5)
    # Open questions for the agent outside a thread run's charge or record (answer 3): the
    # platform queues an ordinary run for them.
    other_open_questions: list[OpenQuestion] = field(default_factory=list[OpenQuestion])


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


def charges_for_run(
    trigger_id: str,
    charges: Sequence[Charge],
    records: Sequence[Record],
    size: int = CHARGE_BATCH_SIZE,
) -> list[str]:
    """The charges a charge run covers: those that arrived with the trigger and aren't handled.

    A charge counts as handled once any record of the agent's names it, so a batch an earlier
    run saved isn't taken again. The triggering charge goes first when it's still unhandled.
    """
    trigger = next((c for c in charges if c.id == trigger_id), None)
    if trigger is None:
        return []
    handled = {r.charge_id for r in records if r.author == Author.AGENT and r.charge_id}
    together = [c for c in charges if c.arrived_at == trigger.arrived_at and c.id not in handled]
    together.sort(key=lambda c: c.id != trigger_id)
    return [c.id for c in together[:size]]


def _log_bytes(log: dict[str, Any]) -> bytes:
    return json.dumps(log, default=str).encode("utf-8")


def to_run_inputs(agent_input: Any) -> RunInputs:
    run = agent_input.run
    checks = agent_input.checks
    charge_ids: list[str] = []
    if run.trigger.kind == TRIGGER_CHARGE and run.trigger.id:
        charge_ids = charges_for_run(run.trigger.id, agent_input.charges, agent_input.records)
    return RunInputs(
        run_id=run.id,
        grant=agent_input.grant,
        now=run.clock_now,
        trigger=run.trigger,
        records=list(agent_input.records),
        charges=list(agent_input.charges),
        files=list(agent_input.files),
        read_file=agent_input.read_file,
        default_items=checks.default_items,
        run_checks=checks.run_checks,
        charge_ids=charge_ids,
        thread_messages=list(agent_input.thread),
        read_through_seq=run.read_through_seq,
    )


def run_agent(agent_input: Any, model: ModelClient | None = None) -> AgentResult:
    """One run, as the platform calls it. Raises AgentRunFailed to fail it.

    Raises TracingTurnedOn first, before anything else, when LangSmith tracing is turned on in
    the environment (issue #82).
    """
    check_no_tracing()
    inputs = to_run_inputs(agent_input)
    if inputs.trigger.kind == TRIGGER_CHARGE and not inputs.charge_ids:
        log = {"run_id": inputs.run_id, "outcome": "saved", "events": [{"event": "nothing_to_do"}]}
        return AgentResult(
            summary="These charges were already handled by an earlier run.", log=_log_bytes(log)
        )
    result = run_once(inputs, model)
    if isinstance(result, RunFailed):
        raise AgentRunFailed(result.error, result.retryable, _log_bytes(result.log))
    return AgentResult(
        records=result.records,
        messages=result.messages,
        summary=result.summary,
        log=_log_bytes(result.log),
        other_open_questions=result.other_open_questions,
    )
