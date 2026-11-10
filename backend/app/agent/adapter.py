"""The agent's one seam with the contract code (issue #14), which is still settling.

Everything the agent needs from app.contracts goes through this module, so a change in the
contract models touches only this file. One piece is a stand-in until the contracts settle it:

- The debug log's name. Answer 5: one log per run in private storage, referenced from the run's
  `log_path`. The contract has the field but no naming rule yet, so `debug_log_path` is the
  agent's proposal for the contracts builder.
"""

from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from app.checks.duplicates import likely_duplicates
from app.checks.rules_match import rule_category
from app.checks.view import GrantView
from app.contracts.charges import Charge
from app.contracts.checks import ChecksInput, ChecksOutput, OpenQuestion, RunChecks
from app.contracts.evidence import EvidenceFile
from app.contracts.records import (
    FACT_KINDS,
    TERM_KINDS,
    Answer,
    ApprovalScope,
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
    "likely_duplicates",
    "ApprovalScope",
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
    """A value the API returned with no citation, accepted after the repeat limit (answer 1).

    The contract marks it uncited, and it stays unconfirmed until the accountant confirms the
    record it's in or types the value.
    """
    return {"value": value, "text": text, "uncited": True}


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
    trigger: Trigger | None = None,
    read_through_seq: int | None = None,
) -> tuple[Record | None, list[str]]:
    """The agent's record, or the reasons the contract models refuse it, as plain sentences.

    In a run a thread message started, the record names that message, so it waits for the
    accountant whatever its kind (the contract reads it from there). The record carries
    its run's read point (call 40).
    """
    thread = trigger is not None and trigger.kind == TriggerKind.THREAD_MESSAGE
    try:
        record = Record.model_validate(
            {
                "id": id,
                "workspace_id": grant.workspace_id,
                "grant_id": grant.id,
                "author": Author.AGENT,
                "written_at": written_at,
                "replaces_id": replaces_id,
                "thread_message_id": trigger.id if thread and trigger is not None else None,
                "read_through_seq": read_through_seq,
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
    trigger: Trigger,
) -> list[str]:
    """The contract's write check, run on every write the agent stages, with the run's trigger."""
    return check_new_record(
        new, records, charges, files, default_items=default_items, trigger=trigger
    )


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
        ChecksInput(now=now, charges=tuple(charges), files=tuple(files), records=tuple(records))
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
TRIGGER_OPEN_QUESTION = TriggerKind.OPEN_QUESTION


def record_waits(state: RecordState, record_id: str, trigger: Trigger) -> bool:
    """Whether the agent's new record waits for the accountant, as the contract decides it.

    Every record a run started by a thread message writes waits, whatever its kind: the record
    names the message (`thread_message_id`), and the contract reads it from there.
    """
    del trigger  # the record carries it
    return state.waits(record_id)


def char_citation(
    file_id: str,
    passage: str,
    start: int,
    end: int,
    match: str,
    lines: list[tuple[int, int]],
) -> dict[str, Any]:
    """A plain-text citation, highlighted on the lines where its value stands on its own.

    The passage and its location stay exactly what the API returned; `lines` become the
    highlight, one character range per line inside the passage (#39). With no such line, the
    citation has no highlight and the viewer shows the whole passage.
    """
    location = {"type": "char_location", "start_char_index": start, "end_char_index": end}
    citation: dict[str, Any] = {
        "file_id": file_id,
        "passage": passage,
        "location": location,
        "match": match,
    }
    if lines:
        citation["highlight"] = [{"start_char_index": s, "end_char_index": e} for s, e in lines]
    return citation


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


def applies_to_is_matchable(
    applies_to: str, records: Sequence[Record], files: Sequence[EvidenceFile], grant_id: str
) -> bool:
    """Whether code can match an approval rule's applies_to to one budget category.

    Asks the checks' own matcher (app.checks.rules_match.rule_category) about a stand-in rule
    with this applies_to, so only the budget lines in force or waiting for their confirmation
    count, the same as when the checks apply the rule. Lines staged in this run count.
    """
    probe = Record.model_validate(
        {
            "id": "applies-to-probe",
            "workspace_id": "probe",
            "grant_id": grant_id,
            "author": Author.USER,
            "author_user_id": "probe",
            "written_at": "2000-01-01T00:00:00+00:00",
            "data": {
                "kind": "approval_rule",
                "dated": {"value": "2000-01-01"},
                "applies_to": {"value": applies_to},
                "approver": {"value": "probe"},
            },
        }
    )
    view = GrantView(grant_id, RecordState(records, files), [], files)
    return rule_category(view, probe) is not None
