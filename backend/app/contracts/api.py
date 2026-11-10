"""API bodies that docs/contracts.md section 12 settles. The endpoint list is in that section.

What the grant, charge and evidence screens get from the server isn't settled
yet, so their bodies aren't here. W4 writes the routes in backend/app/api/, and
the frontend generates its TypeScript types from the OpenAPI schema they produce.
Errors use FastAPI's default {"detail": ...} body.
"""

from pydantic import Field

from .base import Id, Model, Text, UtcDatetime
from .charges import Charge
from .checks import Bucket, ChargeStatus
from .records import RecordData
from .workspaces import Grant


class WorkspaceCreate(Model):
    """POST /workspaces"""

    name: Text


class Clock(Model):
    """GET and POST /workspaces/{workspace_id}/clock"""

    now: UtcDatetime
    simulated: bool  # False when the workspace runs on the real date
    next_arrival_at: UtcDatetime | None = None  # the next charge or file waiting for the clock


class ClockMove(Model):
    """POST /workspaces/{workspace_id}/clock. Nothing moves to the next arrival. The clock only moves forward."""

    to: UtcDatetime | None = None


class GrantSummary(Model):
    """One row of GET /workspaces/{workspace_id}/grants."""

    grant: Grant
    bucket_counts: dict[Bucket, int]
    flagged: int  # how many are on the problem list
    waiting: int  # how many of the agent's records wait for the accountant


class ChargeRow(Model):
    """One row of GET /grants/{grant_id}/charges: each charge with its status."""

    charge: Charge
    status: ChargeStatus | None = None  # None until the checks first run on it


class RowError(Model):
    row: int = Field(ge=1)  # 1 is the first row after the header
    message: Text


class LedgerUploadResult(Model):
    """POST /grants/{grant_id}/ledger"""

    added: int
    already_present: int  # lines whose line ID was already on file
    rejected: list[RowError]


class NewRecord(Model):
    """POST /grants/{grant_id}/records. The server fills in the ID, the author and the time."""

    data: RecordData
    replaces_id: Id | None = None


class WriteRejected(Model):
    """The 422 body when the write check finds problems."""

    detail: list[str]


class FileLink(Model):
    """GET /evidence/{file_id}/content: a short-lived link to the original."""

    url: Text
    expires_at: UtcDatetime
