"""What Gmail and Drive bring in, before it's stored (decision 0025).

The evidence file model is the contract's `EvidenceFile` (docs/contracts.md section
7). This module keeps a local `IncomingFile`, which also carries the bytes and what
the contract has no field for yet, and one adapter, `to_evidence_file`, that turns it
into the contract model.

Held mail, skipped files and the checker's progress are the contract's
(`app/contracts/mail.py`). The checker hands the sink a `PendingHold`, which still
carries the bytes, and `to_held_mail` makes the contract's `HeldMail` once they're
stored. A grant's address and its Drive folder are still a local `GrantRoute`.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Literal

from app.contracts.evidence import EvidenceFile, Source, storage_path
from app.contracts.mail import HeldFile, HeldMail, HoldReason, SkippedFile, SkipReason

IncomingSource = Literal["gmail", "drive", "upload"]  # the contract's `Source` values

# The largest attachment or Drive file taken in. Supabase Storage's free plan caps a
# single upload at 50 MB.
MAX_FILE_BYTES = 50 * 1024 * 1024

# Characters Supabase Storage accepts in an object name, minus the ones that read badly.
_UNSAFE = re.compile(r"[^A-Za-z0-9._\-(), ]+")
_MAX_NAME = 120


def _clean(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return _UNSAFE.sub("_", ascii_text).strip(" ._")


def _split_extension(name: str) -> tuple[str, str]:
    stem, dot, extension = name.rpartition(".")
    if not dot or not extension or len(extension) > 10 or " " in extension:
        return name, ""
    return stem, extension


def safe_name(name: str, fallback: str) -> str:
    """An ASCII file name that is safe inside a storage path, keeping its extension.

    The stem and the extension are cleaned apart, so `请求.pdf` keeps `.pdf`. A stem that
    cleans away to nothing takes the fallback's stem.
    """
    raw_stem, raw_extension = _split_extension(name)
    stem, extension = _clean(raw_stem), _clean(raw_extension)
    fallback_stem, fallback_extension = _split_extension(fallback)
    if not stem:
        stem, extension = fallback_stem, extension or fallback_extension
    suffix = f".{extension}" if extension else ""
    return stem[: _MAX_NAME - len(suffix)].rstrip(" ._") + suffix


@dataclass(frozen=True)
class IncomingFile:
    """One file that will become one evidence file."""

    key: str  # local key, unique within one check; attachments point at their message's key
    grant_id: str
    workspace_id: str
    source: IncomingSource
    name: str
    media_type: str
    data: bytes = field(repr=False)
    document_date: date | None = None
    sender: str | None = None
    source_ref: str | None = None  # the Gmail message ID or the Drive file ID
    parent_key: str | None = None  # for an attachment, the key of the email it came with
    # For a Google Doc, Sheet, Slides or Drawings file: the Google type it was exported
    # from. The contract has no field for this yet (issue 39), and the evidence card needs it.
    exported_from: str | None = None
    arrived_at: datetime | None = None  # set when it arrives, at the workspace's "now"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def arriving(self, now: datetime) -> "IncomingFile":
        return replace(self, arrived_at=now)


@dataclass(frozen=True)
class GrantRoute:
    """What the connectors need to know about one grant. Stored once issue 39 lands."""

    workspace_id: str
    grant_id: str
    tag: str  # the short random code after the plus sign in the grant's address
    drive_folder_id: str | None = None
    # Known senders (0025): people in the award letter with a confirmed term, anyone the
    # accountant added, and the accountant's own sign-in address.
    known_senders: frozenset[str] = frozenset()
    # When the grant's address was made. Its first check takes in everything delivered
    # to the address since then.
    address_created_at: datetime | None = None

    def __post_init__(self) -> None:
        lowered = frozenset(s.strip().lower() for s in self.known_senders)
        object.__setattr__(self, "known_senders", lowered)
        object.__setattr__(self, "tag", self.tag.lower())


@dataclass(frozen=True)
class FoundSkip:
    """A file found not to be taken in, before it's reported.

    It becomes the contract's `SkippedFile` once it has a time, through
    `to_skipped_file`. Very small images and signature parts aren't reported: 0025
    skips them on purpose.
    """

    workspace_id: str
    grant_id: str
    name: str
    source: Literal["gmail", "drive"]
    source_ref: str  # the Gmail message ID, or the grant's Drive folder ID
    reason: SkipReason


def to_skipped_file(found: FoundSkip, skipped_at: datetime | None) -> SkippedFile:
    """The contract's skipped file. One with no time is refused, as a file that hasn't
    arrived is refused by `to_evidence_file`."""
    if skipped_at is None:
        raise ValueError("a skipped file is reported only with the workspace's now")
    return SkippedFile(
        workspace_id=found.workspace_id,
        grant_id=found.grant_id,
        name=found.name,
        source=found.source,
        source_ref=found.source_ref,
        reason=found.reason,
        skipped_at=skipped_at,
    )


@dataclass(frozen=True)
class PendingHold:
    """A message to hold, as the checker hands it to the sink, before it's stored.

    The sink stores `files` in the evidence bucket and saves the contract's `HeldMail`
    with `to_held_mail`, in one write with its `skipped` files. The skipped files go on
    the held message only, never on the grant's own list, so they stay off the grant's
    problem list until it's let in (0025).
    """

    workspace_id: str
    grant_id: str
    sender: str | None  # the From address, when it reads as exactly one address
    # The From line as written, to show the accountant. The contract has no field for it.
    from_header: str
    gmail_message_id: str
    subject: str | None
    files: tuple[IncomingFile, ...]  # the message first, then its attachments; not arrived
    held_at: datetime  # the workspace's "now" when it was held
    reason: HoldReason
    skipped: tuple[SkippedFile, ...] = ()  # stamped with held_at, when they were found


def to_held_mail(pending: PendingHold, *, held_id: str, files: tuple[HeldFile, ...]) -> HeldMail:
    """The contract's held message, once its files are stored as `files`."""
    if len(files) != len(pending.files):
        raise ValueError("every file of a held message is stored")
    return HeldMail(
        id=held_id,
        workspace_id=pending.workspace_id,
        grant_id=pending.grant_id,
        sender=pending.sender,
        reason=pending.reason,
        source_ref=pending.gmail_message_id,
        subject=pending.subject or None,
        held_at=pending.held_at,
        files=files,
        skipped=pending.skipped,
    )


def let_in_skips(held: HeldMail, now: datetime) -> list[SkippedFile]:
    """A held message's skipped files, reported when it's let in, at that moment (0025).

    The sink saves them in the same write as the evidence files the message becomes.
    """
    # model_validate, not model_copy: the time is checked and converted to UTC like any
    # contract timestamp, so a naive time is refused.
    return [
        SkippedFile.model_validate({**skip.model_dump(), "skipped_at": now})
        for skip in held.skipped
    ]


def to_evidence_file(
    incoming: IncomingFile, *, file_id: str, parent_id: str | None
) -> EvidenceFile:
    """The contract's evidence file for an arrived file.

    `file_id` is the new file's ID and `parent_id` the stored ID of its message.
    `exported_from` has no contract field yet and is left out.
    """
    if incoming.arrived_at is None:
        raise ValueError("a file is stored only once it has arrived")
    return EvidenceFile(
        id=file_id,
        workspace_id=incoming.workspace_id,
        grant_id=incoming.grant_id,
        source=Source(incoming.source),
        name=incoming.name,
        media_type=incoming.media_type,
        storage_path=storage_path(incoming.workspace_id, incoming.grant_id, file_id, incoming.name),
        sha256=incoming.sha256,
        document_date=incoming.document_date,
        arrived_at=incoming.arrived_at,
        sender=incoming.sender,
        source_ref=incoming.source_ref,
        parent_id=parent_id,
    )
