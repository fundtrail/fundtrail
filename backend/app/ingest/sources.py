"""The one small interface for mail and Drive, and its stand-in that reads from disk.

Code that checks for new mail and files talks only to `MailSource` and
`DriveSource`. The real Gmail and Drive clients (`google_clients.py`) run only in
the smoke test. Everything else, tests included, uses `DiskMailbox` and `DiskDrive`,
so no Google account is needed (decision 0025).
"""

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import UTC, datetime
from email import message_from_bytes, policy
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Protocol

FOLDER = "application/vnd.google-apps.folder"
GOOGLE_DOC = "application/vnd.google-apps.document"
GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDES = "application/vnd.google-apps.presentation"
GOOGLE_EXPORTED_TYPES = {GOOGLE_DOC, GOOGLE_SHEET, GOOGLE_SLIDES}


@dataclass(frozen=True)
class RawMessage:
    id: str  # the Gmail message ID
    raw: bytes  # the message as it arrived (RFC 822)


@dataclass(frozen=True)
class DriveEntry:
    id: str  # the Drive file ID
    name: str
    mime_type: str
    modified_time: datetime
    md5: str | None  # Drive gives none for Google Docs, Sheets and Slides


class MailSource(Protocol):
    def fetch_new(self, cursor: str | None) -> tuple[list[RawMessage], str]:
        """Messages that arrived after `cursor`, oldest first, and the cursor to pass next time.

        With no cursor, the first check starts from now and returns nothing older. That
        is safe because a grant's address doesn't exist before its grant does, and each
        grant's first check reads its own address's mail with `fetch_delivered_to`.
        """
        ...

    def fetch_delivered_to(self, address: str, since: datetime | None) -> list[RawMessage]:
        """Every message delivered to `address` since `since` (all of them if None), oldest
        first."""
        ...


class DriveSource(Protocol):
    def list_tree(self, folder_id: str) -> list[DriveEntry]:
        """Every file in the folder and the folders inside it. Folders themselves are left out."""
        ...

    def download(self, file_id: str) -> bytes: ...

    def export_pdf(self, file_id: str) -> bytes:
        """A Google Doc, Sheet or Slides file exported as a PDF."""
        ...


class DiskMailbox:
    """A folder of `.eml` files. A message's ID is its file name without the suffix.

    Each file is the message as the mailbox holds it, so it carries the mailbox's own
    `Delivered-To` and `Authentication-Results` headers.

    Files are read in name order, and the cursor is the last name read.
    """

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def fetch_new(self, cursor: str | None) -> tuple[list[RawMessage], str]:
        names = sorted(p.stem for p in self.folder.glob("*.eml"))
        if cursor is None:
            return [], names[-1] if names else ""
        new = [n for n in names if n > cursor]
        messages = [RawMessage(n, (self.folder / f"{n}.eml").read_bytes()) for n in new]
        return messages, new[-1] if new else cursor

    def fetch_delivered_to(self, address: str, since: datetime | None) -> list[RawMessage]:
        found = []
        for path in sorted(self.folder.glob("*.eml")):
            raw = path.read_bytes()
            msg = message_from_bytes(raw, policy=policy.default)
            fields = [str(v) for h in _ADDRESS_HEADERS for v in msg.get_all(h, [])]
            if address.lower() not in {a.lower() for _, a in getaddresses(fields)}:
                continue
            if since is not None and msg["date"]:
                if parsedate_to_datetime(str(msg["date"])) < since:
                    continue
            found.append(RawMessage(path.stem, raw))
        return found


_ADDRESS_HEADERS = ("delivered-to", "x-original-to", "to", "cc")


# On disk, a Google file is stood in for by a file with one of these suffixes. Its bytes
# are what the export returns.
_DISK_GOOGLE_SUFFIXES = {".gdoc": GOOGLE_DOC, ".gsheet": GOOGLE_SHEET, ".gslides": GOOGLE_SLIDES}


class DiskDrive:
    """A folder on disk standing in for Drive.

    A folder's ID and a file's ID are their paths relative to `root`, and a file's
    modified time is its modification time on disk.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def list_tree(self, folder_id: str) -> list[DriveEntry]:
        entries: list[DriveEntry] = []
        for path in sorted((self.root / folder_id).rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            data = path.read_bytes()
            google_type = _DISK_GOOGLE_SUFFIXES.get(path.suffix)
            entries.append(
                DriveEntry(
                    id=path.relative_to(self.root).as_posix(),
                    name=path.stem if google_type else path.name,
                    mime_type=google_type or _guess_type(path),
                    modified_time=datetime.fromtimestamp(path.stat().st_mtime, UTC),
                    md5=None if google_type else hashlib.md5(data).hexdigest(),
                )
            )
        return entries

    def download(self, file_id: str) -> bytes:
        return (self.root / file_id).read_bytes()

    def export_pdf(self, file_id: str) -> bytes:
        return (self.root / file_id).read_bytes()


def _guess_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"
