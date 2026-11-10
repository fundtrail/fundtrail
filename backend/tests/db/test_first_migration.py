"""The constraints in docs/contracts.md section 11, each against a real Postgres."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import psycopg
    from psycopg import errors
    from psycopg.types.json import Jsonb
else:
    psycopg = pytest.importorskip("psycopg")
    errors = pytest.importorskip("psycopg.errors")
    Jsonb = pytest.importorskip("psycopg.types.json").Jsonb

TABLES = [
    "users",
    "workspaces",
    "grants",
    "charges",
    "evidence_files",
    "records",
    "statuses",
    "agent_runs",
    "thread_messages",
]
NOW = "2025-11-14T12:00:00Z"


# Helpers that build a small workspace, one row at a time.


def insert(conn: psycopg.Connection, table: str, **values: Any) -> str:
    columns = ", ".join(values)
    placeholders = ", ".join(["%s"] * len(values))
    params = [Jsonb(v) if isinstance(v, (dict, list)) else v for v in values.values()]
    row = conn.execute(
        f"insert into public.{table} ({columns}) values ({placeholders}) returning id",
        params,
    ).fetchone()
    assert row is not None
    return str(row[0])


def rejects(
    conn: psycopg.Connection, error: type[Exception], table: str, **values: Any
) -> None:
    with pytest.raises(error), conn.transaction():
        insert(conn, table, **values)


def make_user(conn: psycopg.Connection) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute("insert into auth.users (id) values (%s)", [user_id])
    insert(conn, "users", id=user_id, email=f"{user_id.hex[:8]}@university.example")
    return user_id


def make_grant(conn: psycopg.Connection) -> dict[str, Any]:
    user_id = make_user(conn)
    workspace_id = insert(conn, "workspaces", owner_id=user_id, name="Demo")
    grant_id = insert(
        conn, "grants", workspace_id=workspace_id, award_number="SYN-2300117"
    )
    return {"user_id": user_id, "workspace_id": workspace_id, "grant_id": grant_id}


def make_charge(
    conn: psycopg.Connection, g: dict[str, Any], line_id: str = "L-1001"
) -> str:
    return insert(
        conn,
        "charges",
        workspace_id=g["workspace_id"],
        grant_id=g["grant_id"],
        ledger_line_id=line_id,
        transaction_date="2025-11-12",
        posting_date="2025-11-14",
        arrived_at="2025-11-14T00:00:00Z",
        amount_cents=124000,
        description="Sediment core liners",
        account="55016 Lab Instruments and Supplies",
        vendor="Example Lab Supply Co.",
        reference="INV-1001",
    )


def make_file(
    conn: psycopg.Connection, g: dict[str, Any], name: str = "invoice_1001.txt"
) -> str:
    file_id = str(uuid.uuid4())
    return insert(
        conn,
        "evidence_files",
        id=file_id,
        workspace_id=g["workspace_id"],
        grant_id=g["grant_id"],
        source="upload",
        name=name,
        media_type="text/plain",
        storage_path=f"{g['workspace_id']}/{g['grant_id']}/{file_id}/{name}",
        sha256="0" * 64,
        arrived_at="2025-11-12T00:00:00Z",
    )


def record_values(g: dict[str, Any], data: Any, **envelope: Any) -> dict[str, Any]:
    values = {
        "workspace_id": g["workspace_id"],
        "grant_id": g["grant_id"],
        "author": "agent",
        "written_at": NOW,
        "data": data,
    }
    values.update(envelope)
    return values


def make_record(
    conn: psycopg.Connection, g: dict[str, Any], data: dict[str, Any], **envelope: Any
) -> str:
    return insert(conn, "records", **record_values(g, data, **envelope))


def make_bill(conn: psycopg.Connection, g: dict[str, Any]) -> str:
    return make_record(conn, g, {"kind": "bill", "total": {"value": 124000}})


def make_run(
    conn: psycopg.Connection, g: dict[str, Any], status: str = "queued"
) -> str:
    return insert(
        conn,
        "agent_runs",
        workspace_id=g["workspace_id"],
        grant_id=g["grant_id"],
        trigger_kind="clock",
        status=status,
        clock_now=NOW,
    )


def status_values(g: dict[str, Any], **values: Any) -> dict[str, Any]:
    row = {
        "workspace_id": g["workspace_id"],
        "grant_id": g["grant_id"],
        "reasons": [],
        "flagged": False,
        "changed_at": NOW,
        "trigger_kind": "clock",
    }
    row.update(values)
    return row


def message_values(g: dict[str, Any], **values: Any) -> dict[str, Any]:
    row = {
        "workspace_id": g["workspace_id"],
        "grant_id": g["grant_id"],
        "author": "user",
        "author_user_id": g["user_id"],
        "text": "Is this the right invoice?",
        "written_at": NOW,
    }
    row.update(values)
    return row


@pytest.fixture
def g(db: psycopg.Connection) -> dict[str, Any]:
    return make_grant(db)


# The migration applies.


def test_creates_every_table_with_row_level_security_and_no_policies(
    db: psycopg.Connection,
) -> None:
    rows = db.execute(
        "select relname, relrowsecurity from pg_class "
        "where relnamespace = 'public'::regnamespace and relkind = 'r'"
    ).fetchall()
    assert dict(rows) == {table: True for table in TABLES}
    policies = db.execute(
        "select count(*) from pg_policies where schemaname = 'public'"
    ).fetchone()
    assert policies == (0,)


def test_creates_the_current_statuses_view(db: psycopg.Connection) -> None:
    row = db.execute("select to_regclass('public.current_statuses')").fetchone()
    assert row == ("current_statuses",)


def test_creates_the_private_evidence_bucket(db: psycopg.Connection) -> None:
    row = db.execute(
        "select public from storage.buckets where id = 'evidence'"
    ).fetchone()
    assert row == (False,)


def test_has_no_procrastinate_tables(db: psycopg.Connection) -> None:
    row = db.execute(
        "select count(*) from pg_class where relname like 'procrastinate%'"
    ).fetchone()
    assert row == (0,)


# Updates are rejected on records, charges, statuses and thread messages.


@pytest.mark.parametrize("table", ["records", "charges", "statuses", "thread_messages"])
def test_rejects_updates(db: psycopg.Connection, g: dict[str, Any], table: str) -> None:
    charge_id = make_charge(db, g)
    ids = {
        "records": lambda: make_bill(db, g),
        "charges": lambda: charge_id,
        "statuses": lambda: insert(
            db,
            "statuses",
            **status_values(g, charge_id=charge_id, bucket="needs_human"),
        ),
        "thread_messages": lambda: insert(
            db, "thread_messages", **message_values(g, charge_id=charge_id)
        ),
    }
    row_id = ids[table]()
    with pytest.raises(errors.RestrictViolation), db.transaction():
        db.execute(
            f"update public.{table} set workspace_id = workspace_id where id = %s",
            [row_id],
        )


@pytest.mark.parametrize("table", ["records", "charges", "statuses", "thread_messages"])
def test_allows_deletes_so_a_reset_can_clear_the_workspace(
    db: psycopg.Connection, g: dict[str, Any], table: str
) -> None:
    charge_id = make_charge(db, g)
    bill_id = make_bill(db, g)
    make_record(
        db,
        g,
        {
            "kind": "link",
            "record_id": bill_id,
            "charge_id": charge_id,
            "amount_cents": 124000,
        },
    )
    insert(
        db,
        "statuses",
        **status_values(g, charge_id=charge_id, bucket="evidence_complete"),
    )
    insert(db, "thread_messages", **message_values(g, charge_id=charge_id))
    db.execute(
        f"delete from public.{table} where workspace_id = %s", [g["workspace_id"]]
    )
    row = db.execute(
        f"select count(*) from public.{table} where workspace_id = %s",
        [g["workspace_id"]],
    )
    assert row.fetchone() == (0,)


def test_agent_runs_are_updated_in_place(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    run_id = make_run(db, g)
    db.execute(
        "update public.agent_runs set status = 'running', started_at = now() where id = %s",
        [run_id],
    )
    db.execute(
        "update public.agent_runs set status = 'done', finished_at = now() where id = %s",
        [run_id],
    )


def test_deleting_a_workspace_clears_everything_in_it(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    charge_id = make_charge(db, g)
    file_id = make_file(db, g)
    bill_id = make_bill(db, g)
    make_record(db, g, {"kind": "link", "record_id": bill_id, "charge_id": charge_id})
    insert(db, "statuses", **status_values(g, file_id=file_id))
    run_id = make_run(db, g)
    insert(
        db,
        "thread_messages",
        **message_values(
            g, record_id=bill_id, author="agent", author_user_id=None, run_id=run_id
        ),
    )
    db.execute("delete from public.workspaces where id = %s", [g["workspace_id"]])
    for table in TABLES[2:]:
        row = db.execute(f"select count(*) from public.{table}").fetchone()
        assert row == (0,), table


# One charge per ledger line ID in a workspace, and one file per storage path.


def test_one_charge_per_ledger_line_in_a_workspace(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    make_charge(db, g, "L-1001")
    with pytest.raises(errors.UniqueViolation), db.transaction():
        make_charge(db, g, "L-1001")


def test_the_same_ledger_line_may_be_in_two_workspaces(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    make_charge(db, g, "L-1001")
    make_charge(db, make_grant(db), "L-1001")


def test_one_file_per_storage_path(db: psycopg.Connection, g: dict[str, Any]) -> None:
    file_id = make_file(db, g)
    path = db.execute(
        "select storage_path from public.evidence_files where id = %s", [file_id]
    ).fetchone()
    assert path is not None
    rejects(
        db,
        errors.UniqueViolation,
        "evidence_files",
        workspace_id=g["workspace_id"],
        grant_id=g["grant_id"],
        source="gmail",
        name="copy.txt",
        media_type="text/plain",
        storage_path=path[0],
        sha256="1" * 64,
        arrived_at=NOW,
    )


def test_the_same_fingerprint_may_arrive_twice(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    make_file(db, g, "invoice_1001.txt")
    make_file(db, g, "invoice_1001_again.txt")


# Records.


def test_record_kind_charge_and_record_are_generated_from_data(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    charge_id = make_charge(db, g)
    bill_id = make_bill(db, g)
    link_id = make_record(
        db, g, {"kind": "link", "record_id": bill_id, "charge_id": charge_id}
    )
    row = db.execute(
        "select kind, charge_id, record_id from public.records where id = %s", [link_id]
    )
    assert row.fetchone() == ("link", charge_id, bill_id)


def test_record_needs_a_kind(db: psycopg.Connection, g: dict[str, Any]) -> None:
    rejects(db, errors.NotNullViolation, "records", **record_values(g, {"total": 1}))


def test_author_user_id_is_set_for_user(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    make_record(db, g, {"kind": "note"}, author="user", author_user_id=g["user_id"])
    rejects(
        db,
        errors.CheckViolation,
        "records",
        **record_values(g, {"kind": "note"}, author="user"),
    )


def test_author_user_id_is_empty_for_agent(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    rejects(
        db,
        errors.CheckViolation,
        "records",
        **record_values(
            g, {"kind": "note"}, author="agent", author_user_id=g["user_id"]
        ),
    )


def test_author_is_agent_or_user(db: psycopg.Connection, g: dict[str, Any]) -> None:
    rejects(
        db,
        errors.CheckViolation,
        "records",
        **record_values(g, {"kind": "note"}, author="code"),
    )


def test_a_record_can_replace_another(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    bill_id = make_bill(db, g)
    make_record(
        db, g, {"kind": "bill", "total": {"value": 124100}}, replaces_id=bill_id
    )


def test_a_record_cannot_replace_itself(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    rejects(
        db,
        errors.CheckViolation,
        "records",
        **record_values(g, {"kind": "note"}, id="rec-self", replaces_id="rec-self"),
    )


def test_a_record_cannot_replace_a_missing_record(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    rejects(
        db,
        errors.ForeignKeyViolation,
        "records",
        **record_values(g, {"kind": "note"}, replaces_id="nope"),
    )


def test_a_retraction_replaces_something(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    bill_id = make_bill(db, g)
    make_record(db, g, {"kind": "retraction"}, replaces_id=bill_id)
    rejects(
        db, errors.CheckViolation, "records", **record_values(g, {"kind": "retraction"})
    )


@pytest.mark.parametrize("kind", ["link", "budget_assignment"])
def test_link_and_budget_assignment_name_record_and_charge(
    db: psycopg.Connection, g: dict[str, Any], kind: str
) -> None:
    charge_id = make_charge(db, g)
    target_id = make_bill(db, g)
    make_record(db, g, {"kind": kind, "record_id": target_id, "charge_id": charge_id})
    rejects(
        db,
        errors.CheckViolation,
        "records",
        **record_values(g, {"kind": kind, "charge_id": charge_id}),
    )
    rejects(
        db,
        errors.CheckViolation,
        "records",
        **record_values(g, {"kind": kind, "record_id": target_id}),
    )


@pytest.mark.parametrize("missing", ["charge_id", "record_id"])
def test_a_link_points_to_rows_that_exist(
    db: psycopg.Connection, g: dict[str, Any], missing: str
) -> None:
    data = {
        "kind": "link",
        "charge_id": make_charge(db, g),
        "record_id": make_bill(db, g),
    }
    data[missing] = "nope"
    rejects(db, errors.ForeignKeyViolation, "records", **record_values(g, data))


def test_a_judgment_points_to_rows_that_exist(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    charge_id = make_charge(db, g)
    make_record(
        db, g, {"kind": "judgment", "charge_id": charge_id, "question": "allowable"}
    )
    rejects(
        db,
        errors.ForeignKeyViolation,
        "records",
        **record_values(
            g, {"kind": "judgment", "charge_id": "nope", "question": "allowable"}
        ),
    )


@pytest.mark.parametrize(
    "kind", ["confirmation", "accepted_reason", "snooze", "sign_off"]
)
def test_accountant_only_kinds_only_by_user(
    db: psycopg.Connection, g: dict[str, Any], kind: str
) -> None:
    make_record(db, g, {"kind": kind}, author="user", author_user_id=g["user_id"])
    rejects(
        db,
        errors.CheckViolation,
        "records",
        **record_values(g, {"kind": kind}, author="agent"),
    )


def test_data_is_a_json_object(db: psycopg.Connection, g: dict[str, Any]) -> None:
    rejects(db, errors.NotNullViolation, "records", **record_values(g, ["link"]))


# Statuses and the current_statuses view.


def test_current_statuses_gives_the_latest_row_for_each_charge_record_or_file(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    charge_id = make_charge(db, g)
    record_id = make_bill(db, g)
    file_id = make_file(db, g)
    for bucket, changed_at in [
        ("possible_conflict", "2026-02-24T12:00:00Z"),
        ("evidence_complete", "2026-04-10T17:00:00Z"),
        ("needs_human", "2026-03-01T12:00:00Z"),
    ]:
        insert(
            db,
            "statuses",
            **status_values(
                g, charge_id=charge_id, bucket=bucket, changed_at=changed_at
            ),
        )
    insert(db, "statuses", **status_values(g, record_id=record_id, flagged=True))
    insert(db, "statuses", **status_values(g, record_id=record_id, flagged=False))
    insert(db, "statuses", **status_values(g, file_id=file_id, flagged=True))

    rows = db.execute(
        "select charge_id, record_id, file_id, bucket, flagged from public.current_statuses "
        "where workspace_id = %s",
        [g["workspace_id"]],
    ).fetchall()
    assert sorted(rows, key=str) == sorted(
        [
            (charge_id, None, None, "evidence_complete", False),
            (None, record_id, None, None, False),
            (None, None, file_id, None, True),
        ],
        key=str,
    )


def test_a_status_is_about_at_most_one_thing(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    charge_id = make_charge(db, g)
    file_id = make_file(db, g)
    rejects(
        db,
        errors.CheckViolation,
        "statuses",
        **status_values(g, charge_id=charge_id, file_id=file_id, bucket="needs_human"),
    )


def test_a_status_with_no_subject_is_about_the_grant(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    problem = [{"check": "budget", "text": "Spending is over the award's limit."}]
    insert(db, "statuses", **status_values(g, reasons=problem, flagged=True))
    rejects(
        db, errors.CheckViolation, "statuses", **status_values(g, bucket="needs_human")
    )
    rejects(db, errors.NotNullViolation, "statuses", **status_values(g, grant_id=None))


def test_current_statuses_gives_one_row_per_grant_for_its_own_statuses(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    other = make_grant(db)
    charge_id = make_charge(db, g)
    over = [{"check": "budget", "text": "Spending is over the award's limit."}]
    for flagged, changed_at in [
        (True, "2026-02-24T12:00:00Z"),
        (False, "2026-04-10T17:00:00Z"),
        (True, "2026-03-01T12:00:00Z"),
    ]:
        insert(
            db,
            "statuses",
            **status_values(g, reasons=over, flagged=flagged, changed_at=changed_at),
        )
    insert(db, "statuses", **status_values(other, reasons=over, flagged=True))
    insert(
        db,
        "statuses",
        **status_values(g, charge_id=charge_id, bucket="needs_human", flagged=True),
    )

    rows = db.execute(
        "select grant_id, charge_id, flagged, changed_at from public.current_statuses "
        "where charge_id is null and record_id is null and file_id is null "
        "and grant_id in (%s, %s)",
        [g["grant_id"], other["grant_id"]],
    ).fetchall()
    assert sorted(
        (grant_id, charge, flagged) for grant_id, charge, flagged, _ in rows
    ) == sorted([(g["grant_id"], None, False), (other["grant_id"], None, True)])
    latest = {grant_id: changed_at for grant_id, _, _, changed_at in rows}
    assert latest[g["grant_id"]] == datetime(2026, 4, 10, 17, tzinfo=UTC)
    charge_rows = db.execute(
        "select count(*) from public.current_statuses where charge_id = %s", [charge_id]
    ).fetchone()
    assert charge_rows == (1,)


def test_a_charge_status_has_a_bucket_and_others_do_not(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    charge_id = make_charge(db, g)
    file_id = make_file(db, g)
    rejects(
        db, errors.CheckViolation, "statuses", **status_values(g, charge_id=charge_id)
    )
    rejects(
        db,
        errors.CheckViolation,
        "statuses",
        **status_values(g, file_id=file_id, bucket="needs_human"),
    )
    rejects(
        db,
        errors.CheckViolation,
        "statuses",
        **status_values(g, charge_id=charge_id, bucket="done"),
    )


def test_a_status_trigger_has_an_id_unless_it_is_the_clock(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    charge_id = make_charge(db, g)
    about = {"charge_id": charge_id, "bucket": "needs_human"}
    insert(
        db,
        "statuses",
        **status_values(g, **about, trigger_kind="thread_message", trigger_id="m-1"),
    )
    rejects(
        db,
        errors.CheckViolation,
        "statuses",
        **status_values(g, **about, trigger_kind="record"),
    )
    rejects(
        db,
        errors.CheckViolation,
        "statuses",
        **status_values(g, **about, trigger_id="r-1"),
    )
    rejects(
        db,
        errors.CheckViolation,
        "statuses",
        **status_values(g, **about, trigger_kind="run", trigger_id="x"),
    )


# Agent runs.


def test_one_running_agent_run_per_grant(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    make_run(db, g, "running")
    make_run(db, g, "queued")
    make_run(db, g, "done")
    make_run(db, make_grant(db), "running")
    with pytest.raises(errors.UniqueViolation), db.transaction():
        make_run(db, g, "running")


def test_agent_run_status_is_one_of_four(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    with pytest.raises(errors.CheckViolation), db.transaction():
        make_run(db, g, "paused")


# Thread messages.


def test_a_message_is_about_a_charge_or_a_record(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    charge_id = make_charge(db, g)
    record_id = make_bill(db, g)
    insert(db, "thread_messages", **message_values(g, charge_id=charge_id))
    insert(db, "thread_messages", **message_values(g, record_id=record_id))
    rejects(db, errors.CheckViolation, "thread_messages", **message_values(g))
    rejects(
        db,
        errors.CheckViolation,
        "thread_messages",
        **message_values(g, charge_id=charge_id, record_id=record_id),
    )


def test_a_message_author_user_id_is_set_exactly_for_user(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    charge_id = make_charge(db, g)
    rejects(
        db,
        errors.CheckViolation,
        "thread_messages",
        **message_values(g, charge_id=charge_id, author_user_id=None),
    )


def test_an_agent_message_names_its_run(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    charge_id = make_charge(db, g)
    run_id = make_run(db, g)
    agent = {"charge_id": charge_id, "author": "agent", "author_user_id": None}
    insert(db, "thread_messages", **message_values(g, **agent, run_id=run_id))
    rejects(db, errors.CheckViolation, "thread_messages", **message_values(g, **agent))
    rejects(
        db,
        errors.CheckViolation,
        "thread_messages",
        **message_values(g, charge_id=charge_id, run_id=run_id),
    )
