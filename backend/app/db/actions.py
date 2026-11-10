"""What happens when something is put in: a grant, a ledger file, an evidence file, a record.

Each action runs in one transaction: it saves, reruns the checks with its trigger,
and queues the agent runs it calls for. Pings go out after the commit.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.contracts.api import LedgerUploadResult, RowError
from app.contracts.evidence import EvidenceFile, Source, storage_path
from app.contracts.records import TERM_KINDS, Author, Record, RecordData
from app.contracts.rules import check_new_record
from app.contracts.runs import AgentRun, Trigger, TriggerKind
from app.contracts.workspaces import Grant

from . import store
from .jobs import agent_questions_open, charge_batches, queue_run
from .pings import ping_changed, ping_run
from .platform import Platform
from .pool import transaction, workspace_now
from .recheck import recheck_grant


class WriteRejected(Exception):
    """The write check found problems. The API returns them with a 422."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Upload:
    name: str
    media_type: str
    data: bytes


def _new_id() -> str:
    return str(uuid.uuid4())


def _store_file(
    p: Platform, conn: store.Conn, grant: Grant, upload: Upload, now: datetime
) -> EvidenceFile:
    file_id = _new_id()
    name = upload.name.replace("/", "_").strip() or "file"
    f = EvidenceFile(
        id=file_id,
        workspace_id=grant.workspace_id,
        grant_id=grant.id,
        source=Source.UPLOAD,
        name=name,
        media_type=upload.media_type or "application/octet-stream",
        storage_path=storage_path(grant.workspace_id, grant.id, file_id, name),
        sha256=hashlib.sha256(upload.data).hexdigest(),
        arrived_at=now,
    )
    store.insert_file(conn, f)
    # Stored last, after the row passed its constraints. If the commit then fails, the
    # object is left without a row; nothing reads it.
    p.storage.put(f.storage_path, upload.data, f.media_type)
    return f


def _arrive_file(
    p: Platform, conn: store.Conn, grant: Grant, upload: Upload
) -> tuple[EvidenceFile, AgentRun]:
    now = workspace_now(store.workspace_by_id(conn, grant.workspace_id))
    store.get_grant(conn, grant.id, lock=True)
    f = _store_file(p, conn, grant, upload, now)
    trigger = Trigger(kind=TriggerKind.FILE, id=f.id)
    recheck_grant(conn, p.checks, grant, now, trigger)
    return f, queue_run(conn, grant, trigger, now)


def add_grant(p: Platform, workspace_id: str, award_letter: Upload) -> Grant:
    """A new grant from its award letter: the letter is stored as the grant's first file
    and an agent run is queued to read its terms."""
    with transaction(p.pool) as conn:
        grant = store.create_grant(conn, workspace_id)
        _, run = _arrive_file(p, conn, grant, award_letter)
    ping_run(p.pinger, run)
    ping_changed(p.pinger, grant.workspace_id, grant.id)
    return grant


def add_evidence(p: Platform, grant: Grant, upload: Upload) -> EvidenceFile:
    with transaction(p.pool) as conn:
        f, run = _arrive_file(p, conn, grant, upload)
    ping_run(p.pinger, run)
    ping_changed(p.pinger, grant.workspace_id, grant.id, "evidence", "statuses")
    return f


def add_ledger(p: Platform, grant: Grant, content: bytes) -> LedgerUploadResult:
    """Read a ledger file into charges. Lines already on file are skipped, and rows that
    can't be read are reported. Charges that have arrived by the clock's "now" get agent
    runs, one per batch of charges that arrived at the same moment; the rest wait for the clock."""
    from app.ingest.ledger import LedgerFileError, read_ledger_file

    runs: list[AgentRun] = []
    with transaction(p.pool) as conn:
        store.get_grant(conn, grant.id, lock=True)
        now = workspace_now(store.workspace_by_id(conn, grant.workspace_id))
        try:
            read = read_ledger_file(
                content,
                workspace_id=grant.workspace_id,
                grant_id=grant.id,
                existing_line_ids=store.ledger_line_ids(conn, grant.workspace_id),
                now=now,  # the reader applies decision 0023's arrival rule
            )
        except LedgerFileError as error:
            raise WriteRejected([str(error)]) from error
        charges = list(read.charges)
        store.insert_charges(conn, charges)
        arrived = [c for c in charges if c.arrived_at <= now]
        if arrived:
            triggers = {c.id: Trigger(kind=TriggerKind.CHARGE, id=c.id) for c in arrived}
            recheck_grant(
                conn, p.checks, grant, now, triggers[arrived[-1].id], charge_triggers=triggers
            )
            runs = [
                queue_run(conn, grant, triggers[batch[0].id], batch[0].arrived_at)
                for batch in charge_batches(arrived)
            ]
    for run in runs:
        ping_run(p.pinger, run)
    if charges:
        ping_changed(p.pinger, grant.workspace_id, grant.id, "charges", "statuses")
    return LedgerUploadResult(
        added=len(charges),
        already_present=len(read.skipped_line_ids),
        rejected=tuple(RowError(row=r.row, message=r.reason) for r in read.rejected),
    )


_record_data: TypeAdapter[Any] = TypeAdapter(RecordData)


def _fill_term_date(data: dict[str, Any], now: datetime) -> dict[str, Any]:
    """A term the accountant adds without a date, such as a known sender, is dated today
    by the workspace clock. Every term's `dated` is required."""
    if data.get("kind") in {k.value for k in TERM_KINDS} and not data.get("dated"):
        return data | {"dated": {"value": now.date().isoformat()}}
    return data


def add_record(
    p: Platform, grant: Grant, user_id: str, data: dict[str, Any], replaces_id: str | None
) -> Record:
    """The accountant's record: checked by the write check, saved, then the checks rerun.

    When the record leaves a question open for the agent and no run is waiting, a run
    is queued with this record as its trigger.
    """
    run: AgentRun | None = None
    with transaction(p.pool) as conn:
        store.get_grant(conn, grant.id, lock=True)
        now = workspace_now(store.workspace_by_id(conn, grant.workspace_id))
        try:
            record = Record(
                id=_new_id(),
                workspace_id=grant.workspace_id,
                grant_id=grant.id,
                author=Author.USER,
                author_user_id=user_id,
                written_at=now,
                replaces_id=replaces_id,
                data=_record_data.validate_python(_fill_term_date(data, now)),
            )
        except ValidationError as error:
            raise WriteRejected(
                [e["msg"] + f" ({'.'.join(map(str, e['loc']))})" for e in error.errors()]
            ) from error
        records = store.list_records(conn, grant.id, now)
        problems = check_new_record(
            record,
            records,
            store.list_charges(conn, grant.id, now),
            store.list_files(conn, grant.id, now),
            default_items=p.checks.default_items,
        )
        if problems:
            raise WriteRejected(problems)
        store.insert_records(conn, [record])
        trigger = Trigger(kind=TriggerKind.RECORD, id=record.id)
        output = recheck_grant(conn, p.checks, grant, now, trigger)
        # Queued whether or not a run is in progress; a queued run that hasn't started
        # reads this record when it starts, so it's shared (the run-order ruling, 5).
        if agent_questions_open(output.questions) and not store.has_queued_run(conn, grant.id):
            run = queue_run(conn, grant, trigger, now)
    if run is not None:
        ping_run(p.pinger, run)
    ping_changed(p.pinger, grant.workspace_id, grant.id, "records", "statuses")
    return record
