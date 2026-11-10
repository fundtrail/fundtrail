"""The stored-order migration (issue 70): one sequence shared by records, charges and
evidence files, so any two rows can be compared, even rows saved in one transaction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.db.test_first_migration import make_bill, make_charge, make_file, make_grant

if TYPE_CHECKING:
    import psycopg


@pytest.fixture
def g(db: psycopg.Connection) -> dict[str, Any]:
    return make_grant(db)


def stored_seq(conn: psycopg.Connection, table: str, row_id: str) -> int:
    from psycopg import sql

    query = sql.SQL("select stored_seq from {} where id = %s").format(sql.Identifier(table))
    row = conn.execute(query, (row_id,)).fetchone()
    assert row is not None
    return int(row[0])


def test_rows_in_one_transaction_get_increasing_stored_order_across_tables(
    db: psycopg.Connection, g: dict[str, Any]
) -> None:
    with db.transaction():
        file_id = make_file(db, g)
        charge_id = make_charge(db, g)
        record_id = make_bill(db, g)
    order = [
        stored_seq(db, "evidence_files", file_id),
        stored_seq(db, "charges", charge_id),
        stored_seq(db, "records", record_id),
    ]
    assert order == sorted(order) and len(set(order)) == 3
