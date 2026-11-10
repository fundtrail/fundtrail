"""Issue 160: access goes through workspace membership, never `owner_id`.

Fails on a new direct `owner_id` comparison in the backend's app code or the
migrations. `workspaces.owner_id` stays as who created a workspace; writing it when a
workspace is created and the membership backfill read it, and neither compares it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

# A comparison with owner_id on either side, in Python or SQL. A Python keyword argument
# (`owner_id=x`, no spaces, as the formatter writes it) isn't one.
COMPARED = re.compile(
    r"\bowner_id\b\s*(?:==|!=|<>|\bin\b|\bis\b|\bnot\b)|\bowner_id\b\s+=(?!=)"
    r"|(?:==|!=|<>|\s=)\s*[\w.]*\bowner_id\b",
    re.IGNORECASE,
)
# Replaced by private.can_hear_topic in 20261111000000_workspace_members.sql.
REPLACED = {"supabase/migrations/20261110220000_held_mail_and_progress.sql": 2}


def _sources() -> list[Path]:
    return sorted((REPO / "backend" / "app").rglob("*.py")) + sorted(
        (REPO / "supabase" / "migrations").glob("*.sql")
    )


def test_nothing_decides_access_by_owner_id() -> None:
    found: dict[str, int] = {}
    for path in _sources():
        rel = path.relative_to(REPO).as_posix()
        for line in path.read_text(encoding="utf-8").splitlines():
            code = line.split("--", 1)[0] if path.suffix == ".sql" else line.split("#", 1)[0]
            if COMPARED.search(code):
                found[rel] = found.get(rel, 0) + 1
    assert found == REPLACED, (
        "decide access with store.reaches or private.can_reach_workspace / can_reach_grant, "
        f"not owner_id: {found}"
    )


def test_the_guard_catches_a_comparison() -> None:
    for sample in (
        "where w.owner_id = %s",
        "where %s = w.owner_id",
        "if workspace.owner_id == user.id:",
        "and owner_id in (select 1)",
        "w.owner_id is not distinct from auth.uid()",
    ):
        assert COMPARED.search(sample), sample
    for fine in (
        "owner_id: Id",
        "def create_workspace(conn: Conn, owner_id: str, name: str)",
        "insert into public.workspaces (owner_id, name) values (%s, %s)",
        "values (new.id, new.owner_id, 'owner')",
        "store.create_workspace(conn, owner_id=user_id)",
    ):
        assert not COMPARED.search(fine), fine
