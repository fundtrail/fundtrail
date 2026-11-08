"""Request and response bodies for the API. The endpoint list is in docs/contracts.md.

W4 writes the FastAPI routes in backend/app/api/. The frontend generates its
TypeScript types from the OpenAPI schema those routes produce.
"""

from pydantic import AwareDatetime, Field

from .base import Model
from .charges import Charge
from .checks import Bucket, ChargeStatus, StatusEntry
from .evidence import EvidenceFile
from .records import Record, RecordData
from .workspaces import Grant


class WorkspaceCreate(Model):
    name: str = Field(min_length=1)


class Clock(Model):
    now: AwareDatetime
    simulated: bool  # False when the workspace runs on the real date
    next_arrival_at: AwareDatetime | None = None  # the next charge or file waiting for the clock


class ClockMove(Model):
    # None moves to the next arrival. The clock only moves forward.
    to: AwareDatetime | None = None


class GrantSummary(Model):
    grant: Grant
    bucket_counts: dict[Bucket, int]


class Term(Model):
    record: Record
    confirmed: bool


class GrantDetail(Model):
    grant: Grant
    terms: list[Term]  # current term records


class ChargeRow(Model):
    charge: Charge
    status: ChargeStatus | None = None  # None until the checks first run on it


class EvidenceCard(Model):
    file: EvidenceFile
    records: list[Record]  # current records that cite or link this file
    linked_charge_ids: list[str]  # empty while the file waits unlinked


class ChargeDetail(Model):
    charge: Charge
    status: ChargeStatus | None = None
    history: list[StatusEntry]  # oldest first
    evidence: list[EvidenceCard]  # files linked to this charge
    records: list[Record]  # every record the status and the history point to


class FileUrl(Model):
    url: str  # a short-lived signed URL for the original file
    media_type: str
    expires_at: AwareDatetime


class RowError(Model):
    row: int  # 1 is the first row after the header
    message: str


class LedgerUploadResult(Model):
    added: int
    already_present: int  # lines whose ledger line ID was already on file
    rejected: list[RowError]


class NewRecord(Model):
    """A record the app writes for the accountant.

    The server fills in the ID, workspace, grant, author and written_at.
    """

    data: RecordData
    replaces_id: str | None = None
