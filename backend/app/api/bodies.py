"""Response bodies agreed with the screens (#22, provisional) that aren't in the contracts yet.

They move to `app/contracts/api.py` in a follow-up contract pull request, under the same
names. Nothing else in the API defines bodies.
"""

from typing import Any

from app.contracts.base import Id, Model
from app.contracts.charges import Charge
from app.contracts.checks import ChargeStatus
from app.contracts.records import BudgetCategory, Record


class ChargeRow(Model):
    """One row of GET /grants/{grant_id}/charges: a charge with its status.

    Replaces the contracts' ChargeRow: #22 adds the assigned budget line and the ledger
    account group's categories.
    """

    charge: Charge
    status: ChargeStatus | None = None  # None until the checks first run on it
    # The budget_line term the charge's current budget_assignment points to, after
    # following corrections. None when the agent hasn't assigned one.
    budget_line: Record | None = None
    # The NSF budget categories of the ledger account's group. Empty for an account in no group.
    account_categories: list[BudgetCategory] = []


class NewRecordIn(Model):
    """POST /grants/{grant_id}/records. The server fills in the ID, the author and the time,
    and the `dated` of a term the accountant adds without one.

    `data` is one record kind (see Record.data in the response). It's taken as an object
    here so a missing term date can be filled in before the record is checked.
    """

    data: dict[str, Any]
    replaces_id: Id | None = None
