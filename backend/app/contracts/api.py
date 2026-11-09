"""Request and response bodies for the API. The endpoint list is in docs/contracts.md.

W4 writes the FastAPI routes in backend/app/api/. The frontend generates its
TypeScript types from the OpenAPI schema those routes produce.
"""

from enum import StrEnum

from pydantic import AwareDatetime, Field

from .base import Model
from .charges import Charge
from .checks import Bucket, ChargeStatus, GrantNote, OpenQuestion, StatusEntry
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
    flagged: int  # charges on the problem list
    waiting: int  # the agent's records waiting for the accountant


class TermState(StrEnum):
    CONFIRMED = "confirmed"  # or written by the accountant, which needs no confirmation
    WAITING = "waiting"
    REJECTED = "rejected"


class Term(Model):
    record: Record
    state: TermState


class GrantDetail(Model):
    grant: Grant
    terms: list[Term]  # term records that nothing replaces, in every state
    waiting: list[Record]  # the agent's suggested fixes waiting for the accountant
    questions: list[OpenQuestion]  # open questions for the accountant
    notes: list[GrantNote]


class ChargeRow(Model):
    charge: Charge
    status: ChargeStatus | None = None  # None until the checks first run on it


class LinkView(Model):
    """One fact covering a charge, for example "invoice 1001, $1,240"."""

    link: Record  # its data is a Link; the part is what gets highlighted
    record: Record  # the receipt, approval or note
    file: EvidenceFile  # the record's file


class ChargeDetail(Model):
    charge: Charge
    status: ChargeStatus | None = None
    history: list[StatusEntry]  # oldest first
    links: list[LinkView]  # current links to this charge
    judgments: list[Record]  # current answers about this charge
    waiting: list[Record]  # suggested fixes that touch this charge
    records: list[Record]  # every other record the status and the history point to


class EvidenceCard(Model):
    file: EvidenceFile
    records: list[Record]  # current facts and terms read from this file
    links: list[Record]  # current links to those facts; empty while the file waits unlinked


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


class WriteRejected(Model):
    """The 422 body when check_new_record finds problems with a write."""

    problems: list[str]
