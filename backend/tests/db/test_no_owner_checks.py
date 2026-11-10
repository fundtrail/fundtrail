"""Issue 160: access goes through workspace membership, never `owner_id`.

Fails on a new `owner_id` comparison in the backend's app code or the migrations.
`workspaces.owner_id` stays as who created a workspace: writing it when a workspace is
created, and the membership backfill reading it, aren't comparisons.

- SQL (each `.sql` file, and every string constant in Python) is read whole, comments
  dropped and whitespace collapsed, so a comparison split across lines or written
  without spaces (`owner_id=%s`) is caught, and so is `using (owner_id)`.
- Python is read as a syntax tree: any comparison that mentions owner_id, a
  `getattr(..., "owner_id")`, and `operator.eq` / `ne` over it. A keyword argument
  (`owner_id=...`) is never a comparison.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

SQL_COMPARED = [
    re.compile(
        r"\bowner_id\b(?:\s*\)|\s*::\s*\w+)*\s*(?:=|<>|!=|\bin\b|\bis\b|\blike\b)", re.IGNORECASE
    ),
    re.compile(r"(?:=|<>|!=)\s*\(?\s*[\w.\"]*\bowner_id\b", re.IGNORECASE),
    re.compile(r"\busing\s*\([^)]*\bowner_id\b", re.IGNORECASE),
]
# Replaced by private.can_hear_topic in 20261111000000_workspace_members.sql.
REPLACED = {"supabase/migrations/20261110220000_held_mail_and_progress.sql": 2}


def sql_hits(sql: str) -> int:
    text = " ".join(re.sub(r"--[^\n]*", "", sql).split())
    return sum(len(p.findall(text)) for p in SQL_COMPARED)


def _mentions(node: ast.AST) -> bool:
    return any(
        (isinstance(n, ast.Attribute) and n.attr == "owner_id")
        or (isinstance(n, ast.Name) and n.id == "owner_id")
        or (isinstance(n, ast.Constant) and n.value == "owner_id")
        for n in ast.walk(node)
    )


def python_hits(source: str) -> int:
    tree = ast.parse(source)
    found = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and _mentions(node):
            found += 1
        elif isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ""
            )
            if name == "getattr" and any(
                isinstance(a, ast.Constant) and a.value == "owner_id" for a in node.args
            ):
                found += 1
            elif name in ("eq", "ne", "__eq__", "__ne__") and any(_mentions(a) for a in node.args):
                found += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found += sql_hits(node.value)
    return found


def test_nothing_decides_access_by_owner_id() -> None:
    found: dict[str, int] = {}
    for path in sorted((REPO / "backend" / "app").rglob("*.py")):
        if n := python_hits(path.read_text(encoding="utf-8")):
            found[path.relative_to(REPO).as_posix()] = n
    for path in sorted((REPO / "supabase" / "migrations").glob("*.sql")):
        if n := sql_hits(path.read_text(encoding="utf-8")):
            found[path.relative_to(REPO).as_posix()] = n
    assert found == REPLACED, (
        "decide access with store.reaches or private.can_reach_workspace / can_reach_grant, "
        f"not owner_id: {found}"
    )


SQL_DODGES = [
    "where w.owner_id = %s",
    "where w.owner_id=%s",
    "where %s=w.owner_id",
    "and w.owner_id=auth.uid()",
    "where (w.owner_id)=%s",
    "where w.owner_id::text=%s",
    "join public.workspaces w using (owner_id)",
    "where w.owner_id\n   = %s",
    "where w.owner_id in (select 1)",
    "w.owner_id is not distinct from auth.uid()",
    "where w.owner_id like %s",
]
SQL_FINE = [
    "insert into public.workspaces (owner_id, name) values (%s, %s)",
    "values (new.id, new.owner_id, 'owner')",
    "select id, owner_id, 'owner' from public.workspaces",
    "select id, name, owner_id from public.workspaces where id = %s",
    "-- where owner_id = %s\nselect 1",
]
PYTHON_DODGES = [
    "if workspace.owner_id == user.id:\n    pass",
    "if (\n    workspace.owner_id\n    == user.id\n):\n    pass",
    "ok = getattr(ws, 'owner_id') == uid",
    "x = getattr(ws, 'owner_id')",
    "import operator\nok = operator.eq(w.owner_id, uid)",
    "ok = uid in {w.owner_id}",
    "q = 'where w.owner_id=%s'",
    "q = '''select 1\n  where w.owner_id\n  = %s'''",
]
PYTHON_FINE = [
    "owner_id: str = 'x'",
    "def create_workspace(conn, owner_id: str, name: str): pass",
    "store.create_workspace(conn, owner_id=user_id)",
    "q = 'insert into public.workspaces (owner_id, name) values (%s, %s)'",
    "row = {'owner_id': user_id}",
]


def test_the_guard_catches_every_dodge() -> None:
    assert [s for s in SQL_DODGES if not sql_hits(s)] == []
    assert [s for s in SQL_FINE if sql_hits(s)] == []
    assert [s for s in PYTHON_DODGES if not python_hits(s)] == []
    assert [s for s in PYTHON_FINE if python_hits(s)] == []
