"""One run's working state: the staging area, the label table, the documents sent, the log.

Writes are staged, never saved: each one goes through the contract's write check against the
database's records plus this run's staged ones, gets its ID when it's staged so later writes can
point at it, and is saved with the rest only if the whole run finishes (all or nothing).
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .adapter import (
    ChecksOutput,
    Record,
    RecordState,
    ThreadMessage,
    build_record,
    check_write,
    debug_log_path,
    record_waits,
    run_checks_on,
)
from .citations import LabelLine, SentDocument, SentImage
from .inputs import RunInputs
from .rulebook import Rulebook

# The same write problem this many times, and the tool result suggests a flag instead. An uncited
# value is accepted, marked uncited, on this repeat (answer 1).
REPEAT_LIMIT = 3


@dataclass
class Staged:
    record: Record
    waits: bool


@dataclass
class RunContext:
    inputs: RunInputs
    rulebook: Rulebook
    staged: list[Staged] = field(default_factory=list[Staged])
    messages_out: list[ThreadMessage] = field(default_factory=list[ThreadMessage])
    labels: dict[str, LabelLine] = field(default_factory=dict[str, LabelLine])
    documents: list[SentDocument] = field(default_factory=list[SentDocument])
    images: dict[str, SentImage] = field(default_factory=dict[str, SentImage])
    uncited_refusals: Counter[tuple[str, str]] = field(default_factory=Counter[tuple[str, str]])
    problem_counts: Counter[str] = field(default_factory=Counter[str])
    messages: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    summary: str | None = None
    turns: int = 0
    gate_returns: int = 0
    max_tokens_retried: bool = False
    label_note: str = ""  # labels refused this turn, for the next message to the model
    pending_finish_id: str | None = None
    pending_results: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    next: str = "model"
    failure: tuple[str, bool] | None = None  # (error, retryable)
    log: dict[str, Any] = field(default_factory=dict[str, Any])
    _checks: ChecksOutput | None = None

    @property
    def records(self) -> list[Record]:
        """The database's records followed by this run's staged ones."""
        return [*self.inputs.records, *(s.record for s in self.staged)]

    def state(self) -> RecordState:
        return RecordState(self.records, self.inputs.files)

    def checks(self) -> ChecksOutput:
        """The checks on the database plus this run's staged records, rerun after each write."""
        if self._checks is None:
            i = self.inputs
            self._checks = run_checks_on(i.run_checks, i.now, i.charges, i.files, self.records)
        return self._checks

    def stage(
        self, data: dict[str, Any], replaces_id: str | None = None
    ) -> tuple[Staged | None, list[str]]:
        """Run the write check on a new agent record and stage it, or return its problems."""
        i = self.inputs
        record, problems = build_record(
            id=i.new_id(),
            grant=i.grant,
            written_at=i.now,
            data=data,
            replaces_id=replaces_id,
            trigger=i.trigger,
            read_through_seq=i.read_through_seq,
        )
        if record is None:
            return None, problems
        problems = check_write(record, self.records, i.charges, i.files, i.default_items, i.trigger)
        if problems:
            return None, problems
        state = RecordState([*self.records, record], i.files)
        staged = Staged(record=record, waits=record_waits(state, record.id, i.trigger))
        self.staged.append(staged)
        self._checks = None
        return staged, []

    def note_problems(self, tool: str, problems: list[str]) -> str:
        """The write problems as one tool result, with a nudge toward a flag on the third repeat."""
        text = "Not saved. " + " ".join(p if p.endswith(".") else p + "." for p in problems)
        key = tool + "|" + "|".join(sorted(problems))
        self.problem_counts[key] += 1
        self.log_event("write_problem", tool=tool, problems=problems)
        if self.problem_counts[key] >= REPEAT_LIMIT:
            text += (
                " This is the same problem for the third time: if you can't fix it, flag the "
                "charge, record or file with what you found instead."
            )
        return text

    # The debug log (answer 5).

    def start_log(
        self, system: list[dict[str, Any]], tools: list[dict[str, Any]], model: str, effort: str
    ) -> None:
        i = self.inputs
        self.log = {
            "run_id": i.run_id,
            "grant_id": i.grant.id,
            "workspace_id": i.grant.workspace_id,
            "trigger": i.trigger.model_dump(mode="json"),
            "clock_now": i.now.isoformat(),
            "model": model,
            "effort": effort,
            "prompt_sha256": _sha(system[0]["text"]),
            "rulebook_sha256": _sha(self.rulebook.text),
            "tools_sha256": _sha(json.dumps(tools, sort_keys=True)),
            "events": [],
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        }

    def log_event(self, kind: str, **data: Any) -> None:
        self.log.setdefault("events", []).append({"event": kind, **_loggable(data)})

    def add_usage(self, usage: Any) -> None:
        totals = self.log.setdefault("usage", {})
        for name in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            totals[name] = totals.get(name, 0) + (getattr(usage, name, 0) or 0)

    @property
    def log_path(self) -> str:
        i = self.inputs
        return debug_log_path(i.grant.workspace_id, i.grant.id, i.run_id)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _loggable(value: Any) -> Any:
    """JSON for the log, with file contents replaced by their size and fingerprint."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():  # pyright: ignore[reportUnknownVariableType]
            if k == "data" and isinstance(v, str):  # a file's contents never go in the log
                out[k] = {"omitted_bytes": len(v), "sha256": _sha(v)}
            else:
                out[str(k)] = _loggable(v)  # pyright: ignore[reportUnknownArgumentType]
        return out
    if isinstance(value, list | tuple):
        return [_loggable(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
