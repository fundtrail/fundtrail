"""A sample's folder, read once into a `SamplePack`.

The folder layout is the seed builder's (W3), `data/samples/<sample>/`:

- `timeline.json`: `sample`, `starts_at` and `events`, scheduled events only. A sample, in
  every choice, opens at the start of its timeline: its first event.
- `user_actions.json`: what the do-everything play does, and when (optional).
- `sample.json`: the sample's own facts, such as its award number, and the option text
  (optional; kept as read until its shape is settled).
- `answer_key.json`: contracts.md section 14 (optional; read by the plays).
- The documents and `ledger.csv`, named by the events.

An event is one of:

- `file`: one document arriving, with `source` (`upload`, `gmail` or `drive`) and, for
  Gmail, `sender`. `"deliver": "user"` marks a file the user is expected to bring in
  (ruling 44): from its `at`, its date, it waits for the user until they deliver it. The
  clock never delivers it.
- `ledger`: the whole ledger file arriving. Each line arrives at the later of 00:00 UTC on
  its posting date and the event's time (decision 0023).
- `ledger_line`: one ledger line arriving at the event's time.

`user_actions.json` is the answer key's accountant script (ruling 47). Each action names
its target by stable references (a ledger line ID, a file name, a record kind and the
expected decision or values), never a record ID:

- `confirm_terms`: `file`
- `deliver_file`: `file`, marked for the user, on or after its date
- `decide_suggestion`: `suggestion` (the record kind suggested), `decision` (`accept` or
  `reject`), and a `line_id` or a `file`
- `answer_flag`: `line_id`, `answer`
- `enter_share`: `line_id`, `file` (the bill), `share`, `out_of`, `basis` (decision 0021)
- `let_in_mail`: `file`, a scheduled Gmail file held from an unknown sender (ruling 59)
- `accept_reason`: `note`, `check`, and optionally `problem`; about a `line_id`, a `file`,
  or neither for the grant itself (ruling 59)
- `sign_off`: `note` (ruling 59)

For every kind but `accept_reason` and `sign_off`, `note` is a comment on the step; for
those two it's the accountant's note, and it's needed.

The loader holds the script to the seed's own rules (ruling 51, as `data/test_seed.py`
checks them): an answer is supports, contradicts or unsure; a suggestion is a record kind
the agent suggests; a line is in the ledger and a file is on the timeline; an action about
a line comes after the line arrives, and one about a file after the file arrives (for a
file the user brings in, after the script brings it in); a share is a number from 0 to
`out_of`, and `out_of` is above 0.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from email import policy
from email.parser import BytesParser
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Any

from app.contracts.api import ArrivalSource
from app.contracts.records import RecordKind

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
    deliver_by_user: bool = False  # the user is expected to bring it in, from `at` on


@dataclass(frozen=True)
class UserAction:
    """One step of the accountant script, performed as the user would (ruling 47)."""

    at: datetime
    action: str  # one of ACTION_FIELDS
    file: str | None = None
    line_id: str | None = None
    suggestion: str | None = None  # decide_suggestion: the record kind suggested
    decision: str | None = None  # decide_suggestion: accept or reject
    answer: str | None = None  # answer_flag
    share: Decimal | None = None  # enter_share: the part of the bill, as `share` of `out_of`
    out_of: Decimal | None = None  # above 0, and at least `share`
    basis: str | None = None  # enter_share: why that share (decision 0021)
    check: str | None = None  # accept_reason: the reason's check
    problem: str | None = None  # accept_reason: the reason's problem, when the check has several
    # A comment on the step; for accept_reason and sign_off, the accountant's note.
    note: str | None = None


# The record kinds an agent's suggestion can be: the ones that wait for the accountant.
SUGGESTION_KINDS = frozenset(
    {
        RecordKind.LINK,
        RecordKind.JUDGMENT,
        RecordKind.CHECKLIST_REMOVAL,
        RecordKind.DISPUTE,
        RecordKind.DUPLICATE,
        RecordKind.CORRECTION,
        RecordKind.REMAINDER,
        RecordKind.RETRACTION,
    }
)
# The answers to a flag (contracts.md section 14).
ANSWERS = frozenset({"supports", "contradicts", "unsure"})

# Each action's fields besides `at` and `note`: the ones it needs, and the ones it may take.
ACTION_FIELDS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "confirm_terms": (frozenset({"file"}), frozenset()),
    "deliver_file": (frozenset({"file"}), frozenset()),
    "decide_suggestion": (frozenset({"suggestion", "decision"}), frozenset({"line_id", "file"})),
    "answer_flag": (frozenset({"line_id", "answer"}), frozenset()),
    "enter_share": (frozenset({"line_id", "file", "share", "out_of", "basis"}), frozenset()),
    "let_in_mail": (frozenset({"file"}), frozenset()),
    "accept_reason": (frozenset({"note", "check"}), frozenset({"problem", "line_id", "file"})),
    "sign_off": (frozenset({"note"}), frozenset()),
}
# The kinds whose note is the accountant's own, so it's needed.
NOTE_IS_THE_ACCOUNTANTS = frozenset({"accept_reason", "sign_off"})


@dataclass(frozen=True)
class SamplePack:
    sample: str
    folder: Path  # where timeline.json and the keys are
    files_folder: Path  # where the documents and the ledger are
    starts_at: datetime  # the clock's first "now": the first scheduled event
    events: tuple[ScheduledEvent, ...]  # in time order; ties keep the file's order
    actions: tuple[UserAction, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict[str, Any])  # sample.json, as read

    def event(self, event_id: str) -> ScheduledEvent | None:
        return next((e for e in self.events if e.id == event_id), None)

    def file_bytes(self, name: str) -> bytes:
        return _inside(self.files_folder, name).read_bytes()

    def message_id(self, name: str) -> str | None:
        """An email file's Message-ID header, without its angle brackets, if it has one."""
        if not name.lower().endswith(".eml"):
            return None
        return message_id_of(self.file_bytes(name))

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


def event_id(kind: EventKind, name: str) -> str:
    """An event's ID, from what it is, not where it sits in the file: a file's name or a
    ledger line's ID (each scheduled once), hashed so it's safe in a URL. Adding, removing
    or moving another event changes no other event's ID, and a ledger file's later line
    has the same ID as a `ledger_line` event for that line would."""
    key = "line" if kind is EventKind.LEDGER_LINE else kind.value
    digest = hashlib.sha256(f"{key}/{name}".encode()).hexdigest()[:16]
    return f"{key}-{digest}"


def message_id_of(raw: bytes) -> str | None:
    """An email's Message-ID header, without its angle brackets, if it has one."""
    headers = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
    value = str(headers.get("Message-ID") or "").strip().strip("<>").strip()
    return value or None


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


def _event(raw: dict[str, Any], where: str) -> ScheduledEvent:
    e = _parse_event(raw, where)
    return replace(e, id=event_id(e.kind, e.name))


def _parse_event(raw: dict[str, Any], where: str) -> ScheduledEvent:
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
            return ScheduledEvent(
                id="",
                at=at,
                kind=EventKind.FILE,
                source=source,
                name=str(raw.get("file") or ""),
                note=note,
                sender=raw.get("sender"),
                deliver_by_user=deliver == "user",
            )
        case "ledger":
            name = str(raw.get("file") or LEDGER_FILE)
            if name != LEDGER_FILE:
                raise PackError(f"{where}: the ledger file is {LEDGER_FILE}.")
            return ScheduledEvent("", at, EventKind.LEDGER, ArrivalSource.LEDGER, name, note)
        case "ledger_line":
            line_id = raw.get("line_id")
            if not isinstance(line_id, str) or not line_id:
                raise PackError(f"{where}: a ledger line needs its line_id.")
            return ScheduledEvent(
                "", at, EventKind.LEDGER_LINE, ArrivalSource.LEDGER, line_id, note
            )
        case kind:
            raise PackError(f"{where}: {kind!r} isn't a scheduled event.")


def _number(value: Any) -> Decimal | None:
    """A whole or decimal number, written as a number or as text; None for anything else."""
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _action(raw: dict[str, Any], where: str) -> UserAction:
    action = raw.get("action")
    if action not in ACTION_FIELDS:
        raise PackError(f"{where}: {action!r} isn't one of {sorted(ACTION_FIELDS)}.")
    required, optional = ACTION_FIELDS[action]
    given = set(raw) - {"at", "action"}
    if action not in NOTE_IS_THE_ACCOUNTANTS:
        given -= {"note"}
    if not required <= given or given - required - optional:
        raise PackError(
            f"{where}: {action} takes {sorted(required)}, and may take {sorted(optional)}."
        )
    if action == "decide_suggestion":
        if raw["decision"] not in ("accept", "reject"):
            raise PackError(f"{where}: a decision is accept or reject.")
        if not given & {"line_id", "file"}:
            raise PackError(f"{where}: a decision is about a line_id or a file.")
        if raw["suggestion"] not in SUGGESTION_KINDS:
            raise PackError(
                f"{where}: suggestion {raw['suggestion']!r} isn't one of "
                f"{sorted(k.value for k in SUGGESTION_KINDS)}."
            )
    if action == "answer_flag" and raw["answer"] not in ANSWERS:
        raise PackError(f"{where}: an answer is one of {sorted(ANSWERS)}.")
    for name in ("note", "check", "problem") if action in NOTE_IS_THE_ACCOUNTANTS else ():
        if name in raw and not (isinstance(raw[name], str) and raw[name].strip()):
            raise PackError(f"{where}: {name} is text that isn't empty.")
    if action == "accept_reason" and {"line_id", "file"} <= given:
        raise PackError(f"{where}: an accepted reason is about a line_id, a file, or the grant.")
    share = out_of = None
    if action == "enter_share":
        share, out_of = _number(raw["share"]), _number(raw["out_of"])
        if share is None or out_of is None or not (out_of > 0 and 0 <= share <= out_of):
            raise PackError(
                f"{where}: share and out_of are numbers, with out_of above 0 and the share "
                "from 0 to out_of."
            )
    text = {k: (str(raw[k]) if k in raw else None) for k in ("file", "line_id", "suggestion")}
    return UserAction(
        at=_time(raw.get("at"), where),
        action=action,
        file=text["file"],
        line_id=text["line_id"],
        suggestion=text["suggestion"],
        decision=raw.get("decision"),
        answer=raw.get("answer"),
        share=share,
        out_of=out_of,
        basis=raw.get("basis"),
        check=raw.get("check"),
        problem=raw.get("problem"),
        note=raw.get("note"),
    )


def _actions(raw: list[dict[str, Any]], where: str) -> tuple[UserAction, ...]:
    actions = [_action(a, f"{where}, action {n}") for n, a in enumerate(raw, start=1)]
    return tuple(sorted(actions, key=lambda a: a.at))


def _build(
    *,
    sample: str,
    folder: Path,
    files_folder: Path,
    raw_events: list[dict[str, Any]],
    starts_at: datetime | None,
    actions: tuple[UserAction, ...],
    meta: dict[str, Any],
    where: str,
) -> SamplePack:
    parsed = [_event(raw, f"{where}, event {n}") for n, raw in enumerate(raw_events, start=1)]
    if not parsed:
        raise PackError(f"{where}: the timeline has no events.")
    # A stable sort: events at the same time keep the file's order.
    events = tuple(sorted(parsed, key=lambda e: e.at))
    starts = events[0].at
    if starts_at is not None and starts_at != starts:
        raise PackError(f"{where}: starts_at isn't the first event's time.")
    pack = SamplePack(
        sample=sample,
        folder=folder,
        files_folder=files_folder,
        starts_at=starts,
        events=events,
        actions=actions,
        meta=meta,
    )
    _check(pack, where)
    return pack


def _check(pack: SamplePack, where: str) -> None:
    lines = set(pack.ledger_line_ids())
    seen_lines: set[str] = set()
    seen_files: set[str] = set()
    for e in pack.events:
        if e.kind is EventKind.LEDGER_LINE:
            if e.name not in lines:
                raise PackError(f"{where}: {LEDGER_FILE} has no line {e.name}.")
            if e.name in seen_lines:
                raise PackError(f"{where}: line {e.name} arrives twice.")
            seen_lines.add(e.name)
            continue
        if not _inside(pack.files_folder, e.name).is_file():
            raise PackError(f"{where}: {e.name} isn't in {pack.files_folder}.")
        # A file is scheduled once, so its name is its event's ID and a stable reference.
        if e.name in seen_files:
            raise PackError(f"{where}: {e.name} is scheduled twice.")
        seen_files.add(e.name)
    posted = _posting_midnights(pack)
    for e in pack.events:
        if e.kind is EventKind.LEDGER_LINE and e.at < posted[e.name]:
            raise PackError(f"{where}: line {e.name} arrives before its posting date.")
    if seen_lines and any(e.kind is EventKind.LEDGER for e in pack.events):
        raise PackError(f"{where}: a timeline has a ledger event or ledger_line events, not both.")
    _check_script(pack, where)


def _posting_midnights(pack: SamplePack) -> dict[str, datetime]:
    """00:00 UTC on each ledger line's posting date: the earliest it can arrive."""
    header, rows = pack._ledger_rows  # pyright: ignore[reportPrivateUsage]
    if "posting_date" not in header:
        raise PackError(f"{pack.files_folder}: {LEDGER_FILE} has no posting_date header.")
    column = header.index("posting_date")
    out: dict[str, datetime] = {}
    for line_id, row in rows.items():
        try:
            out[line_id] = datetime.combine(date.fromisoformat(row[column]), time(), tzinfo=UTC)
        except (IndexError, ValueError) as error:
            raise PackError(f"{pack.files_folder}: {line_id} has no posting date.") from error
    return out


def _line_arrivals(pack: SamplePack) -> dict[str, datetime]:
    """When each ledger line arrives: its `ledger_line` event, or the later of the ledger
    file's event and 00:00 UTC on its posting date (decision 0023)."""
    out = {e.name: e.at for e in pack.events if e.kind is EventKind.LEDGER_LINE}
    ledger = next((e for e in pack.events if e.kind is EventKind.LEDGER), None)
    if ledger is not None:
        for line_id, posting in _posting_midnights(pack).items():
            out[line_id] = max(posting, ledger.at)
    return out


def _attachments(pack: SamplePack) -> dict[str, ScheduledEvent]:
    """The scheduled Gmail events' attachments, as the player takes them in (email_parts),
    by the sha256 of their bytes: the event each first comes with."""
    from app.ingest.email_files import email_parts

    found: dict[str, ScheduledEvent] = {}
    for e in pack.events:
        if e.kind is not EventKind.FILE or e.source is not ArrivalSource.GMAIL:
            continue
        parts = email_parts(pack.file_bytes(e.name), message_id=e.id, grant_id="", workspace_id="")
        for f in parts.files[1:]:  # the message itself first, then its attachments
            found.setdefault(_sha256(f.data), e)
    return found


def _check_script(pack: SamplePack, where: str) -> None:
    """Each scripted action is possible at its time (ruling 51). A step's file is a
    scheduled file, or a file in the folder with the same bytes as an attachment of a
    scheduled Gmail event: that arrives with its email (when it's let in, if it's held),
    and it's never delivered or let in on its own."""
    files = {e.name: e for e in pack.events if e.kind is EventKind.FILE}
    lines = _line_arrivals(pack)
    brought = {a.file: a.at for a in pack.actions if a.action == "deliver_file"}
    let_in = {a.file: a.at for a in pack.actions if a.action == "let_in_mail"}
    attachments: dict[str, ScheduledEvent] | None = None
    for a in pack.actions:
        what = f"{where}: {a.action} at {a.at.isoformat()}"
        if a.line_id is not None:
            if a.line_id not in lines:
                raise PackError(f"{what}: {LEDGER_FILE} has no line {a.line_id}.")
            if a.at <= lines[a.line_id]:
                raise PackError(f"{what}: comes before line {a.line_id} arrives.")
        if a.file is None:
            continue
        event = files.get(a.file)
        if event is None:
            if not _inside(pack.files_folder, a.file).is_file():
                raise PackError(f"{what}: {a.file} isn't on the timeline.")
            if attachments is None:
                attachments = _attachments(pack)
            email = attachments.get(pack.sha256(a.file))
            if email is None:
                raise PackError(f"{what}: {a.file} isn't on the timeline.")
            if a.action in ("deliver_file", "let_in_mail"):
                raise PackError(f"{what}: {a.file} is an attachment of {email.name}.")
            if email.deliver_by_user:
                arrived = brought.get(email.name)
            else:
                arrived = let_in.get(email.name, email.at)
            if arrived is None or a.at <= arrived:
                raise PackError(f"{what}: comes before {a.file} arrives with {email.name}.")
            continue
        if a.action == "let_in_mail" and event.source.value != "gmail":
            raise PackError(f"{what}: {a.file} isn't a Gmail file, so it's never held.")
        if a.action == "deliver_file":
            if not event.deliver_by_user:
                raise PackError(f"{what}: {a.file} is delivered by the user but not marked so.")
            if a.at < event.at:
                raise PackError(f"{what}: {a.file} is delivered before its date.")
            continue
        arrived = brought.get(a.file) if event.deliver_by_user else event.at
        if arrived is None or a.at <= arrived:
            raise PackError(f"{what}: comes before {a.file} arrives.")


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
        actions=actions,
        meta=meta,
        where=where,
    )


def load_pack(sample: str, data_dir: Path = DATA_DIR) -> SamplePack:
    """The sample's pack, from `data/samples/<sample>/`. An unknown sample is a PackError."""
    folder = data_dir / "samples" / sample
    if not (folder / "timeline.json").is_file():
        raise PackError(f"There's no sample called {sample!r} in {data_dir / 'samples'}.")
    return load_folder(folder)
