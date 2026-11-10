"""A Drive folder tied to a grant by its link (decision 0025).

- A new file becomes an evidence file.
- A file Drive says was modified arrives as a new evidence file; the earlier one stays.
- A file still being edited is taken once it has stopped changing for `SETTLE`.
- A Google Doc, Sheet or Slides file is exported to PDF, and the export is marked.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .incoming import IncomingFile, safe_name
from .sources import GOOGLE_EXPORTED_TYPES, DriveEntry, DriveSource

# How long a file has to go without changing before it's taken in.
SETTLE = timedelta(minutes=10)

_FOLDER_LINK = [
    re.compile(r"drive\.google\.com/drive/(?:u/\d+/)?folders/([\w-]+)"),
    re.compile(r"drive\.google\.com/(?:open|folderview)\?(?:.*&)?id=([\w-]+)"),
]


def folder_id_from_link(link: str) -> str:
    """The folder ID in a Drive folder link the accountant pasted."""
    for pattern in _FOLDER_LINK:
        match = pattern.search(link)
        if match:
            return match.group(1)
    raise ValueError("not a Google Drive folder link")


def version_of(entry: DriveEntry) -> str:
    """What makes two sightings of a file the same version."""
    return f"{entry.modified_time.isoformat()}|{entry.md5 or ''}"


@dataclass
class DriveState:
    """The version of each file last taken in, per grant: {(grant_id, file_id): version}."""

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
    if entry.mime_type in GOOGLE_EXPORTED_TYPES:
        data = source.export_pdf(entry.id)
        name = safe_name(entry.name, "export") + ".pdf"
        media_type = "application/pdf"
        exported_from = entry.mime_type
    else:
        data = source.download(entry.id)
        name = safe_name(entry.name, "file")
        media_type = entry.mime_type
        exported_from = None
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
