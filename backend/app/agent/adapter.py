"""The agent's one seam with the contract code (issue #14), which is still settling.

Everything the agent needs from app.contracts goes through this module, so a change in the
contract models touches only this file. Two pieces are stand-ins until the contracts settle them:

- An uncited value. The coordinator's answer 1: after the repeat limit the write tool accepts a
  value with no citation, marked uncited, and it's saved as unconfirmed. The contract's Record
  still refuses an agent value with no citation, so `uncited_value` builds the value the way the
  contract is expected to take it, and today the write check refuses it.
- The debug log's name. Answer 5: one log per run in private storage, referenced from the run's
  `log_path`. The contract has the field but no naming rule yet, so `debug_log_path` is the
  agent's proposal for the contracts builder.
"""

from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from app.contracts.charges import Charge
from app.contracts.checks import ChecksInput, ChecksOutput, OpenQuestion, RunChecks
from app.contracts.evidence import EvidenceFile
from app.contracts.records import (
    FACT_KINDS,
    TERM_KINDS,
    Answer,
    Author,
    Bill,
    BudgetAssignment,
    BudgetCategory,
    Citation,
    Cited,
    Decision,
    DefaultItems,
    Judgment,
    Link,
    PeriodOfPerformance,
    Question,
    Record,
    RecordKind,
    cited_values,
)
from app.contracts.rules import RecordState, check_new_record
from app.contracts.runs import AgentRun, Trigger, TriggerKind
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant

__all__ = [
    "Bill",
    "BudgetAssignment",
    "Link",
    "PeriodOfPerformance",
    "FACT_KINDS",
    "TERM_KINDS",
    "AgentRun",
    "Answer",
    "Author",
    "BudgetCategory",
    "Charge",
    "ChecksInput",
    "ChecksOutput",
    "Citation",
    "Cited",
    "Decision",
    "DefaultItems",
    "EvidenceFile",
    "Grant",
    "Judgment",
    "OpenQuestion",
    "Question",
    "Record",
    "RecordKind",
    "RecordState",
    "RunChecks",
    "ThreadMessage",
    "Trigger",
    "TriggerKind",
    "build_record",
    "check_write",
    "cited_values",
    "debug_log_path",
    "uncited_value",
]

# The private Supabase Storage bucket for agent debug logs. Provisional, for #14 and W4.
DEBUG_LOG_BUCKET = "agent-logs"


def debug_log_path(workspace_id: str, grant_id: str, run_id: str) -> str:
    """Where a run's debug log lives inside DEBUG_LOG_BUCKET. Provisional, for #14 to settle."""
    return f"{workspace_id}/{grant_id}/{run_id}.json"


def uncited_value(value: object, text: str) -> dict[str, Any]:
    """A value the API returned with no citation, accepted after the repeat limit.

    It carries no citation, so it's unconfirmed. The contract's marker for "uncited" isn't
    settled yet, and today's Record refuses it, which the write tool reports back.
    """
    return {"value": value, "text": text}


def _plain(error: ValidationError) -> list[str]:
    problems: list[str] = []
    for e in error.errors():
        where = ".".join(str(p) for p in e["loc"] if not str(p).startswith("function-after"))
        message = str(e["msg"]).removeprefix("Value error, ")
        problems.append(f"{where}: {message}" if where else message)
    return problems


def build_record(
    *,
    id: str,
    grant: Grant,
    written_at: Any,
    data: dict[str, Any],
    replaces_id: str | None = None,
) -> tuple[Record | None, list[str]]:
    """The agent's record, or the reasons the contract models refuse it, as plain sentences."""
    try:
        record = Record.model_validate(
            {
                "id": id,
                "workspace_id": grant.workspace_id,
                "grant_id": grant.id,
                "author": Author.AGENT,
                "written_at": written_at,
                "replaces_id": replaces_id,
                "data": data,
            }
        )
    except ValidationError as error:
        return None, _plain(error)
    return record, []


def check_write(
    new: Record,
    records: Sequence[Record],
    charges: Sequence[Charge],
    files: Sequence[EvidenceFile],
    default_items: DefaultItems,
) -> list[str]:
    """The contract's write check, run on every write the agent stages."""
    return check_new_record(new, records, charges, files, default_items=default_items)


def citation_of(record: Record, field: str) -> Citation | None:
    """The citation on one of a record's cited values, by its path, for example "total"."""
    for path, value in cited_values(record.data):
        if path == field:
            return value.citation
    return None


def run_checks_on(
    run_checks: RunChecks,
    now: Any,
    charges: Sequence[Charge],
    files: Sequence[EvidenceFile],
    records: Sequence[Record],
) -> ChecksOutput:
    return run_checks(
        ChecksInput(now=now, charges=list(charges), files=list(files), records=list(records))
    )


def agent_questions(output: ChecksOutput) -> list[OpenQuestion]:
    """The open questions waiting for the agent."""
    return [q for q in output.questions if q.answer_by == Author.AGENT]


QUESTION_TEXT = {
    Question.ALLOWABLE: "Is this cost necessary and reasonable, and is it for this project?",
    Question.COVERS: "Does this approval cover this charge?",
    Question.UNUSUAL_TERM: "Does this term change anything for this charge?",
}

TRIGGER_FILE = TriggerKind.FILE
TRIGGER_CHARGE = TriggerKind.CHARGE
TRIGGER_RECORD = TriggerKind.RECORD
TRIGGER_THREAD = TriggerKind.THREAD_MESSAGE
TRIGGER_CLOCK = TriggerKind.CLOCK


def _record_models(*names: str) -> dict[str, Any]:
    from app.contracts import records

    return {
        getattr(records, n).model_fields["kind"].default.value: getattr(records, n) for n in names
    }


# The record kinds the agent writes with write_term and write_fact, by kind.
TERM_RECORD_MODELS = _record_models(
    "PeriodOfPerformance", "BudgetLine", "Person", "ApprovalRule", "Rate", "Notice", "OtherTerm"
)
FACT_RECORD_MODELS = _record_models("Bill", "Approval", "Note")
