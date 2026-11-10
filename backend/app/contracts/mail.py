"""Mail held from unknown senders, and what the Gmail and Drive checker saves (decision 0025).

Mail from anyone who isn't a known sender is held: it's stored, the agent doesn't
read it, and no check uses it. The accountant can let one message in, add the
sender as known (a `person` term, which lets in everything held from them), or
dismiss it. Letting in and dismissing are `mail_action` records. A message that's
let in arrives at that moment, as evidence files.
"""

from enum import StrEnum
from typing import Literal

from .base import Id, Model, Text, UtcDatetime


class HeldFile(Model):
    """One stored file of a held message: the message itself, or an attachment."""

    name: Text
    media_type: Text
    storage_path: Text  # in the private evidence bucket
    sha256: Text


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
