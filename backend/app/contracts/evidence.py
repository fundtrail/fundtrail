"""Evidence files: the originals, stored as they arrived (docs/contracts.md section 7)."""

from datetime import date
from enum import StrEnum

from pydantic import model_validator

from .base import Id, Model, Text, UtcDatetime

# The private Supabase Storage bucket the originals live in.
STORAGE_BUCKET = "evidence"


def storage_path(workspace_id: str, grant_id: str, file_id: str, name: str) -> str:
    """Where a file lives inside STORAGE_BUCKET."""
    return f"{workspace_id}/{grant_id}/{file_id}/{name}"


class Source(StrEnum):
    GMAIL = "gmail"
    DRIVE = "drive"
    UPLOAD = "upload"


class EvidenceFile(Model):
    id: Id
    workspace_id: Id
    grant_id: Id  # one grant per file for now
    source: Source
    name: Text  # the file name shown to the user
    media_type: Text  # for example application/pdf, image/jpeg, text/plain, message/rfc822
    storage_path: Text  # {workspace_id}/{grant_id}/{file_id}/{name} inside STORAGE_BUCKET
    sha256: Text  # of the stored bytes; catches the exact same file arriving twice
    # The file's own date when the source gives one, such as an email's sent date.
    # A date written inside the document is a cited value on a record instead.
    document_date: date | None = None
    arrived_at: UtcDatetime  # when it reached FundTrail; the clock uses this one
    sender: str | None = None  # the sender's address, for Gmail
    source_ref: str | None = None  # the Gmail message ID or the Drive file ID
    parent_id: str | None = None  # for an attachment, the email it came with
    # Decision 0025: a Google Doc, Sheet or Slides file is exported to a PDF when
    # it's read, and the export is what's stored. This is the Google type it was
    # exported from, so its card can say it's an export. None for any other file.
    exported_from: str | None = None

    @model_validator(mode="after")
    def _path(self):
        if self.storage_path != storage_path(self.workspace_id, self.grant_id, self.id, self.name):
            raise ValueError("storage_path is {workspace_id}/{grant_id}/{file_id}/{name}")
        return self
