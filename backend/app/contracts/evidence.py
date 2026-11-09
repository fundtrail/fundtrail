"""Evidence files: originals stored as they arrived."""

from datetime import date
from enum import StrEnum

from pydantic import AwareDatetime

from .base import Model

STORAGE_BUCKET = "evidence"  # private Supabase Storage bucket


class Source(StrEnum):
    GMAIL = "gmail"
    DRIVE = "drive"
    UPLOAD = "upload"


class EvidenceFile(Model):
    id: str
    workspace_id: str
    grant_id: str
    source: Source
    name: str  # the file name shown to the user
    media_type: str  # for example application/pdf, image/jpeg, text/plain
    # Path inside STORAGE_BUCKET: {workspace_id}/{grant_id}/{file_id}/{name}
    storage_path: str
    sha256: str  # of the stored bytes
    # Its own date when the source gives one, such as an email's sent date.
    # A date the document states inside it is a cited value on a record instead.
    document_date: date | None = None
    arrived_at: AwareDatetime  # when it reached FundTrail; the clock uses this one
    sender: str | None = None  # the sender's email address, for Gmail
    source_ref: str | None = None  # Gmail message ID or Drive file ID
    parent_id: str | None = None  # for an attachment, the email file it came in
