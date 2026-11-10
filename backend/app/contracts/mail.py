"""Mail held from unknown senders, and what the Gmail and Drive checker saves (decision 0025).

Mail from anyone who isn't a known sender is held: it's stored, the agent doesn't
read it, and no check uses it. The accountant can let one message in, add the
sender as known (a `person` term, which lets in everything held from them), or
dismiss it. Letting in and dismissing are `mail_action` records. A message that's
let in arrives at that moment, as evidence files.
"""

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import model_validator

from .base import Id, Model, Text, UtcDatetime


class SkipReason(StrEnum):
    TOO_LARGE = "too_large"
    NOT_EXPORTABLE = "not_exportable"  # a Google file that couldn't be exported to a PDF


class SkippedFile(Model):
    """A file Gmail or Drive brought that wasn't taken in. The checks raise one problem on the
    grant naming the grant's skipped files."""

    workspace_id: Id
    grant_id: Id
    name: Text
    source: Literal["gmail", "drive"]
    source_ref: Text  # the Gmail message ID, or the Drive folder ID
    reason: SkipReason
    skipped_at: UtcDatetime  # the workspace's "now"


class HeldFile(Model):
    """One stored file of a held message: the message itself, or an attachment."""

    name: Text
    media_type: Text
    storage_path: Text  # in the private evidence bucket
    sha256: Text
    # Ruling 43: the sent date the file's evidence file takes as its document_date when
    # the message is let in. On a sample grant it's the grant's now when the message
    # was held (the sample's sent date), never the message's Date header; on any other
    # grant it's the Date header's date. None when there's none.
    document_date: date | None = None


class HoldReason(StrEnum):
    UNKNOWN_SENDER = "unknown_sender"  # the sender isn't a known sender
    # The address is a known sender's, but it couldn't be verified as really theirs.
    UNVERIFIED_SENDER = "unverified_sender"


class HeldMail(Model):
    """One message held: its sender isn't known, or a known address couldn't be verified."""

    id: Id
    workspace_id: Id
    grant_id: Id  # routed by the code in the address it was delivered to
    sender: str | None = None  # the sender's address, lower case
    reason: HoldReason
    source_ref: Text  # the Gmail message ID
    subject: str | None = None
    held_at: UtcDatetime  # the workspace's "now" when it was held
    files: tuple[HeldFile, ...]  # the message first, then its attachments
    # The message's attachments that weren't taken in, found when it was read. They're
    # kept with the held message, never in the grant's own skipped files, so they stay
    # off the grant's problem list while it's held. They reach the grant only if the
    # message is let in, and they stay here, unused, if it's dismissed.
    skipped: tuple[SkippedFile, ...] = ()

    @model_validator(mode="after")
    def _skips_are_this_messages(self):
        for skip in self.skipped:
            mine = (skip.workspace_id, skip.grant_id, skip.source, skip.source_ref)
            if mine != (self.workspace_id, self.grant_id, "gmail", self.source_ref):
                raise ValueError("a held message's skipped files are its own Gmail attachments")
        return self


class DriveVersion(Model):
    """The version of one Drive file last taken in for a grant."""

    grant_id: Id
    drive_file_id: Id
    version: Text  # what makes two sightings of a file the same version


class CheckerProgress(Model):
    """What the Gmail and Drive checker saves between checks, for the app's one account."""

    mail_cursor: str | None = None  # Gmail's position after the last check
    seen_message_ids: tuple[Id, ...] = ()
    drive_versions: tuple[DriveVersion, ...] = ()
    # The grants whose first search of their address has finished. A grant is added only
    # once every message delivered to its address before then was stored or held, never
    # when the search starts, so a first search cut off partway is redone in full after
    # a restart and nothing is missed.
    first_search_done: tuple[Id, ...] = ()
