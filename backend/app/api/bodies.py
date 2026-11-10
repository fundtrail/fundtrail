"""Request and response bodies agreed with the screens (#22, provisional) that aren't in the
contracts yet.

They move to `app/contracts/api.py` in the second contract change (#39), under the same
names. Nothing else in the API defines bodies.
"""

from typing import Annotated

from pydantic import Field

from app.contracts.base import Id, Model, UtcDatetime
from app.contracts.charges import Charge
from app.contracts.checks import ChargeStatus
from app.contracts.records import (
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
    Dispute,
    Duplicate,
    Judgment,
    Link,
    Note,
    Notice,
    OtherTerm,
    PeriodOfPerformance,
    Person,
    Rate,
    Record,
    Retraction,
    SignOff,
    Snooze,
)
from app.contracts.runs import RunStatus, Trigger


class RunRow(Model):
    """One row of GET /grants/{grant_id}/runs: the run as section 9 describes it, without the
    debug log's path, which is never shown to the accountant."""

    id: Id
    workspace_id: Id
    grant_id: Id
    trigger: Trigger
    status: RunStatus
    clock_now: UtcDatetime
    queued_at: UtcDatetime
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    summary: str | None = None
    error: str | None = None


class ChargeRow(Model):
    """One row of GET /grants/{grant_id}/charges: a charge with its status.

    Replaces the contracts' ChargeRow: #22 adds the assigned budget line and the ledger
    account group's categories.
    """

    charge: Charge
    status: ChargeStatus | None = None  # None until the checks first run on it
    # The budget_line term the charge's current budget_assignment points to, after
    # following corrections. None when no budget line is assigned.
    budget_line: Record | None = None
    # The NSF budget categories of the ledger account's group. Empty for an account in no group.
    account_categories: list[BudgetCategory] = Field(default_factory=list[BudgetCategory])


# The record request. A term the accountant adds may leave out `dated`: the server fills
# in the workspace's "now". The stored record still requires it.


class PeriodOfPerformanceInput(PeriodOfPerformance):
    dated: CitedDate | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


class BudgetLineInput(BudgetLine):
    dated: CitedDate | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


class PersonInput(Person):
    dated: CitedDate | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


class ApprovalRuleInput(ApprovalRule):
    dated: CitedDate | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


class RateInput(Rate):
    dated: CitedDate | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


class NoticeInput(Notice):
    dated: CitedDate | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


class OtherTermInput(OtherTerm):
    dated: CitedDate | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


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
    | Confirmation
    | AcceptedReason
    | Snooze
    | SignOff
    | Retraction,
    Field(discriminator="kind"),
]


class NewRecordInput(Model):
    """POST /grants/{grant_id}/records. The server fills in the ID, the author, the time,
    and the `dated` of a term the accountant adds without one."""

    data: RecordDataInput
    replaces_id: Id | None = None
