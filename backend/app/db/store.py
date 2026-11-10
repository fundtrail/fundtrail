"""Database access: rows in and out of the first migration's tables, as contract models.

Every function takes an open psycopg connection; the caller owns the transaction.
Connections use dict rows (see `pool.py`).

Nothing here decides what counts. Lists return everything visible at a clock time,
in the order written, and callers apply `app.contracts.rules` to them.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, LiteralString

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.contracts.charges import Charge
from app.contracts.checks import ChargeStatus, GrantStatus, RecordStatus
from app.contracts.evidence import EvidenceFile
from app.contracts.mail import CheckerProgress, HeldMail, SkippedFile
from app.contracts.records import Record
from app.contracts.runs import AgentRun, RunStatus, Trigger, TriggerKind
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant, User, Workspace

type Conn = Connection[dict[str, Any]]

_P13 = "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s"
_P14 = "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s"


def _clean(row: dict[str, Any], *drop: str) -> dict[str, Any]:
    out = {k: v for k, v in row.items() if k not in drop}
    for k, v in out.items():
        if hasattr(v, "hex") and k.endswith(("id", "_id")) and not isinstance(v, str):
            out[k] = str(v)  # uuid columns come back as UUID objects
    return out


# Users, workspaces and grants.


def upsert_user(conn: Conn, user: User) -> User:
    """The users row for a signed-in Supabase user, written only the first time they're seen."""
    conn.execute(
        """insert into public.users (id, email, name) values (%s, %s, %s)
           on conflict (id) do nothing""",
        (user.id, user.email, user.name),
    )
    return user


def reaches(kind: Literal["workspace", "grant"], column: LiteralString) -> LiteralString:
    """The one access rule, as a SQL condition on `column` for a user ID parameter: whether
    the user may reach that workspace or grant (issue 160). It asks the migration's
    private.can_reach_workspace / private.can_reach_grant, the functions the Realtime
    policy asks too, so a later rule changes in one place."""
    return f"private.can_reach_{kind}({column}, %s::uuid)"


def list_workspaces(conn: Conn, user_id: str) -> list[Workspace]:
    """The workspaces this user may reach."""
    rows = conn.execute(
        "select id, name, owner_id from public.workspaces"
        f" where {reaches('workspace', 'id')} order by name, id",
        (user_id,),
    ).fetchall()
    return [Workspace.model_validate(_clean(r)) for r in rows]


def create_workspace(conn: Conn, owner_id: str, name: str) -> Workspace:
    """A new workspace. The database adds its creator as its owner member, and its Sample
    accountant, in the same transaction."""
    row = conn.execute(
        "insert into public.workspaces (owner_id, name) values (%s, %s)"
        " returning id, name, owner_id",
        (owner_id, name),
    ).fetchone()
    assert row is not None
    return Workspace.model_validate(_clean(row))


def get_workspace(conn: Conn, workspace_id: str, user_id: str) -> Workspace | None:
    """The workspace, only if this user may reach it."""
    row = conn.execute(
        "select id, name, owner_id from public.workspaces"
        f" where id = %s and {reaches('workspace', 'id')}",
        (workspace_id, user_id),
    ).fetchone()
    return Workspace.model_validate(_clean(row)) if row else None


def workspace_by_id(conn: Conn, workspace_id: str) -> Workspace:
    row = conn.execute(
        "select id, name, owner_id from public.workspaces where id = %s", (workspace_id,)
    ).fetchone()
    assert row is not None
    return Workspace.model_validate(_clean(row))


# A grant's columns. `clock_now` is a sample grant's stored clock (read through the clock
# module), and `sample` says what it was opened from.
_GRANT_COLUMNS: LiteralString = (
    "id, workspace_id, funder, award_number, title, address_code, drive_folder_id,"
    " clock_now, sample"
)


def create_grant(conn: Conn, workspace_id: str) -> Grant:
    row = conn.execute(
        f"insert into public.grants (workspace_id) values (%s) returning {_GRANT_COLUMNS}",
        (workspace_id,),
    ).fetchone()
    assert row is not None
    return Grant.model_validate(row)


def list_grants(conn: Conn, workspace_id: str) -> list[Grant]:
    rows = conn.execute(
        f"select {_GRANT_COLUMNS} from public.grants where workspace_id = %s order by id",
        (workspace_id,),
    ).fetchall()
    return [Grant.model_validate(r) for r in rows]


def get_grant(
    conn: Conn, grant_id: str, user_id: str | None = None, *, lock: bool = False
) -> Grant | None:
    """The grant; with user_id, only if that user may reach it.

    lock=True takes the grant's row lock until the transaction ends. Every write to a
    grant's records takes it, so the write check and the save see the same records.
    """
    query: LiteralString = f"select {_GRANT_COLUMNS} from public.grants g where g.id = %s"
    params: tuple[str, ...] = (grant_id,)
    if user_id is not None:
        query += f" and {reaches('grant', 'g.id')}"
        params += (user_id,)
    if lock:
        query += " for update of g"
    row = conn.execute(query, params).fetchone()
    return Grant.model_validate(row) if row else None


# Charges.

_CHARGE_COLUMNS = (
    "id, workspace_id, grant_id, ledger_line_id, transaction_date, posting_date, arrived_at, "
    "amount_cents, description, account, vendor, reference, original_line_id"
)


def ledger_line_ids(conn: Conn, grant_id: str) -> set[str]:
    """Every ledger line ID on file for the grant, arrived or not: a line is matched once.

    Line IDs are unique per grant, so another grant's lines never count here.
    """
    rows = conn.execute(
        "select ledger_line_id from public.charges where grant_id = %s", (grant_id,)
    ).fetchall()
    return {r["ledger_line_id"] for r in rows}


def insert_charges(conn: Conn, charges: Sequence[Charge]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            f"insert into public.charges ({_CHARGE_COLUMNS}) values ({_P13})",
            [
                (
                    c.id,
                    c.workspace_id,
                    c.grant_id,
                    c.ledger_line_id,
                    c.transaction_date,
                    c.posting_date,
                    c.arrived_at,
                    c.amount_cents,
                    c.description,
                    c.account,
                    c.vendor,
                    c.reference,
                    c.original_line_id,
                )
                for c in charges
            ],
        )


def list_charges(conn: Conn, grant_id: str, now: datetime) -> list[Charge]:
    """The grant's charges that have arrived by now: posting date, then ledger line ID."""
    rows = conn.execute(
        f"""select {_CHARGE_COLUMNS}, stored_seq from public.charges
            where grant_id = %s and arrived_at <= %s
            order by posting_date, ledger_line_id""",
        (grant_id, now),
    ).fetchall()
    return [Charge.model_validate(r) for r in rows]


# Evidence files.

_FILE_COLUMNS = (
    "id, workspace_id, grant_id, source, name, media_type, storage_path, sha256, document_date, "
    "arrived_at, sender, source_ref, parent_id, exported_from"
)


_FILE_COLUMNS_F = (
    "f.id, f.workspace_id, f.grant_id, f.source, f.name, f.media_type, f.storage_path, "
    "f.sha256, f.document_date, f.arrived_at, f.sender, f.source_ref, f.parent_id, "
    "f.exported_from"
)


def insert_file(conn: Conn, f: EvidenceFile) -> None:
    conn.execute(
        f"insert into public.evidence_files ({_FILE_COLUMNS}) values ({_P14})",
        (
            f.id,
            f.workspace_id,
            f.grant_id,
            f.source.value,
            f.name,
            f.media_type,
            f.storage_path,
            f.sha256,
            f.document_date,
            f.arrived_at,
            f.sender,
            f.source_ref,
            f.parent_id,
            f.exported_from,
        ),
    )


def list_files(conn: Conn, grant_id: str, now: datetime) -> list[EvidenceFile]:
    rows = conn.execute(
        f"""select {_FILE_COLUMNS}, stored_seq from public.evidence_files
            where grant_id = %s and arrived_at <= %s
            order by arrived_at, id""",
        (grant_id, now),
    ).fetchall()
    return [EvidenceFile.model_validate(r) for r in rows]


def get_file(conn: Conn, file_id: str, user_id: str) -> EvidenceFile | None:
    """The file, only if this user may reach its grant."""
    row = conn.execute(
        f"""select {_FILE_COLUMNS_F}, f.stored_seq
            from public.evidence_files f
            where f.id = %s and {reaches("grant", "f.grant_id")}""",
        (file_id, user_id),
    ).fetchone()
    return EvidenceFile.model_validate(row) if row else None


# Records.


def _record(row: dict[str, Any]) -> Record:
    return Record.model_validate(
        {
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "grant_id": row["grant_id"],
            "author": row["author"],
            "author_user_id": str(row["author_user_id"]) if row["author_user_id"] else None,
            "written_at": row["written_at"],
            "replaces_id": row["replaces_id"],
            "thread_message_id": row["thread_message_id"],
            "stored_seq": row["stored_seq"],
            "read_through_seq": row["read_through_seq"],
            "data": row["data"],
        }
    )


def list_records(conn: Conn, grant_id: str, now: datetime | None = None) -> list[Record]:
    """The grant's records, replaced, waiting and rejected ones included, in the order they
    were stored. A record's date never orders records (the run-order ruling); `now`, when
    given, leaves out records dated after it."""
    rows = conn.execute(
        """select id, workspace_id, grant_id, author, author_user_id, written_at, replaces_id,
                  thread_message_id, stored_seq, read_through_seq, data
           from public.records where grant_id = %s and (%s::timestamptz is null or written_at <= %s)
           order by stored_seq""",
        (grant_id, now, now),
    ).fetchall()
    return [_record(r) for r in rows]


def insert_records(conn: Conn, records: Sequence[Record]) -> list[Record]:
    """Insert in order. The database gives each its stored_seq (#70), the one stored order;
    it's never sent. Returns the records as stored, each with its stored_seq."""
    stored: list[Record] = []
    for r in records:
        row = conn.execute(
            """insert into public.records
                 (id, workspace_id, grant_id, author, author_user_id, written_at, replaces_id,
                  thread_message_id, read_through_seq, data, created_at)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, clock_timestamp())
               returning stored_seq""",
            (
                r.id,
                r.workspace_id,
                r.grant_id,
                r.author.value,
                r.author_user_id,
                r.written_at,
                r.replaces_id,
                r.thread_message_id,
                r.read_through_seq,
                Jsonb(r.data.model_dump(mode="json")),
            ),
        ).fetchone()
        assert row is not None
        stored.append(r.model_copy(update={"stored_seq": row["stored_seq"]}))
    return stored


# Agent runs.

_RUN_COLUMNS = (
    "id, workspace_id, grant_id, trigger_kind, trigger_id, status, clock_now, queued_at, "
    "started_at, finished_at, summary, error, log_path, thread_charge_id, thread_record_id, "
    "read_through_seq"
)


def _run(row: dict[str, Any]) -> AgentRun:
    data = dict(row)
    data["trigger"] = Trigger(kind=TriggerKind(data.pop("trigger_kind")), id=data.pop("trigger_id"))
    return AgentRun.model_validate(data)


def insert_run(
    conn: Conn,
    workspace_id: str,
    grant_id: str,
    trigger: Trigger,
    clock_now: datetime,
    *,
    thread_charge_id: str | None = None,
    thread_record_id: str | None = None,
) -> AgentRun:
    """A queued run. A run a thread message starts names the thread's charge or record."""
    row = conn.execute(
        f"""insert into public.agent_runs
              (workspace_id, grant_id, trigger_kind, trigger_id, clock_now,
               thread_charge_id, thread_record_id)
            values (%s, %s, %s, %s, %s, %s, %s) returning {_RUN_COLUMNS}""",
        (
            workspace_id,
            grant_id,
            trigger.kind.value,
            trigger.id,
            clock_now,
            thread_charge_id,
            thread_record_id,
        ),
    ).fetchone()
    assert row is not None
    return _run(row)


def get_run(conn: Conn, run_id: str, *, lock: bool = False) -> AgentRun | None:
    query = f"select {_RUN_COLUMNS} from public.agent_runs where id = %s"
    if lock:
        query += " for update"
    row = conn.execute(query, (run_id,)).fetchone()  # pyright: ignore[reportArgumentType]
    return _run(row) if row else None


def list_runs(conn: Conn, grant_id: str) -> list[AgentRun]:
    """The grant's runs, newest first."""
    rows = conn.execute(
        f"select {_RUN_COLUMNS} from public.agent_runs"
        " where grant_id = %s order by queued_at desc, id desc",
        (grant_id,),
    ).fetchall()
    return [_run(r) for r in rows]


def failed_runs(conn: Conn, grant_id: str) -> list[AgentRun]:
    rows = conn.execute(
        f"select {_RUN_COLUMNS} from public.agent_runs"
        " where grant_id = %s and status = 'failed' order by queued_at",
        (grant_id,),
    ).fetchall()
    return [_run(r) for r in rows]


def set_run(
    conn: Conn,
    run_id: str,
    status: RunStatus,
    *,
    started: bool = False,
    finished: bool = False,
    summary: str | None = None,
    error: str | None = None,
    log_path: str | None = None,
    clock_now: datetime | None = None,
) -> None:
    conn.execute(
        """update public.agent_runs set status = %s,
             started_at = case when %s and started_at is null then now() else started_at end,
             finished_at = case when %s then now() else finished_at end,
             summary = coalesce(%s, summary), error = %s,
             log_path = coalesce(%s, log_path),
             clock_now = coalesce(%s, clock_now)
           where id = %s""",
        (status.value, started, finished, summary, error, log_path, clock_now, run_id),
    )


def other_running_runs(conn: Conn, grant_id: str, run_id: str) -> list[str]:
    rows = conn.execute(
        "select id from public.agent_runs where grant_id = %s and status = 'running' and id <> %s",
        (grant_id, run_id),
    ).fetchall()
    return [r["id"] for r in rows]


def has_queued_run(conn: Conn, grant_id: str) -> bool:
    """Whether a run on the grant is queued and hasn't started: it will read everything
    stored when it starts, so a new record can share it.

    The queued run's row is locked until the caller's transaction ends. A run's start
    takes the same row lock, so it waits for the record to commit and then reads it.
    """
    row = conn.execute(
        """select id from public.agent_runs where grant_id = %s and status = 'queued'
           limit 1 for update""",
        (grant_id,),
    ).fetchone()
    return row is not None


def has_pending_run(conn: Conn, grant_id: str) -> bool:
    row = conn.execute(
        "select 1 from public.agent_runs"
        " where grant_id = %s and status in ('queued', 'running') limit 1",
        (grant_id,),
    ).fetchone()
    return row is not None


# Thread messages.

_MESSAGE_COLUMNS = (
    "id, workspace_id, grant_id, charge_id, record_id, author, author_user_id, run_id, text, "
    "written_at"
)


def _message(row: dict[str, Any]) -> ThreadMessage:
    return ThreadMessage.model_validate(_clean(row))


def insert_messages(conn: Conn, messages: Sequence[ThreadMessage]) -> None:
    for m in messages:
        conn.execute(
            f"""insert into public.thread_messages ({_MESSAGE_COLUMNS}, created_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, clock_timestamp())""",
            (
                m.id,
                m.workspace_id,
                m.grant_id,
                m.charge_id,
                m.record_id,
                m.author.value,
                m.author_user_id,
                m.run_id,
                m.text,
                m.written_at,
            ),
        )


def get_message(conn: Conn, message_id: str) -> ThreadMessage | None:
    row = conn.execute(
        f"select {_MESSAGE_COLUMNS} from public.thread_messages where id = %s", (message_id,)
    ).fetchone()
    return _message(row) if row else None


def list_thread(
    conn: Conn, *, charge_id: str | None = None, record_id: str | None = None
) -> list[ThreadMessage]:
    """One thread, oldest first."""
    rows = conn.execute(
        f"""select {_MESSAGE_COLUMNS} from public.thread_messages
            where (%s::text is not null and charge_id = %s)
               or (%s::text is not null and record_id = %s)
            order by written_at, created_at, id""",
        (charge_id, charge_id, record_id, record_id),
    ).fetchall()
    return [_message(r) for r in rows]


# Statuses.

type Status = ChargeStatus | RecordStatus | GrantStatus


def status_key(status: Status) -> tuple[str, str | None]:
    """What a status is about: ("charge", id), ("record", id), ("file", id) or ("grant", None)."""
    if isinstance(status, ChargeStatus):
        return ("charge", status.charge_id)
    if isinstance(status, RecordStatus):
        return ("record", status.record_id) if status.record_id else ("file", status.file_id)
    return ("grant", None)


def _status_columns(status: Status) -> dict[str, Any]:
    if isinstance(status, ChargeStatus):
        return {
            "charge_id": status.charge_id,
            "record_id": None,
            "file_id": None,
            "bucket": status.bucket.value,
            "reasons": [r.model_dump(mode="json") for r in status.reasons],
            "checklist": [c.model_dump(mode="json") for c in status.checklist],
            "problems": None,
            "net_cents": status.net_cents,
            "corrections": list(status.corrections),
            "reversed": status.reversed,
            "flagged": status.flagged,
            "rechecking": status.rechecking,
            "accepted": status.accepted,
            "snoozed": status.snoozed,
        }
    return {
        "charge_id": None,
        "record_id": status.record_id if isinstance(status, RecordStatus) else None,
        "file_id": status.file_id if isinstance(status, RecordStatus) else None,
        "bucket": None,
        "reasons": None,
        "checklist": None,
        "problems": [p.model_dump(mode="json") for p in status.problems],
        "net_cents": None,
        "corrections": [],
        "reversed": False,
        "flagged": status.flagged,
        "rechecking": False,
        "accepted": status.accepted,
        "snoozed": status.snoozed,
    }


def _status_from_row(row: dict[str, Any]) -> Status:
    common = {
        "grant_id": row["grant_id"],
        "flagged": row["flagged"],
        "accepted": row["accepted"],
        "snoozed": row["snoozed"],
    }
    if row["charge_id"]:
        return ChargeStatus.model_validate(
            common
            | {
                "charge_id": row["charge_id"],
                "bucket": row["bucket"],
                "reasons": row["reasons"],
                "checklist": row["checklist"],
                "rechecking": row["rechecking"],
                "net_cents": row["net_cents"],
                "corrections": row["corrections"],
                "reversed": row["reversed"],
            }
        )
    if row["record_id"] or row["file_id"]:
        return RecordStatus.model_validate(
            common
            | {
                "record_id": row["record_id"],
                "file_id": row["file_id"],
                "problems": row["problems"],
            }
        )
    return GrantStatus.model_validate(common | {"problems": row["problems"]})


def current_statuses(conn: Conn, grant_id: str) -> dict[tuple[str, str | None], Status]:
    """The latest status of everything on the grant that has one."""
    rows = conn.execute(
        """select grant_id, charge_id, record_id, file_id, bucket, reasons, checklist,
                  problems, flagged, rechecking, accepted, snoozed, net_cents, corrections, reversed
           from public.current_statuses where grant_id = %s""",
        (grant_id,),
    ).fetchall()
    out: dict[tuple[str, str | None], Status] = {}
    for row in rows:
        status = _status_from_row(row)
        out[status_key(status)] = status
    return out


def insert_status(
    conn: Conn, workspace_id: str, status: Status, changed_at: datetime, trigger: Trigger
) -> None:
    cols = _status_columns(status)
    conn.execute(
        """insert into public.statuses
             (workspace_id, grant_id, charge_id, record_id, file_id, bucket, reasons, checklist,
              problems, flagged, rechecking, accepted, snoozed, changed_at, trigger_kind,
              trigger_id, net_cents, corrections, reversed)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            workspace_id,
            status.grant_id,
            cols["charge_id"],
            cols["record_id"],
            cols["file_id"],
            cols["bucket"],
            Jsonb(cols["reasons"]) if cols["reasons"] is not None else None,
            Jsonb(cols["checklist"]) if cols["checklist"] is not None else None,
            Jsonb(cols["problems"]) if cols["problems"] is not None else None,
            cols["flagged"],
            cols["rechecking"],
            cols["accepted"],
            cols["snoozed"],
            changed_at,
            trigger.kind.value,
            trigger.id,
            cols["net_cents"],
            Jsonb(cols["corrections"]),
            cols["reversed"],
        ),
    )


def same_status(a: Status, b: Status) -> bool:
    return json.dumps(_status_columns(a), sort_keys=True) == json.dumps(
        _status_columns(b), sort_keys=True
    )


def statuses_as_of(conn: Conn, grant_id: str, at: datetime) -> dict[tuple[str, str | None], Status]:
    """The latest status of everything on the grant as it stood at a clock time."""
    rows = conn.execute(
        """select distinct on (charge_id, record_id, file_id)
                  grant_id, charge_id, record_id, file_id, bucket, reasons, checklist, problems,
                  flagged, rechecking, accepted, snoozed, net_cents, corrections, reversed
           from public.statuses where grant_id = %s and changed_at <= %s
           order by charge_id, record_id, file_id, changed_at desc, id desc""",
        (grant_id, at),
    ).fetchall()
    out: dict[tuple[str, str | None], Status] = {}
    for row in rows:
        status = _status_from_row(row)
        out[status_key(status)] = status
    return out


@dataclass(frozen=True)
class StatusRow:
    changed_at: datetime
    trigger: Trigger
    status: Status


def status_history(
    conn: Conn,
    *,
    charge_id: str | None = None,
    record_ids: Sequence[str] = (),
    file_id: str | None = None,
) -> list[StatusRow]:
    """A charge's, some records' or a file's status rows, oldest first."""
    rows = conn.execute(
        """select grant_id, charge_id, record_id, file_id, bucket, reasons, checklist, problems,
                  flagged, rechecking, accepted, snoozed, net_cents, corrections, reversed,
                  changed_at, trigger_kind, trigger_id
           from public.statuses
           where charge_id = %s or record_id = any(%s) or file_id = %s
           order by changed_at, id""",
        (charge_id, list(record_ids), file_id),
    ).fetchall()
    return [
        StatusRow(
            changed_at=r["changed_at"],
            trigger=Trigger(kind=TriggerKind(r["trigger_kind"]), id=r["trigger_id"]),
            status=_status_from_row(r),
        )
        for r in rows
    ]


def get_charge(conn: Conn, charge_id: str, user_id: str) -> Charge | None:
    """The charge, only if this user may reach its grant."""
    row = conn.execute(
        """select c.id, c.workspace_id, c.grant_id, c.ledger_line_id, c.transaction_date,
                  c.posting_date, c.arrived_at, c.amount_cents, c.description, c.account,
                  c.vendor, c.reference, c.original_line_id
           from public.charges c
           where c.id = %s and """
        + reaches("grant", "c.grant_id"),
        (charge_id, user_id),
    ).fetchone()
    return Charge.model_validate(row) if row else None


def get_record(conn: Conn, record_id: str, user_id: str) -> Record | None:
    """The record, only if this user may reach its grant."""
    row = conn.execute(
        """select r.id, r.workspace_id, r.grant_id, r.author, r.author_user_id, r.written_at,
                  r.replaces_id, r.thread_message_id, r.stored_seq,
                  r.read_through_seq, r.data
           from public.records r
           where r.id = %s and """
        + reaches("grant", "r.grant_id"),
        (record_id, user_id),
    ).fetchone()
    return _record(row) if row else None


def grant_messages(conn: Conn, grant_id: str, now: datetime) -> list[ThreadMessage]:
    """Every thread message on the grant written by now, oldest first."""
    rows = conn.execute(
        f"""select {_MESSAGE_COLUMNS} from public.thread_messages
            where grant_id = %s and written_at <= %s order by written_at, created_at, id""",
        (grant_id, now),
    ).fetchall()
    return [_message(r) for r in rows]


def pending_runs(conn: Conn, grant_id: str) -> list[AgentRun]:
    """Queued and running runs, oldest first."""
    rows = conn.execute(
        f"""select {_RUN_COLUMNS} from public.agent_runs
            where grant_id = %s and status in ('queued', 'running') order by queued_at, id""",
        (grant_id,),
    ).fetchall()
    return [_run(r) for r in rows]


def set_grant_clock(conn: Conn, grant_id: str, now: datetime) -> None:
    """Set a grant's stored clock. Only the clock module calls this."""
    conn.execute("update public.grants set clock_now = %s where id = %s", (now, grant_id))


def all_grants(conn: Conn) -> list[Grant]:
    rows = conn.execute(f"select {_GRANT_COLUMNS} from public.grants order by id").fetchall()
    return [Grant.model_validate(r) for r in rows]


END_OF_TIME = datetime.max.replace(tzinfo=UTC)


def has_review_since(conn: Conn, grant_id: str, at: datetime) -> bool:
    """Whether a closeout review (a run the clock started) works as of `at` or later."""
    row = conn.execute(
        """select 1 from public.agent_runs
           where grant_id = %s and trigger_kind = 'clock' and clock_now >= %s limit 1""",
        (grant_id, at),
    ).fetchone()
    return row is not None


def next_catch_up_time(conn: Conn, grant_id: str, run_id: str) -> datetime | None:
    """The earliest time of another catch-up run still queued or running on the grant."""
    row = conn.execute(
        """select min(r.clock_now) as at from public.agent_runs r
           join procrastinate_jobs j on j.args ->> 'run_id' = r.id
           where r.grant_id = %s and r.id <> %s and r.status in ('queued', 'running')
             and j.status in ('todo', 'doing') and (j.args ->> 'catch_up')::boolean""",
        (grant_id, run_id),
    ).fetchone()
    return row["at"] if row else None


def get_user(conn: Conn, user_id: str) -> User | None:
    row = conn.execute(
        "select id, email, name from public.users where id = %s", (user_id,)
    ).fetchone()
    return User.model_validate(_clean(row)) if row else None


def grant_status_history(conn: Conn, grant_id: str, now: datetime) -> list[StatusRow]:
    """Every status row on the grant up to now, oldest first."""
    rows = conn.execute(
        """select grant_id, charge_id, record_id, file_id, bucket, reasons, checklist, problems,
                  flagged, rechecking, accepted, snoozed, net_cents, corrections, reversed,
                  changed_at, trigger_kind, trigger_id
           from public.statuses where grant_id = %s and changed_at <= %s
           order by changed_at, id""",
        (grant_id, now),
    ).fetchall()
    return [
        StatusRow(
            changed_at=r["changed_at"],
            trigger=Trigger(kind=TriggerKind(r["trigger_kind"]), id=r["trigger_id"]),
            status=_status_from_row(r),
        )
        for r in rows
    ]


def set_read_point(conn: Conn, run_id: str, read_through_seq: int) -> None:
    """The last stored point a run read when it started (call 40)."""
    conn.execute(
        "update public.agent_runs set read_through_seq = %s where id = %s",
        (read_through_seq, run_id),
    )


def set_award_number_and_title(
    conn: Conn, grant_id: str, award_number: str | None, title: str | None
) -> None:
    """The grant's award number and title, as the notices that count print them. A grant row
    is updated only when they change."""
    conn.execute(
        """update public.grants set award_number = %s, title = %s
           where id = %s and (award_number is distinct from %s or title is distinct from %s)""",
        (award_number, title, grant_id, award_number, title),
    )


# Mail held from unknown senders, skipped files and the checker's progress (decision 0025).

_HELD_COLUMNS = (
    "id, workspace_id, grant_id, sender, reason, source_ref, subject, held_at, files, skipped"
)


def insert_held_mail(conn: Conn, held: HeldMail) -> bool:
    """Saves a held message. False when the grant already holds that Gmail message."""
    dumped = held.model_dump(mode="json")
    row = conn.execute(
        f"""insert into public.held_mail ({_HELD_COLUMNS})
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (grant_id, source_ref) do nothing
            returning id""",
        (
            held.id,
            held.workspace_id,
            held.grant_id,
            held.sender,
            held.reason.value,
            held.source_ref,
            held.subject,
            held.held_at,
            Jsonb(dumped["files"]),
            Jsonb(dumped["skipped"]),
        ),
    ).fetchone()
    return row is not None


def has_message(conn: Conn, grant_id: str, message_id: str) -> bool:
    """Whether the grant already has a Gmail message, as an evidence file or as held mail:
    the one check for both storing and holding it."""
    row = conn.execute(
        """select 1 from public.held_mail where grant_id = %s and source_ref = %s
           union all
           select 1 from public.evidence_files
           where grant_id = %s and source = 'gmail' and source_ref = %s and parent_id is null
           limit 1""",
        (grant_id, message_id, grant_id, message_id),
    ).fetchone()
    return row is not None


def list_held_mail(conn: Conn, workspace_id: str, now: datetime) -> list[HeldMail]:
    """Every message held on the workspace's grants by `now`, whether or not it's still held."""
    rows = conn.execute(
        f"""select {_HELD_COLUMNS} from public.held_mail
            where workspace_id = %s and held_at <= %s order by held_at, id""",
        (workspace_id, now),
    ).fetchall()
    return [HeldMail.model_validate(r) for r in rows]


def has_gmail_message(conn: Conn, grant_id: str, message_id: str) -> bool:
    """Whether a Gmail message has arrived on the grant as an evidence file."""
    row = conn.execute(
        """select 1 from public.evidence_files
           where grant_id = %s and source = 'gmail' and source_ref = %s and parent_id is null""",
        (grant_id, message_id),
    ).fetchone()
    return row is not None


def insert_skipped(conn: Conn, skipped: Sequence[SkippedFile]) -> None:
    """Saves skipped files. One the grant already has (same source, place, name and reason)
    isn't saved again: the problem names the set of files, so a repeat adds nothing."""
    for s in skipped:
        conn.execute(
            """insert into public.skipped_files
                 (workspace_id, grant_id, name, source, source_ref, reason, skipped_at)
               select %s, %s, %s, %s, %s, %s, %s
               where not exists (
                 select 1 from public.skipped_files
                 where grant_id = %s and source = %s and source_ref = %s and name = %s
                   and reason = %s)""",
            (
                s.workspace_id,
                s.grant_id,
                s.name,
                s.source,
                s.source_ref,
                s.reason.value,
                s.skipped_at,
                s.grant_id,
                s.source,
                s.source_ref,
                s.name,
                s.reason.value,
            ),
        )


def list_skipped(conn: Conn, grant_id: str, now: datetime) -> list[SkippedFile]:
    rows = conn.execute(
        """select workspace_id, grant_id, name, source, source_ref, reason, skipped_at
           from public.skipped_files where grant_id = %s and skipped_at <= %s
           order by skipped_at, id""",
        (grant_id, now),
    ).fetchall()
    return [SkippedFile.model_validate(r) for r in rows]


def lock_progress(conn: Conn) -> CheckerProgress:
    """The checker's saved progress, locked until the transaction ends. Every write the
    checker makes takes this lock, so checking what's already taken in and saving it
    can't interleave."""
    conn.execute("insert into public.checker_progress (id) values (true) on conflict do nothing")
    row = conn.execute(
        """select mail_cursor, seen_message_ids, drive_versions, first_search_done
           from public.checker_progress for update"""
    ).fetchone()
    assert row is not None
    return CheckerProgress.model_validate(row)


def save_progress(conn: Conn, progress: CheckerProgress) -> None:
    dumped = progress.model_dump(mode="json")
    conn.execute(
        """update public.checker_progress
           set mail_cursor = %s, seen_message_ids = %s, drive_versions = %s,
               first_search_done = %s""",
        (
            progress.mail_cursor,
            Jsonb(dumped["seen_message_ids"]),
            Jsonb(dumped["drive_versions"]),
            Jsonb(dumped["first_search_done"]),
        ),
    )


def acting_member_emails(conn: Conn, workspace_id: str) -> list[str]:
    """The sign-in addresses of the workspace's members who can act, lower case: decision
    0025's "the accountant's own address" among a grant's known senders."""
    rows = conn.execute(
        """select lower(u.email) as email from public.workspace_members m
           join public.users u on u.id = m.user_id
           where m.workspace_id = %s and private.can_act(m.role)
           order by 1""",
        (workspace_id,),
    ).fetchall()
    return [r["email"] for r in rows]


def sample_accountant_id(conn: Conn, workspace_id: str) -> str:
    """The workspace's Sample accountant (issue 165): a member that can't act and that
    nobody signs in as. A sample grant's past decisions are written as it."""
    row = conn.execute(
        """select user_id::text as id from public.workspace_members
           where workspace_id = %s and role = 'sample'""",
        (workspace_id,),
    ).fetchone()
    assert row is not None, "every workspace has its Sample accountant"
    return row["id"]
