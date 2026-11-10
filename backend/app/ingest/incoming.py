"""What Gmail and Drive bring in, before it's stored (decision 0025).

The evidence file model lives in the contracts (docs/contracts.md section 7, the
`EvidenceFile` model in PR 35). It isn't on main yet, so this module keeps a local
`IncomingFile` and one adapter, `evidence_file_fields`, that turns it into the
contract's fields by name. When the contract lands, the adapter becomes
`EvidenceFile(**evidence_file_fields(...))` and nothing else here changes.

Held mail, a grant's address and its Drive folder wait on contract additions
(issue 39). Until then `HeldMail` and `GrantRoute` are local types behind the
same adapter.
"""

import hashlib
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Literal

Source = Literal["gmail", "drive", "upload"]  # the contract's `Source` values

_UNSAFE = re.compile(r"[^\w.,\- ()]+")


def safe_name(name: str, fallback: str) -> str:
    """A file name that is safe inside a storage path: no slashes or control characters."""
    cleaned = _UNSAFE.sub("_", name).strip(" ._")[:150]
    return cleaned or fallback


@dataclass(frozen=True)
class IncomingFile:
    """One file that will become one evidence file."""

    key: str  # local key, unique within one check; attachments point at their message's key
    grant_id: str
    workspace_id: str
    source: Source
    name: str
    media_type: str
    data: bytes = field(repr=False)
    document_date: date | None = None
    sender: str | None = None
    source_ref: str | None = None  # the Gmail message ID or the Drive file ID
    parent_key: str | None = None  # for an attachment, the key of the email it came with
    # For a Google Doc, Sheet or Slides file: the Google type it was exported from.
    # The contract has no field for this yet (issue 39), and the evidence card needs it.
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
    # accountant added, and the accountant's own sign-in address. Lower case.
    known_senders: frozenset[str] = frozenset()
    # When the grant's address was made. Its first check takes in everything delivered
    # to the address since then.
    address_created_at: datetime | None = None


# Why a message is held:
# - "unknown_sender": the From address isn't a known sender.
# - "unverified_sender": the From address is a known sender, but the mailbox couldn't
#   verify that the message really came from that address.
HoldReason = Literal["unknown_sender", "unverified_sender"]


@dataclass(frozen=True)
class HeldMail:
    """Mail held for the accountant: stored, not read by the agent, not used by checks.

    The accountant can still let it in.
    """

    grant_id: str
    workspace_id: str
    sender: str | None
    gmail_message_id: str
    files: tuple[IncomingFile, ...]  # the message first, then its attachments; not arrived
    held_at: datetime  # the workspace's "now" when it was held
    reason: HoldReason = "unknown_sender"

    def let_in(self, now: datetime) -> list[IncomingFile]:
        """A message that's let in arrives at that moment (0025)."""
        return [f.arriving(now) for f in self.files]


def storage_path(workspace_id: str, grant_id: str, file_id: str, name: str) -> str:
    """The contract's storage path, `{workspace_id}/{grant_id}/{file_id}/{name}`."""
    return f"{workspace_id}/{grant_id}/{file_id}/{name}"


def evidence_file_fields(
    incoming: IncomingFile, *, file_id: str, parent_id: str | None
) -> dict[str, object]:
    """The contract `EvidenceFile`'s fields for an arrived file, by name.

    `file_id` is the new file's ID and `parent_id` the stored ID of its message.
    `exported_from` has no contract field yet and is left out.
    """
    if incoming.arrived_at is None:
        raise ValueError("a file is stored only once it has arrived")
    return {
        "id": file_id,
        "workspace_id": incoming.workspace_id,
        "grant_id": incoming.grant_id,
        "source": incoming.source,
        "name": incoming.name,
        "media_type": incoming.media_type,
        "storage_path": storage_path(
            incoming.workspace_id, incoming.grant_id, file_id, incoming.name
        ),
        "sha256": incoming.sha256,
        "document_date": incoming.document_date,
        "arrived_at": incoming.arrived_at,
        "sender": incoming.sender,
        "source_ref": incoming.source_ref,
        "parent_id": parent_id,
    }
