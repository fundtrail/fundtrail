"""A Drive folder tied to a grant by its link (decision 0025).

- A new file becomes an evidence file. The first check of a folder takes every file
  already in it.
- A file Drive says was modified arrives as a new evidence file; the earlier one stays.
- A file still being edited is taken once it has stopped changing for `SETTLE`.
- A Google Doc, Sheet, Slides or Drawings file is exported to PDF (Portable Document
  Format), and the export is marked. Other Google types are skipped.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .incoming import MAX_FILE_BYTES, IncomingFile, safe_name
from .sources import GOOGLE_EXPORTED_TYPES, GOOGLE_PREFIX, CannotTake, DriveEntry, DriveSource

# How long a file has to go without changing before it's taken in.
SETTLE = timedelta(minutes=10)

_FOLDER_LINK = [
    re.compile(r"^(?:https?://)?drive\.google\.com/drive/(?:u/\d+/)?folders/([\w-]+)"),
    re.compile(r"^(?:https?://)?drive\.google\.com/(?:open|folderview)\?(?:[^#]*&)?id=([\w-]+)"),
]


def folder_id_from_link(link: str) -> str:
    """The folder ID in a Drive folder link the accountant pasted."""
    for pattern in _FOLDER_LINK:
        match = pattern.match(link.strip())
        if match:
            return match.group(1)
    raise ValueError("not a Google Drive folder link")


def version_of(entry: DriveEntry) -> str:
    """What makes two sightings of a file the same version.

    A file with an MD5 checksum is the same version while its bytes are the same, so a
    change to its modified time alone doesn't store a copy. A Google file has no
    checksum, so its modified time is used.
    """
    return f"md5:{entry.md5}" if entry.md5 else f"modified:{entry.modified_time.isoformat()}"


@dataclass
class DriveState:
    """Per grant, the version of each file last taken in or skipped:
    {(grant_id, file_id): version}."""

    taken: dict[tuple[str, str], str] = field(default_factory=dict)


def files_to_take(
    entries: list[DriveEntry], *, grant_id: str, state: DriveState, real_now: datetime
) -> list[DriveEntry]:
    """New or modified files that have stopped changing."""
    ready = []
    for entry in entries:
        if state.taken.get((grant_id, entry.id)) == version_of(entry):
            continue
        if real_now - entry.modified_time < SETTLE:
            continue  # still changing; looked at again on the next check
        ready.append(entry)
    return ready


def drive_file(
    source: DriveSource, entry: DriveEntry, *, grant_id: str, workspace_id: str
) -> IncomingFile:
    """Read one file. Raises `CannotTake` for a file that can't be taken in as it is."""
    if entry.mime_type in GOOGLE_EXPORTED_TYPES:
        data = source.export_pdf(entry.id)
        name = safe_name(entry.name, "export") + ".pdf"
        media_type = "application/pdf"
        exported_from = entry.mime_type
    elif entry.mime_type.startswith(GOOGLE_PREFIX):
        raise CannotTake(f"a Google file of type {entry.mime_type} can't be exported to PDF")
    else:
        if entry.size is not None and entry.size > MAX_FILE_BYTES:
            raise CannotTake("file over the size limit")
        data = source.download(entry.id)
        name = safe_name(entry.name, "file")
        media_type = entry.mime_type
        exported_from = None
    if len(data) > MAX_FILE_BYTES:
        raise CannotTake("file over the size limit")
    return IncomingFile(
        key=f"drive:{entry.id}:{version_of(entry)}",
        grant_id=grant_id,
        workspace_id=workspace_id,
        source="drive",
        name=name,
        media_type=media_type,
        data=data,
        # Drive's modified time is when the file was edited, not the document's own date.
        document_date=None,
        source_ref=entry.id,
        exported_from=exported_from,
    )
