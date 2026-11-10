"""What Gmail and Drive bring in, before it's stored (decision 0025).

The evidence file model is the contract's `EvidenceFile` (docs/contracts.md section
7). This module keeps a local `IncomingFile`, which also carries the bytes and what
the contract has no field for yet, and one adapter, `to_evidence_file`, that turns it
into the contract model.

Held mail, a grant's address and its Drive folder wait on contract additions
(issue 39). Until then `HeldMail` and `GrantRoute` are local types.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Literal

from app.contracts.evidence import EvidenceFile, Source, storage_path

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


# Why a message is held:
# - "unknown_sender": the From address isn't a known sender.
# - "unverified_sender": the message claims a known sender, or its From line can't be
#   read as exactly one address, and the mailbox couldn't verify that it really came
#   from that address.
HoldReason = Literal["unknown_sender", "unverified_sender"]


# Why a file the accountant sent wasn't taken in:
# - "too_large": over MAX_FILE_BYTES, or a Google export over Drive's 10 MB limit.
# - "not_exportable": a Google file with no PDF export, such as a Form or a Site.
SkipReason = Literal["too_large", "not_exportable"]


@dataclass(frozen=True)
class SkippedFile:
    """A file that was sent but not taken in, so the grant can show it as a problem.

    Its fields are the contract's `SkippedFile` (PR 61, `app/contracts/mail.py`), which
    isn't on main yet. Very small images and signature parts aren't reported: 0025
    skips them on purpose.
    """

    workspace_id: str
    grant_id: str
    name: str
    source: Literal["gmail", "drive"]
    source_ref: str  # the Gmail message ID, or the grant's Drive folder ID
    reason: SkipReason
    skipped_at: datetime | None = None  # the workspace's "now"; set when it's reported

    def at(self, now: datetime) -> "SkippedFile":
        return replace(self, skipped_at=now)


@dataclass(frozen=True)
class LetIn:
    """What a held message brings when it's let in."""

    files: list[IncomingFile]  # arrived at that moment
    skipped: list[SkippedFile]  # attachments that weren't taken in, reported at that moment


@dataclass(frozen=True)
class HeldMail:
    """Mail held for the accountant: stored, not read by the agent, not used by checks.

    Its skipped attachments are kept here and reported only if it's let in, because no
    check uses held mail (0025). The accountant can still let it in.
    """

    grant_id: str
    workspace_id: str
    sender: str | None  # the From address, when it reads as exactly one address
    from_header: str  # the From line as written, to show the accountant
    gmail_message_id: str
    files: tuple[IncomingFile, ...]  # the message first, then its attachments; not arrived
    held_at: datetime  # the workspace's "now" when it was held
    reason: HoldReason = "unknown_sender"
    skipped: tuple[SkippedFile, ...] = ()  # not reported while held

    def let_in(self, now: datetime) -> LetIn:
        """A message that's let in arrives at that moment (0025), and so do its skips."""
        return LetIn(
            files=[f.arriving(now) for f in self.files],
            skipped=[s.at(now) for s in self.skipped],
        )


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
