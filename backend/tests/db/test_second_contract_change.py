"""The columns and checks the second contract change (#39) adds to the first migration's tables."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.db.test_first_migration import (
    NOW,
    OVER_LIMIT,
    insert,
    make_bill,
    make_charge,
    make_file,
    make_grant,
    make_record,
    message_values,
    record_values,
    rejects,
    status_values,
)

if TYPE_CHECKING:
    import psycopg
    from psycopg import errors
    from psycopg.types.json import Jsonb
else:
    psycopg = pytest.importorskip("psycopg")
    errors = pytest.importorskip("psycopg.errors")
    Jsonb = pytest.importorskip("psycopg.types.json").Jsonb


@pytest.fixture
def g(db: psycopg.Connection) -> dict[str, Any]:
    return make_grant(db)


def run_values(g: dict[str, Any], **values: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "workspace_id": g["workspace_id"],
        "grant_id": g["grant_id"],
        "trigger_kind": "clock",
        "clock_now": NOW,
    }
    row.update(values)
    return row


def make_message(db: psycopg.Connection, g: dict[str, Any], charge_id: str) -> str:
    return insert(db, "thread_messages", **message_values(g, charge_id=charge_id))


# Grants and evidence files: decision 0025.


def test_a_grant_has_an_address_code_and_a_drive_folder(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    db.execute(
        "insert into public.grants (workspace_id, address_code, drive_folder_id) "
        "values (%s, 'k7q2x', 'folder-1')",
        [g["workspace_id"]],
    )
    row = db.execute(
        "select address_code, drive_folder_id from public.grants where address_code = 'k7q2x'"
    ).fetchone()
    assert row == ("k7q2x", "folder-1")


def test_two_grants_cannot_share_an_address_code(db: psycopg.Connection, g: dict[str, Any]) -> None:
    insert(db, "grants", workspace_id=g["workspace_id"], address_code="k7q2x")
    rejects(
        db, errors.UniqueViolation, "grants", workspace_id=g["workspace_id"], address_code="k7q2x"
    )
    other = make_grant(db)
    rejects(
        db,
        errors.UniqueViolation,
        "grants",
        workspace_id=other["workspace_id"],
        address_code="k7q2x",
    )


def test_grants_without_an_address_code_are_allowed(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    insert(db, "grants", workspace_id=g["workspace_id"])
    insert(db, "grants", workspace_id=g["workspace_id"])


def test_an_evidence_file_says_what_it_was_exported_from(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    file_id = make_file(db, g)
    row = db.execute(
        "select exported_from from public.evidence_files where id = %s", [file_id]
    ).fetchone()
    assert row == (None,)
    exported = insert(
        db,
        "evidence_files",
        workspace_id=g["workspace_id"],
        grant_id=g["grant_id"],
        source="drive",
        name="budget.pdf",
        media_type="application/pdf",
        storage_path=f"{g['workspace_id']}/{g['grant_id']}/f-2/budget.pdf",
        sha256="2" * 64,
        arrived_at=NOW,
        exported_from="application/vnd.google-apps.spreadsheet",
    )
    row = db.execute(
        "select exported_from from public.evidence_files where id = %s", [exported]
    ).fetchone()
    assert row == ("application/vnd.google-apps.spreadsheet",)


# Records: the thread message of the run that wrote it, and mail_action.


def test_an_agent_record_names_the_thread_message_of_its_run(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    message_id = make_message(db, g, make_charge(db, g))
    record_id = make_record(db, g, {"kind": "note"}, thread_message_id=message_id)
    row = db.execute(
        "select thread_message_id from public.records where id = %s", [record_id]
    ).fetchone()
    assert row == (message_id,)


def test_only_the_agent_records_name_a_thread_message(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    message_id = make_message(db, g, make_charge(db, g))
    rejects(
        db,
        errors.CheckViolation,
        "records",
        **record_values(
            g,
            {"kind": "note"},
            author="user",
            author_user_id=g["user_id"],
            thread_message_id=message_id,
        ),
    )


def test_a_record_names_a_thread_message_that_exists(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    rejects(
        db,
        errors.ForeignKeyViolation,
        "records",
        **record_values(g, {"kind": "note"}, thread_message_id="nope"),
    )


def test_mail_action_is_the_accountants_only(db: psycopg.Connection, g: dict[str, Any]) -> None:
    # The held message it names has to exist (issue 43's migration).
    db.execute(
        "insert into public.held_mail "
        "(id, workspace_id, grant_id, reason, source_ref, held_at, files) "
        "values ('held-1', %s, %s, 'unknown_sender', 'msg-1', %s, '[]')",
        [g["workspace_id"], g["grant_id"], NOW],
    )
    data = {"kind": "mail_action", "held_mail_id": "held-1", "action": "let_in"}
    make_record(db, g, data, author="user", author_user_id=g["user_id"])
    rejects(db, errors.CheckViolation, "records", **record_values(g, data, author="agent"))


# Agent runs: the open_question trigger and a thread run's subject.


def test_open_question_is_a_trigger_kind(db: psycopg.Connection, g: dict[str, Any]) -> None:
    charge_id = make_charge(db, g)
    insert(db, "agent_runs", **run_values(g, trigger_kind="open_question", trigger_id=charge_id))
    insert(
        db,
        "statuses",
        **status_values(
            g,
            charge_id=charge_id,
            bucket="needs_human",
            trigger_kind="open_question",
            trigger_id=charge_id,
        ),
    )
    rejects(db, errors.CheckViolation, "agent_runs", **run_values(g, trigger_kind="open_question"))
    rejects(
        db,
        errors.CheckViolation,
        "statuses",
        **status_values(g, trigger_kind="open_question"),
    )


def test_a_thread_run_names_its_charge_or_record(db: psycopg.Connection, g: dict[str, Any]) -> None:
    charge_id = make_charge(db, g)
    record_id = make_bill(db, g)
    message_id = make_message(db, g, charge_id)
    thread = {"trigger_kind": "thread_message", "trigger_id": message_id}
    insert(db, "agent_runs", **run_values(g, **thread, thread_charge_id=charge_id))
    insert(db, "agent_runs", **run_values(g, **thread, thread_record_id=record_id))
    rejects(db, errors.CheckViolation, "agent_runs", **run_values(g, **thread))
    rejects(
        db,
        errors.CheckViolation,
        "agent_runs",
        **run_values(g, **thread, thread_charge_id=charge_id, thread_record_id=record_id),
    )


@pytest.mark.parametrize("trigger_kind", ["record", "charge", "file", "open_question", "clock"])
def test_only_a_thread_run_names_a_thread_subject(
    db: psycopg.Connection, g: dict[str, Any], trigger_kind: str
) -> None:
    charge_id = make_charge(db, g)
    trigger_id = None if trigger_kind == "clock" else charge_id
    trigger = {"trigger_kind": trigger_kind, "trigger_id": trigger_id}
    insert(db, "agent_runs", **run_values(g, **trigger))
    rejects(
        db,
        errors.CheckViolation,
        "agent_runs",
        **run_values(g, **trigger, thread_charge_id=charge_id),
    )


def test_a_thread_subject_exists(db: psycopg.Connection, g: dict[str, Any]) -> None:
    message_id = make_message(db, g, make_charge(db, g))
    thread = {"trigger_kind": "thread_message", "trigger_id": message_id}
    rejects(
        db,
        errors.ForeignKeyViolation,
        "agent_runs",
        **run_values(g, **thread, thread_charge_id="no"),
    )
    rejects(
        db,
        errors.ForeignKeyViolation,
        "agent_runs",
        **run_values(g, **thread, thread_record_id="no"),
    )


# Statuses: decision 0020, on a charge's row.


def test_a_charge_status_carries_its_net_corrections_and_reversed(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    charge_id = make_charge(db, g)
    reversal_id = make_charge(db, g, "L-1003")
    charge = {"charge_id": charge_id, "bucket": "evidence_complete"}
    insert(db, "statuses", **status_values(g, **charge))
    insert(
        db,
        "statuses",
        **status_values(g, **charge, net_cents=0, corrections=[reversal_id], reversed=True),
    )
    row = db.execute(
        "select net_cents, corrections, reversed from public.current_statuses where charge_id = %s",
        [charge_id],
    ).fetchone()
    assert row == (0, [reversal_id], True)


def test_a_new_status_row_nets_nothing_by_default(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    status_id = insert(
        db, "statuses", **status_values(g, charge_id=make_charge(db, g), bucket="needs_human")
    )
    row = db.execute(
        "select net_cents, corrections, reversed from public.statuses where id = %s",
        [int(status_id)],
    ).fetchone()
    assert row == (None, [], False)


def test_a_reversed_charge_nets_to_zero(db: psycopg.Connection, g: dict[str, Any]) -> None:
    charge = {"charge_id": make_charge(db, g), "bucket": "evidence_complete", "reversed": True}
    for net in [None, 124000, -1]:
        rejects(db, errors.CheckViolation, "statuses", **status_values(g, **charge, net_cents=net))


def test_corrections_is_a_json_array(db: psycopg.Connection, g: dict[str, Any]) -> None:
    charge = {"charge_id": make_charge(db, g), "bucket": "needs_human"}
    for value in [None, "L-1003", {"id": "L-1003"}]:
        rejects(
            db,
            errors.CheckViolation,
            "statuses",
            **status_values(g, **charge, corrections=Jsonb(value)),
        )


def test_only_a_charge_status_nets(db: psycopg.Connection, g: dict[str, Any]) -> None:
    for about in [{"record_id": make_bill(db, g)}, {"file_id": make_file(db, g)}, {}]:
        insert(db, "statuses", **status_values(g, **about, problems=OVER_LIMIT))
        for wrong in [{"net_cents": 0}, {"corrections": ["c-1"]}, {"reversed": True}]:
            rejects(db, errors.CheckViolation, "statuses", **status_values(g, **about, **wrong))
