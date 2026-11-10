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


def _stand_in_likely_duplicates(new: Record, records: Sequence[Record]) -> list[Record]:
    """Bills on file that look like the same one as a new bill: the same document number, or the
    same total and vendor. A stand-in until the checks' own search lands."""

    def key(r: Record, name: str) -> str | None:
        v = getattr(r.data, name, None)
        return None if v is None else str(v.value).lower()

    found: list[Record] = []
    for r in records:
        if r.id == new.id or r.kind != RecordKind.BILL:
            continue
        number = key(new, "document_number")
        vendor = key(new, "vendor")
        same_number = number is not None and number == key(r, "document_number")
        same_total = (
            vendor is not None
            and vendor == key(r, "vendor")
            and key(new, "total") == key(r, "total")
        )
        if same_number or same_total:
            found.append(r)
    return found


# The search for likely duplicate bills belongs to the checks (W2), as a pure function in
# backend/app/checks/. Once it lands, this one line becomes its import, for example
# `from app.checks import likely_duplicates`.
likely_duplicates = _stand_in_likely_duplicates


def record_waits(state: RecordState, record_id: str, trigger: Trigger) -> bool:
    """Whether the agent's new record waits for the accountant.

    The main coordinator's ruling: every record a run started by a thread message writes waits,
    whatever its kind. The contract enforces it from the run's trigger once #39 lands; until
    then this tells the model the same thing, and the saved record follows the contract.
    """
    return trigger.kind == TriggerKind.THREAD_MESSAGE or state.waits(record_id)


def char_citation(
    file_id: str,
    passage: str,
    start: int,
    end: int,
    match: str,
    lines: list[tuple[int, int]],
) -> dict[str, Any]:
    """A plain-text citation, highlighted on the lines where its value stands on its own.

    `start`, `end` and `passage` are the API's one cited range; `lines` are the character ranges
    to highlight inside it. #39 adds several ranges to a text citation's highlight. Until it
    lands, a citation holds one range, so it runs from the first such line to the last, and
    the passage is that range's text.
    """
    location = {"type": "char_location", "start_char_index": start, "end_char_index": end}
    citation: dict[str, Any] = {
        "file_id": file_id,
        "passage": passage,
        "location": location,
        "match": match,
    }
    if lines:
        first, last = lines[0][0], lines[-1][1]
        offset = first - start
        citation["passage"] = passage[offset : offset + (last - first)]
        location["start_char_index"], location["end_char_index"] = first, last
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
