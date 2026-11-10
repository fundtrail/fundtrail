"""The screen bodies agreed in #22 (provisional), with the names the first screens chose
(PR 40, frontend/src/lib/api/types.ts).

Isolated here until the second contract change (#39) moves them into
`app/contracts/api.py` under the same names. Every body is made of the contract models
and the checks' output; the server works out what nothing stores and writes the wording.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import Field

from app.contracts.base import Cents, Id, Model, Text, UtcDatetime
from app.contracts.charges import Charge
from app.contracts.checks import (
    Bucket,
    ChargeStatus,
    GrantNote,
    OpenQuestion,
    Problem,
    RecordStatus,
)
from app.contracts.evidence import EvidenceFile
from app.contracts.records import BudgetCategory, Record
from app.contracts.runs import AgentRun, RunStatus, Trigger
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant

RecordStateName = Literal["counts", "waiting", "rejected", "replaced", "retracted"]


# Grants.


class CloseoutDate(Model):
    """The next closeout date that follows from the end date in force, as the server words it."""

    date: date
    label: Text


class GrantSummary(Model):
    """One row of GET /workspaces/{workspace_id}/grants (answer 7)."""

    grant: Grant
    end_date: date | None = None  # the end date in force; None while no period counts
    charges_ready: int  # Evidence complete or accepted, and not snoozed (decision 0022)
    charges_total: int
    on_problem_list: int  # rows on the grant's problem list
    waiting: int  # the agent's records waiting for the accountant
    bucket_counts: dict[Bucket, int]
    next_closeout: CloseoutDate | None = None


class BudgetLineView(Model):
    line: Record  # the budget_line term in force
    amount_cents: Cents
    spent_cents: Cents


class BudgetView(Model):
    lines: list[BudgetLineView]
    limit_cents: Cents | None = None  # "Total Amount Obligated to Date" on the latest notice
    spent_cents: Cents  # the sum of the charges on the grant's ledger


class TermView(Model):
    """A term on the terms page: waiting first, then in force, each with what it replaced."""

    record: Record
    state: RecordStateName
    decision: Record | None = None  # the confirmation that decided it
    status: RecordStatus | None = None
    replaces: Record | None = None


class SignOffState(Model):
    """Decision 0022: not signed, signed, or changed since sign-off with what changed."""

    state: Literal["not_signed", "signed", "changed"]
    sign_off: Record | None = None
    changes: list[Text] = Field(default_factory=list[Text])  # worded by the server


class GrantDetail(Model):
    """GET /grants/{grant_id}. Carries no flagged charges: the problem list is its own response."""

    summary: GrantSummary
    terms: list[TermView]
    budget: BudgetView
    grant_notes: list[GrantNote]
    sign_off: SignOffState


# The problem list.


class GrantProblem(Problem):
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
    record_ids: list[Id]
    text: Text


class RecordProblemRow(Model):
    kind: Literal["record"] = "record"
    status: RecordStatus
    record: Record | None = None
    file: EvidenceFile | None = None


class ChargeProblemRow(Model):
    kind: Literal["charge"] = "charge"
    charge: Charge
    status: ChargeStatus


ProblemRow = Annotated[
    GrantProblemRow | TermsWaitingRow | RecordProblemRow | ChargeProblemRow,
    Field(discriminator="kind"),
]


class ProblemList(Model):
    """GET /grants/{grant_id}/problems, sorted by the server (answer 1)."""

    rows: list[ProblemRow]


# Values, links and answers.


class ValueState(Model):
    path: Text  # as cited_values names it, for example "total" or "items[0].amount"
    confirmed: bool
    how: Literal["found", "record_confirmed", "typed"] | None = None
    confirmed_at: UtcDatetime | None = None


class LinkView(Model):
    link: Record
    record: Record | None = None  # the bill, approval or note now, after corrections
    values: list[ValueState] = Field(default_factory=list[ValueState])
    file: EvidenceFile | None = None
    charge: Charge | None = None


class AnswerView(Model):
    judgment: Record
    out_of_date: bool  # an open question covers it again


class SuggestionView(Model):
    record: Record  # the agent's record waiting for the accountant
    replaces: Record | None = None
    charge_ids: list[Id] = Field(default_factory=list[Id])


class BudgetAssignmentView(Model):
    assignment: Record
    line: Record


class HistoryEntry(Model):
    changed_at: UtcDatetime
    trigger: Trigger
    bucket: Bucket | None = None
    previous_bucket: Bucket | None = None
    text: Text  # worded by the server, for example "Apr 10, 2026 · new end date confirmed · ..."


# Threads.


class CheckItem(Model):
    kind: Literal["check"] = "check"
    at: UtcDatetime
    text: Text  # code's check results when the status changed, worded by the server


class MessageItem(Model):
    kind: Literal["message"] = "message"
    at: UtcDatetime
    message: ThreadMessage


class SuggestionItem(Model):
    kind: Literal["suggestion"] = "suggestion"
    at: UtcDatetime
    record: Record
    state: RecordStateName
    text: Text


class DecisionItem(Model):
    kind: Literal["decision"] = "decision"
    at: UtcDatetime
    record: Record
    text: Text


ThreadItem = Annotated[
    CheckItem | MessageItem | SuggestionItem | DecisionItem, Field(discriminator="kind")
]


class Thread(Model):
    """One thread in time order (answer 10), and whether a run that will reach it is
    running or queued (answer 12)."""

    items: list[ThreadItem]
    agent: RunStatus | None = None  # running or queued, or None
    agent_run: AgentRun | None = None


class NewMessage(Model):
    text: Text


class ChargeDetail(Model):
    """GET /charges/{charge_id}."""

    charge: Charge
    status: ChargeStatus | None = None
    budget: BudgetAssignmentView | None = None
    account_categories: list[BudgetCategory] = Field(default_factory=list[BudgetCategory])
    history: list[HistoryEntry]
    links: list[LinkView]
    answers: list[AnswerView]
    questions: list[OpenQuestion]
    waiting: list[SuggestionView]
    thread: Thread


# Evidence.


class FactView(Model):
    record: Record
    state: RecordStateName
    values: list[ValueState]
    links: list[LinkView]
    status: RecordStatus | None = None


class DuplicateView(Model):
    mark: Record
    state: RecordStateName
    original: EvidenceFile | None = None


class EvidenceCard(Model):
    file: EvidenceFile
    facts: list[FactView]
    status: RecordStatus | None = None
    duplicate: DuplicateView | None = None


# The clock.


class NextArrival(Model):
    at: UtcDatetime
    source: Literal["ledger", "email", "drive", "upload"]
    name: Text  # the file name, or the ledger line ID
    grant_id: Id


class ClockView(Model):
    """GET and POST /workspaces/{workspace_id}/clock (answer 9, decision 0023)."""

    now: UtcDatetime
    simulated: bool
    next_arrival_at: UtcDatetime | None = None
    next_arrival: NextArrival | None = None
    catching_up: bool = False  # the agent is still working through arrivals the clock passed


class ClockMove(Model):
    """Nothing moves to the next arrival. The clock only moves forward."""

    to: UtcDatetime | None = None
