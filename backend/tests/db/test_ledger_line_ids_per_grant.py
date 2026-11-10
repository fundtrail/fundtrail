"""Ledger line IDs are unique per grant, not per workspace (issue 165)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.db.test_first_migration import insert, make_charge, make_grant

if TYPE_CHECKING:
    import psycopg
    from psycopg import errors
else:
    errors = pytest.importorskip("psycopg.errors")


def test_two_grants_in_one_workspace_may_hold_the_same_line(db: psycopg.Connection) -> None:
    g = make_grant(db)
    copy = insert(db, "grants", workspace_id=g["workspace_id"], award_number="SYN-2300117")
    make_charge(db, g, "L-1001")
    make_charge(db, {**g, "grant_id": copy}, "L-1001")


def test_one_grant_still_holds_a_line_once(db: psycopg.Connection) -> None:
    g: dict[str, Any] = make_grant(db)
    make_charge(db, g, "L-1001")
    with pytest.raises(errors.UniqueViolation), db.transaction():
        make_charge(db, g, "L-1001")
