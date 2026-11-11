"""API (application programming interface) bodies: docs/contracts.md section 12, and the
screen bodies agreed in issue 22.

W4 writes the routes in backend/app/api/, and the frontend generates its
TypeScript types from the OpenAPI schema they produce. Errors use FastAPI's
default {"detail": ...} body.

The bodies are the contract models and the checks' output as they are. A wrapper
exists only to put a record next to what code works out about it, such as whether
it counts or whether a value is confirmed: the server works those out with the
contract functions, and the screens never do. Every body carries its citations,
so the viewer needs no separate highlight endpoint.
"""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import Cents, Id, Model, Text, UtcDatetime
from .buckets import Bucket
from .charges import Charge
from .checks import (
    ChargeStatus,
    GrantNote,
    OpenQuestion,
    Problem,
    RecordStatus,
    StatusEntry,
)
from .evidence import EvidenceFile
from .mail import HeldMail
from .records import (
    AcceptedReason,
    Approval,
    ApprovalRule,
    Bill,
    BudgetAssignment,
    BudgetCategory,
    BudgetLine,
    ChecklistItem,
    ChecklistRemoval,
    CitedDate,
    Confirmation,
    Correction,
    Dispute,
    Duplicate,
    Judgment,
    Link,
    MailDecision,
    Note,
    Notice,
    OtherTerm,
    PeriodOfPerformance,
    Person,
    Rate,
    Record,
    RecordKind,
    Remainder,
    Retraction,
    Snooze,
)
from .runs import AgentRun
from .signoff import SignOffStateName, SnapshotChange
from .threads import ThreadMessage
from .workspaces import Grant, SampleChoice

# Workspaces and the clock.


class WorkspaceCreate(Model):
    """POST /workspaces"""

    name: Text


class ArrivalSource(StrEnum):
    LEDGER = "ledger"
    GMAIL = "gmail"
    DRIVE = "drive"
    UPLOAD = "upload"


# What code works out about a record, in one word or a few fields.


class RecordState(StrEnum):
    """What counts (docs/contracts.md section 1) in one word per record. Not rules.RecordState."""

    COUNTS = "counts"  # current and in effect
    WAITING = "waiting"  # the agent's record waiting for a confirmation
    REJECTED = "rejected"
    REPLACED = "replaced"  # a record that counts replaces it
    RETRACTED = "retracted"


class ValueHow(StrEnum):
    FOUND = "found"  # its citation was found in its file
    RECORD_CONFIRMED = "record_confirmed"  # the accountant confirmed the record it's in
    TYPED = "typed"  # the accountant typed it


class ValueState(Model):
    """Whether one value is confirmed, and how. Code works it out each time; nothing stores it."""

    path: Text  # as records.cited_values names it, for example "total" or "items[0].amount"
    confirmed: bool
    how: ValueHow | None = None  # None when it's unconfirmed
    confirmed_at: UtcDatetime | None = None  # the confirmation's or the typed record's clock time


class RecordView(Model):
    """One row of GET /grants/{grant_id}/records."""

    record: Record
    state: RecordState


# The grant list and the grant page.


class CloseoutDate(Model):
    """The next closeout date that follows from the end date in force."""

    date: date
    label: Text  # for example "Notice of Expiration", worded by the server


class ReadingProgress(Model):
    """How far the agent is through the files and ledger lines it has to read (ruling 71).

    Counts the current stretch of work: the files and ledger lines that the grant's
    queued and running runs cover, and those of runs that finished since the grant
    last had none queued or running. Read means its run finished. Enough for
    "Reading 3 of 8 files". A first version.
    """

    files_read: int = Field(ge=0)
    files_total: int = Field(ge=0)
    lines_read: int = Field(ge=0)  # ledger lines
    lines_total: int = Field(ge=0)

    @model_validator(mode="after")
    def _read_within_total(self):
        if self.files_read > self.files_total or self.lines_read > self.lines_total:
            raise ValueError("the agent can't have read more than it has to read")
        return self


class GrantSummary(Model):
    """One row of GET /workspaces/{workspace_id}/grants (issue 22, answer 7)."""

    grant: Grant
    end_date: date | None = None  # the end date in force; None while no period is confirmed
    charges_ready: int  # ready for closeout: checks.ready_for_closeout
    charges_total: int
    on_problem_list: int  # rows on the grant's problem list
    waiting: int  # the agent's records waiting for the accountant
    bucket_counts: dict[Bucket, int]
    next_closeout: CloseoutDate | None = None
    # Issue 165: the grant's "now" (its simulated clock on a sample grant, else the
    # real date), sent with every grant so screens never ask the browser for the date.
    now: UtcDatetime
    # Ruling 71: while the agent works on the grant, how far it is; None while it has
    # nothing queued or running.
    reading: ReadingProgress | None = None
    # Ruling 71: the one-line summary of the grant's last finished run (its
    # AgentRun.summary); None before any run finishes or when it left none.
    last_run_summary: Text | None = None


class SampleOption(Model):
    """One choice in the Add a grant dropdown's Sample list. GET /samples returns them in order.

    Names and descriptions come from the sample packs (W3).
    """

    choice: SampleChoice
    name: Text
    description: Text
    needs_confirm: bool  # true for larger_live
    available: bool
    unavailable_reason: str | None = None  # why it can't be opened now, for example a stale prerun


class SampleCreate(Model):
    """POST /workspaces/{workspace_id}/samples: opens a sample grant, returning its GrantSummary.

    It returns 201. The one refusal is a 409 whose `detail` is a SampleRefusal with
    reason `needs_confirm`: the choice needs a confirm and `confirmed` is false.
    Opening is never refused for the read-live limit, which is on moving the clock
    (timeline.TimelineMove).
    """

    choice: SampleChoice
    confirmed: bool = False


class SampleRefusalReason(StrEnum):
    NEEDS_CONFIRM = "needs_confirm"  # the larger live sample needs the user's confirm
    # Another of the user's larger read-live samples has agent runs queued or running
    # from a move of its clock.
    ANOTHER_SAMPLE_WORKING = "another_sample_working"


class SampleRefusal(Model):
    """The 409 `detail` of POST /workspaces/{workspace_id}/samples, of
    POST /grants/{grant_id}/timeline/start-over and of POST /grants/{grant_id}/timeline
    (ruling 41).

    Opening a sample and starting one over are refused only with `needs_confirm`.
    The read-live limit is settled as ruling 48, a first version, and is on the clock
    move: while one of the user's larger read-live samples has agent runs queued or
    running from a move of its clock, moving the clock of another of the user's
    larger read-live samples is refused with `another_sample_working`, and `grant`
    names the one still working.
    """

    reason: SampleRefusalReason
    message: Text  # worded by the server
    # For another_sample_working: the larger read-live sample still working.
    grant: GrantSummary | None = None


class TermView(Model):
    """One term on the grant page (answer 5), with what it replaced."""

    record: Record
    state: RecordState
    decision: Record | None = None  # the confirmation that decided it
    replaces: Record | None = None  # the term it replaced
    values: tuple[ValueState, ...] = ()
    status: RecordStatus | None = None  # its own problem, such as the agent's flag


class BudgetLineView(Model):
    """One budget line with what it holds and what's spent against it (answer 8)."""

    line: Record  # the budget_line term in force
    amount_cents: Cents
    spent_cents: Cents
    # Ruling 74: for a sub-line, the category it sits inside (records.CATEGORY_PARENT),
    # for example other_direct_costs for materials_and_supplies; None for a top-level
    # line. A sub-line's amount and spending are already inside its parent's, so the
    # rows don't add up: the screen nests a sub-line under its parent.
    parent: BudgetCategory | None = None


class BudgetView(Model):
    """The grant's budget figures, with the grant notes beside them (answers 3 and 8)."""

    lines: tuple[BudgetLineView, ...]
    # The award's limit: "Total Amount Obligated to Date" on the latest confirmed notice.
    limit_cents: Cents | None = None
    spent_cents: Cents  # the sum of the charges on the grant's ledger


class ReusableNoteView(Model):
    """A reusable note, what it excuses, and every charge it covers now."""

    note: Record  # the current accepted_reason with reusable true
    charge: Charge  # the charge it was written on: its ledger account and vendor
    amount_limit_cents: Cents  # the largest amount accepted under it
    covered: tuple[Charge, ...] = ()


class SignOffState(Model):
    """Not signed, signed, or changed since sign-off, with what changed (answer 14, 0022)."""

    state: SignOffStateName
    sign_off: Record | None = None  # the current sign_off record
    changes: tuple[SnapshotChange, ...] = ()
    # Ruling 72: why signing off can't be done now, in plain words, for example "The
    # agent is still working on this grant. Sign off once it's done."; None when it
    # can. The same reason the sign-off route refuses with.
    unavailable_reason: Text | None = None


class AcceptedGrantProblem(Model):
    """A problem on the grant itself that the accountant accepted (ruling 84).

    It leaves the problem list and shows on the grant overview beside the budget it's
    about, with the note, who accepted it and when, and Reopen.
    """

    problem: Problem  # check, problem and text, in the server's words
    # The accepted_reason record that accepts it. Reopen retracts it, and the problem
    # comes back to the problem list.
    acceptance_id: Id
    note: Text  # the accountant's note
    accepted_by: Text  # who accepted it: the member's name, else their email address
    accepted_at: UtcDatetime  # when, on the grant's clock (the acceptance's written_at)


class GrantDetail(Model):
    """GET /grants/{grant_id}. Carries no flagged charges: the problem list has its own response."""

    summary: GrantSummary
    terms: tuple[TermView, ...]
    budget: BudgetView
    grant_notes: tuple[GrantNote, ...]
    reusable_notes: tuple[ReusableNoteView, ...] = ()
    sign_off: SignOffState
    # Ruling 84: the grant's own problems the accountant accepted, oldest acceptance
    # first. Empty when none is accepted.
    accepted_problems: tuple[AcceptedGrantProblem, ...] = ()


# The problem list (answers 1 to 4 and 6). The server sorts the rows.


class GrantProblem(Problem):
    """A problem on the grant itself, as a row: with whether it's flagged, accepted or snoozed."""

    flagged: bool
    accepted: bool = False
    snoozed: bool = False


class GrantProblemRow(Model):
    kind: Literal["grant"] = "grant"
    problem: GrantProblem


class TermsWaitingRow(Model):
    """One row per source document with terms waiting to be confirmed (answer 4)."""

    kind: Literal["terms_waiting"] = "terms_waiting"
    file: EvidenceFile
    record_ids: tuple[Id, ...]
    text: Text  # for example "8 terms waiting to be confirmed", worded by the server


class RecordProblemRow(Model):
    kind: Literal["record"] = "record"
    status: RecordStatus
    record: Record | None = None
    file: EvidenceFile | None = None


class ChargeProblemRow(Model):
    kind: Literal["charge"] = "charge"
    charge: Charge
    status: ChargeStatus
    # Ruling 62: the benefit charges whose only problem is that they wait on this
    # salary line. They show with this row instead of as rows of their own, and
    # clear when this row clears. Empty for every other row.
    waiting_charge_ids: tuple[Id, ...] = ()


class HeldMailRow(Model):
    """Mail held from a sender who isn't known, or couldn't be verified (decision 0025)."""

    kind: Literal["held_mail"] = "held_mail"
    held: HeldMail


ProblemRow = Annotated[
    GrantProblemRow | TermsWaitingRow | RecordProblemRow | ChargeProblemRow | HeldMailRow,
    Field(discriminator="kind"),
]


class ProblemList(Model):
    """GET /grants/{grant_id}/problems"""

    rows: tuple[ProblemRow, ...]


def problem_row_key(row: ProblemRow) -> str:
    """A stable name for a row, for a sign-off's snapshot of the problem list."""
    match row:
        case GrantProblemRow():
            return f"grant:{row.problem.check}:{row.problem.problem}"
        case TermsWaitingRow():
            return f"terms_waiting:{row.file.id}"
        case RecordProblemRow():
            return f"record:{row.status.record_id or ''}:{row.status.file_id or ''}"
        case ChargeProblemRow():
            return f"charge:{row.charge.id}"
        case HeldMailRow():
            return f"held_mail:{row.held.id}"


# The charges list and the charge page.


class ChargeRow(Model):
    """One row of GET /grants/{grant_id}/charges (answers 8 and 15)."""

    charge: Charge
    status: ChargeStatus | None = None  # None until the checks first run on it
    # The budget_line term the charge's current budget_assignment points to, after
    # following corrections. None when no budget line is assigned.
    budget_line: Record | None = None
    # The NSF budget categories of the ledger account's group. Empty for an account in no group.
    account_categories: tuple[BudgetCategory, ...] = ()


class HistoryEntry(Model):
    """One status change, worded by the server (answer 11)."""

    entry: StatusEntry
    text: Text  # for example "new end date confirmed"


class LinkView(Model):
    """One fact covering a charge, for example "invoice 2050, $5,000 of $10,000"."""

    link: Record  # its part is what gets highlighted
    record: Record  # the bill, approval or note it points to now, after following corrections
    values: tuple[ValueState, ...] = ()  # that record's values
    file: EvidenceFile | None = None  # the record's file; None for a record the accountant typed


class RuleSource(Model):
    label: Text
    url: Text


class RuleView(Model):
    """A rulebook rule an answer names, looked up from the rulebook file."""

    id: Id  # for example "NSF-AIRFARE-CLASS"
    title: Text
    text: Text
    sources: tuple[RuleSource, ...] = ()


class AnswerView(Model):
    judgment: Record
    out_of_date: bool  # an open question covers it: rechecking, or back with the accountant
    rule: RuleView | None = None


class SuggestionChange(Model):
    """What accepting one of the agent's waiting records changes, worded by code (issue 114).

    The checks word it (app.checks.suggestions.suggestion_change), so every screen and
    the report read the same words. The agent's own reason stays on the record.
    """

    title: Text  # what accepting does, in one line
    now: str | None = None  # what's in force now, when it replaces something
    suggested: str | None = None  # what the agent suggests instead


class SuggestionView(Model):
    """One of the agent's records waiting for the accountant, with what it would replace."""

    record: Record
    replaces: Record | None = None
    charge_ids: tuple[Id, ...] = ()  # the charges it touches
    # What accepting it changes, worded by the server. The platform fills it.
    change: SuggestionChange | None = None


class StatusThreadEntry(Model):
    """Code's check results, at the time the status changed."""

    kind: Literal["status"] = "status"
    entry: StatusEntry


class MessageThreadEntry(Model):
    kind: Literal["message"] = "message"
    message: ThreadMessage


class RecordThreadEntry(Model):
    """The agent's suggestion, or the accountant's decision."""

    kind: Literal["record"] = "record"
    record: Record
    state: RecordState


ThreadEntry = Annotated[
    StatusThreadEntry | MessageThreadEntry | RecordThreadEntry, Field(discriminator="kind")
]


class Thread(Model):
    """A charge's or a record's thread, merged in time order by the server (answers 10, 12, 13).

    A record's thread follows the record that replaces it.
    """

    entries: tuple[ThreadEntry, ...]
    agent_run: AgentRun | None = None  # a run that will reach this thread, running or queued


class NewMessage(Model):
    """Posting to a thread. The server fills in the author, the time and the subject."""

    text: Text


class ChargeDetail(Model):
    """GET /charges/{charge_id}"""

    charge: Charge
    status: ChargeStatus | None = None
    budget_line: Record | None = None
    account_categories: tuple[BudgetCategory, ...] = ()
    corrections: tuple[Charge, ...] = ()  # the charges netted into it
    history: tuple[HistoryEntry, ...] = ()  # oldest first
    links: tuple[LinkView, ...] = ()
    answers: tuple[AnswerView, ...] = ()
    questions: tuple[OpenQuestion, ...] = ()
    waiting: tuple[SuggestionView, ...] = ()
    thread: Thread
    records: dict[Id, Record] = Field(default_factory=dict[Id, Record])
    files: dict[Id, EvidenceFile] = Field(default_factory=dict[Id, EvidenceFile])


# Evidence cards.


class FactLink(Model):
    link: Record
    charge: Charge


class FactView(Model):
    """One fact or term read from a file, its values' confirmed state and what it pays for."""

    record: Record  # after following corrections
    state: RecordState
    values: tuple[ValueState, ...] = ()
    links: tuple[FactLink, ...] = ()
    status: RecordStatus | None = None


class DuplicateView(Model):
    mark: Record  # the duplicate record
    state: RecordState  # waiting, or counts once confirmed


class EvidenceCard(Model):
    """One row of GET /grants/{grant_id}/evidence. `file.exported_from` says it's an export."""

    file: EvidenceFile
    facts: tuple[FactView, ...] = ()
    status: RecordStatus | None = None  # the file's own problem
    duplicate: DuplicateView | None = None  # when the file is the copy in a duplicate mark
    files: dict[Id, EvidenceFile] = Field(default_factory=dict[Id, EvidenceFile])


# Uploads and files.


class RowError(Model):
    row: int = Field(ge=1)  # 1 is the first row after the header
    message: Text


class LedgerUploadResult(Model):
    """POST /grants/{grant_id}/ledger"""

    added: int
    already_present: int  # lines whose line ID was already on file for this grant
    rejected: tuple[RowError, ...]


class TextSegment(Model):
    """A span of characters kept from the stored file, and where it sits in the reading text."""

    stored_start: int = Field(ge=0)  # where the span starts in the stored file's text
    reading_start: int = Field(ge=0)  # where it starts in the reading text
    length: int = Field(ge=1)


class ReadingView(Model):
    """The text the agent reads for an email on a grant with a stored clock (ruling 45).

    A first version. On a sample grant the viewer shows the same text the agent read,
    with the grant's date in place of the message's own. The segments are the spans
    kept from the stored file, in order; the gaps between them are headers replaced
    or dropped. A highlight at stored character positions maps into the reading text
    through the segment that holds it.
    """

    text: str
    segments: tuple[TextSegment, ...]


class FileLink(Model):
    """GET /evidence/{file_id}/content: a short-lived link to the original.

    `url` is always the original, still downloadable. For an email on a grant with a
    stored clock, `reading` is set too, and the viewer shows `reading.text`, mapping
    each stored-position highlight through its segments (ruling 45).
    """

    url: Text
    media_type: str | None = None
    expires_at: UtcDatetime
    reading: ReadingView | None = None


# The records request (POST /grants/{grant_id}/records). A term the accountant adds
# may leave out `dated`: the server fills in the workspace's "now". A sign-off sends
# only its note: the server stores the report and fills in the rest. The stored
# record still requires them.


class PeriodOfPerformanceInput(PeriodOfPerformance):
    dated: CitedDate | None = None  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]


class BudgetLineInput(BudgetLine):
    dated: CitedDate | None = None  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]


class PersonInput(Person):
    dated: CitedDate | None = None  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]


class ApprovalRuleInput(ApprovalRule):
    dated: CitedDate | None = None  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]


class RateInput(Rate):
    dated: CitedDate | None = None  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]


class NoticeInput(Notice):
    dated: CitedDate | None = None  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]


class OtherTermInput(OtherTerm):
    dated: CitedDate | None = None  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]


class SignOffInput(Model):
    kind: Literal[RecordKind.SIGN_OFF] = RecordKind.SIGN_OFF
    note: str | None = None


RecordDataInput = Annotated[
    PeriodOfPerformanceInput
    | BudgetLineInput
    | PersonInput
    | ApprovalRuleInput
    | RateInput
    | NoticeInput
    | OtherTermInput
    | Bill
    | Approval
    | Note
    | Link
    | BudgetAssignment
    | Judgment
    | ChecklistItem
    | ChecklistRemoval
    | Dispute
    | Duplicate
    | Correction
    | Remainder
    | Confirmation
    | AcceptedReason
    | Snooze
    | SignOffInput
    | MailDecision
    | Retraction,
    Field(discriminator="kind"),
]


class NewRecordInput(Model):
    """POST /grants/{grant_id}/records. The server fills in the ID, the author, the time,
    the `dated` of a term the accountant adds without one, and a sign-off's report."""

    data: RecordDataInput
    replaces_id: Id | None = None


class WriteRejected(Model):
    """The 422 body when the write check finds problems."""

    detail: tuple[str, ...]
