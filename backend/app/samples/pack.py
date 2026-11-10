"""A sample's folder, read once into a `SamplePack`.

The folder layout is the seed builder's (W3), `data/samples/<sample>/`:

- `timeline.json`: `sample`, `starts_at`, `opens_at` and `events`, scheduled events only.
- `user_actions.json`: what the do-everything play does, and when (optional).
- `sample.json`: the sample's own facts, such as its award number, and the option text
  (optional; kept as read until its shape is settled).
- `answer_key.json`: contracts.md section 14 (optional; read by the plays).
- The documents and `ledger.csv`, named by the events.

An event is one of:

- `file`: one document arriving, with `source` (`upload`, `gmail` or `drive`) and, for
  Gmail, `sender`. `"deliver": "user"` marks a file the user is expected to bring in;
  its `at` is the clock's fallback. `available_at` (optional) is when the user can first
  deliver it; without it, the sample's opening.
- `ledger`: the whole ledger file arriving. Each line arrives at the later of 00:00 UTC on
  its posting date and the event's time (decision 0023).
- `ledger_line`: one ledger line arriving at the event's time.

Until the seed builder's `data/samples/` lands, the two samples are read from today's
layout (`data/demo/salt-marsh-carbon/` and `data/from-scratch/`, each with an
`arrivals.json`). Their `accountant` events aren't scheduled events: they become the
user actions the do-everything play performs.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Any

from app.contracts.api import ArrivalSource

# The repo's data folder: backend/app/samples/pack.py -> the repo root -> data.
DATA_DIR = Path(__file__).resolve().parents[3] / "data"

LEDGER_FILE = "ledger.csv"

# The two samples. The small one is read live; the larger one is read live or prerun.
SMALL_SAMPLE = "nitrate-sensors"
LARGER_SAMPLE = "salt-marsh-carbon"

_FILE_SOURCES = {
    "upload": ArrivalSource.UPLOAD,
    "gmail": ArrivalSource.GMAIL,
    "drive": ArrivalSource.DRIVE,
}


class PackError(ValueError):
    """A sample folder that can't be read. The message names the folder and what's wrong."""


class EventKind(StrEnum):
    FILE = "file"
    LEDGER = "ledger"
    LEDGER_LINE = "ledger_line"


@dataclass(frozen=True)
class ScheduledEvent:
    """One scheduled event. `id` is stable for the pack: the same on every load."""

    id: str
    at: datetime
    kind: EventKind
    source: ArrivalSource  # `ledger` for the ledger file and its lines
    name: str  # the file name, or the ledger line ID
    note: str | None = None
    sender: str | None = None  # for Gmail
    deliver_by_user: bool = False  # the user is expected to bring it in; `at` is the fallback
    available_at: datetime | None = None  # for a user delivery: when the user can first bring it


@dataclass(frozen=True)
class UserAction:
    """One action the do-everything play performs, as the user would."""

    at: datetime
    action: str  # confirm_terms or deliver_file, for now
    file: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class SamplePack:
    sample: str
    folder: Path  # where timeline.json (or arrivals.json) and the keys are
    files_folder: Path  # where the documents and the ledger are
    starts_at: datetime  # the clock's first "now": the first scheduled event
    opens_at: datetime  # the simulated opening date
    events: tuple[ScheduledEvent, ...]  # in time order; ties keep the file's order
    actions: tuple[UserAction, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict[str, Any])  # sample.json, as read

    def event(self, event_id: str) -> ScheduledEvent | None:
        return next((e for e in self.events if e.id == event_id), None)

    def file_bytes(self, name: str) -> bytes:
        return _inside(self.files_folder, name).read_bytes()

    def sha256(self, name: str) -> str:
        return self._hashes[name] if name in self._hashes else _sha256(self.file_bytes(name))

    @cached_property
    def _hashes(self) -> dict[str, str]:
        names = {e.name for e in self.events if e.kind is EventKind.FILE}
        return {name: _sha256(self.file_bytes(name)) for name in names}

    def ledger_bytes(self) -> bytes:
        return self.file_bytes(LEDGER_FILE)

    @cached_property
    def _ledger_rows(self) -> tuple[list[str], dict[str, list[str]]]:
        text = self.ledger_bytes().decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        if not rows or "line_id" not in rows[0]:
            raise PackError(f"{self.files_folder}: {LEDGER_FILE} has no line_id header.")
        header, index = rows[0], rows[0].index("line_id")
        return header, {row[index]: row for row in rows[1:] if len(row) > index and row[index]}

    def ledger_line_ids(self) -> list[str]:
        return list(self._ledger_rows[1])

    def ledger_row(self, line_id: str) -> bytes:
        """A ledger file holding only this line, with the header: what a `ledger_line`
        event uploads."""
        header, rows = self._ledger_rows
        if line_id not in rows:
            raise PackError(f"{self.files_folder}: {LEDGER_FILE} has no line {line_id}.")
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(header)
        writer.writerow(rows[line_id])
        return out.getvalue().encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inside(folder: Path, name: str) -> Path:
    """The file `name` directly inside `folder`. A name with a path in it is refused."""
    if not name or Path(name).name != name or name in {".", ".."}:
        raise PackError(f"{folder}: {name!r} isn't a plain file name.")
    return folder / name


def _time(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise PackError(f"{where}: a time must be a string.")
    try:
        at = datetime.fromisoformat(value)
    except ValueError as error:
        raise PackError(f"{where}: {value!r} isn't a time.") from error
    if at.tzinfo is None:
        raise PackError(f"{where}: {value!r} has no time zone.")
    return at


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PackError(f"{path}: {error}") from error


def _event(raw: dict[str, Any], event_id: str, where: str) -> ScheduledEvent:
    at = _time(raw.get("at"), where)
    note = raw.get("note")
    match raw.get("kind"):
        case "file":
            source = _FILE_SOURCES.get(raw.get("source", ""))
            if source is None:
                raise PackError(f"{where}: a file's source is upload, gmail or drive.")
            deliver = raw.get("deliver")
            if deliver not in (None, "user"):
                raise PackError(f'{where}: deliver is "user" or left out.')
            available = raw.get("available_at")
            if available is not None and deliver != "user":
                raise PackError(f"{where}: available_at is only for a file the user delivers.")
            return ScheduledEvent(
                id=event_id,
                at=at,
                kind=EventKind.FILE,
                source=source,
                name=str(raw.get("file") or ""),
                note=note,
                sender=raw.get("sender"),
                deliver_by_user=deliver == "user",
                available_at=_time(available, where) if available is not None else None,
            )
        case "ledger":
            name = str(raw.get("file") or LEDGER_FILE)
            if name != LEDGER_FILE:
                raise PackError(f"{where}: the ledger file is {LEDGER_FILE}.")
            return ScheduledEvent(event_id, at, EventKind.LEDGER, ArrivalSource.LEDGER, name, note)
        case "ledger_line":
            line_id = raw.get("line_id")
            if not isinstance(line_id, str) or not line_id:
                raise PackError(f"{where}: a ledger line needs its line_id.")
            return ScheduledEvent(
                event_id, at, EventKind.LEDGER_LINE, ArrivalSource.LEDGER, line_id, note
            )
        case kind:
            raise PackError(f"{where}: {kind!r} isn't a scheduled event.")


def _actions(raw: list[dict[str, Any]], where: str) -> tuple[UserAction, ...]:
    actions = [
        UserAction(
            at=_time(a.get("at"), f"{where}, action {n}"),
            action=str(a.get("action") or ""),
            file=a.get("file"),
            note=a.get("note"),
        )
        for n, a in enumerate(raw, start=1)
    ]
    return tuple(sorted(actions, key=lambda a: a.at))


def _build(
    *,
    sample: str,
    folder: Path,
    files_folder: Path,
    raw_events: list[dict[str, Any]],
    starts_at: datetime | None,
    opens_at: datetime | None,
    actions: tuple[UserAction, ...],
    meta: dict[str, Any],
    where: str,
) -> SamplePack:
    numbered = [
        _event(raw, f"e{n:03d}", f"{where}, event {n}") for n, raw in enumerate(raw_events, start=1)
    ]
    if not numbered:
        raise PackError(f"{where}: the timeline has no events.")
    # A stable sort: events at the same time keep the file's order, and each keeps the ID
    # its place in the file gave it.
    events = tuple(sorted(numbered, key=lambda e: e.at))
    starts = starts_at or events[0].at
    opens = opens_at or starts
    pack = SamplePack(
        sample=sample,
        folder=folder,
        files_folder=files_folder,
        starts_at=starts,
        opens_at=opens,
        events=events,
        actions=actions,
        meta=meta,
    )
    _check(pack, where)
    return pack


def _check(pack: SamplePack, where: str) -> None:
    if pack.opens_at < pack.starts_at:
        raise PackError(f"{where}: it opens before it starts.")
    if pack.events[0].at < pack.starts_at:
        raise PackError(f"{where}: an event comes before the sample starts.")
    lines = set(pack.ledger_line_ids())
    seen_lines: set[str] = set()
    for e in pack.events:
        if e.kind is EventKind.LEDGER_LINE:
            if e.name not in lines:
                raise PackError(f"{where}: {LEDGER_FILE} has no line {e.name}.")
            if e.name in seen_lines:
                raise PackError(f"{where}: line {e.name} arrives twice.")
            seen_lines.add(e.name)
        elif not _inside(pack.files_folder, e.name).is_file():
            raise PackError(f"{where}: {e.name} isn't in {pack.files_folder}.")
        if e.available_at is not None and e.available_at > e.at:
            raise PackError(f"{where}: {e.name} is available only after the clock delivers it.")
    if seen_lines and any(e.kind is EventKind.LEDGER for e in pack.events):
        raise PackError(f"{where}: a timeline has a ledger event or ledger_line events, not both.")
    delivered = {e.name for e in pack.events if e.deliver_by_user}
    for a in pack.actions:
        if a.action == "deliver_file" and a.file not in delivered:
            raise PackError(f"{where}: {a.file} is delivered by the user but not marked so.")


def load_folder(folder: Path) -> SamplePack:
    """Read a sample folder in the seed builder's layout (`timeline.json` and the rest)."""
    timeline = _read_json(folder / "timeline.json")
    where = str(folder / "timeline.json")
    sample = timeline.get("sample") or folder.name
    actions_path = folder / "user_actions.json"
    actions: tuple[UserAction, ...] = ()
    if actions_path.is_file():
        actions = _actions(_read_json(actions_path).get("actions", []), str(actions_path))
    meta_path = folder / "sample.json"
    meta = _read_json(meta_path) if meta_path.is_file() else {}
    raw_events = timeline.get("events", [])
    if any(e.get("kind") == "accountant" for e in raw_events):
        raise PackError(f"{where}: a decision is the user's, never a scheduled event.")
    return _build(
        sample=sample,
        folder=folder,
        files_folder=folder,
        raw_events=raw_events,
        starts_at=_time(timeline["starts_at"], where) if "starts_at" in timeline else None,
        opens_at=_time(timeline["opens_at"], where) if "opens_at" in timeline else None,
        actions=actions,
        meta=meta,
        where=where,
    )


# Today's layout, until data/samples/ lands: the folder, where its files are, and where its
# opening date comes from (the demo seed's opening, or its first event).
_LEGACY = {
    LARGER_SAMPLE: ("demo/salt-marsh-carbon", "", "demo/seed.json"),
    SMALL_SAMPLE: ("from-scratch", "pack", None),
}


def _load_legacy(data_dir: Path, sample: str) -> SamplePack:
    folder_name, files_name, opening_file = _LEGACY[sample]
    folder = data_dir / folder_name
    where = str(folder / "arrivals.json")
    raw = _read_json(folder / "arrivals.json").get("events", [])
    scheduled = [e for e in raw if e.get("kind") != "accountant"]
    actions = _actions([e for e in raw if e.get("kind") == "accountant"], where)
    opens_at = None
    if opening_file is not None:
        opens_at = _time(_read_json(data_dir / opening_file).get("opening_at"), opening_file)
    return _build(
        sample=sample,
        folder=folder,
        files_folder=folder / files_name if files_name else folder,
        raw_events=scheduled,
        starts_at=None,
        opens_at=opens_at,
        actions=actions,
        meta={},
        where=where,
    )


def load_pack(sample: str, data_dir: Path = DATA_DIR) -> SamplePack:
    """The sample's pack: from `data/samples/<sample>/` when it's there, else from today's
    layout. An unknown sample is a PackError."""
    folder = data_dir / "samples" / sample
    if (folder / "timeline.json").is_file():
        return load_folder(folder)
    if sample in _LEGACY:
        return _load_legacy(data_dir, sample)
    raise PackError(f"There's no sample called {sample!r} in {data_dir}.")
