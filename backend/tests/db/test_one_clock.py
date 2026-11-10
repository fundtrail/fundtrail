"""One clock per grant: only app/db/clock.py asks the system what time it is for a grant.

Fails on a system-time read anywhere in the backend's app code, the migrations or the
frontend's source, outside clock.py and the machine-time uses listed below. Tests are
not scanned.

- Python is read as a syntax tree, so an aliased import (`from datetime import datetime
  as dt`), a bound method (`f = datetime.now`) or `getattr(datetime, "now")` is caught
  as well as a plain call. SQL is matched in every string constant except docstrings.
- Migrations are matched as SQL; only the real-time defaults listed are allowed.
- The frontend is matched by pattern.

The allow-list is keyed by file and function with an exact count, so a new read in the
same file, or a second one in an allowed function, fails. A listed use that's gone
fails too, so the list stays honest.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CLOCK = "backend/app/db/clock.py"

SQL = re.compile(
    r"\bnow\s*\(|\b(current_timestamp|current_date|current_time|localtimestamp|localtime)\b"
    r"|\b(clock_timestamp|statement_timestamp|transaction_timestamp|timeofday)\s*\(|'now'",
    re.IGNORECASE,
)
FRONTEND = re.compile(
    r"\bnew\s+(?:[\w$]+\.)*Date\b(?!\s*\(\s*[^\s)])|(?<![\w$.])(?<!new )Date\s*\("
    r"|\bDate\.now\b|\bperformance\.(?:now|timeOrigin)\b|\bTemporal\.Now\b"
)
FRONTEND_TYPES = ("*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.cjs", "*.mts", "*.cts")

_CLOCK_ATTRS: dict[tuple[str, ...], set[str]] = {
    ("datetime", "datetime"): {"now", "today", "utcnow"},
    ("datetime", "date"): {"today"},
}
_TIME_FUNCS = {"time", "time_ns", "localtime", "gmtime", "ctime", "asctime"}
_GETATTR_NAMES = {"now", "today", "utcnow", "time", "time_ns"}
# A call to an attribute by one of these names counts whatever the object before the dot
# is: sa.func.now(), func.current_timestamp(), D = datetime; D.now(), a star import.
_CALLED_NAMES = {
    "now",
    "utcnow",
    "today",
    "current_timestamp",
    "current_date",
    "localtimestamp",
    "clock_timestamp",
}

# Machine time, never a grant's time: (file, function) -> (exact count, why).
ALLOWED: dict[tuple[str, str], tuple[int, str]] = {
    ("backend/app/db/store.py", "insert_records"): (1, "stored order of records"),
    ("backend/app/db/store.py", "insert_messages"): (1, "stored order of thread messages"),
    ("backend/app/db/store.py", "set_run"): (2, "a run's started_at and finished_at, real time"),
    ("backend/app/db/jobs.py", "_RunRetry.get_retry_decision"): (1, "retry backoff"),
    ("backend/app/api/routes.py", "signed_link"): (1, "the signed-link expiry"),
    # Ingest dates what it brings by the grant clock (issue 157, done). This one is machine
    # time: Drive's settle check, against Drive's own real modified times.
    ("backend/app/ingest/checker.py", "check_drive"): (1, "Drive's settle check"),
}

# Real-time column defaults in the migrations: (table, column), by contract.
ALLOWED_DEFAULTS = {
    ("users", "created_at"),
    ("records", "created_at"),
    ("thread_messages", "created_at"),
    ("agent_runs", "queued_at"),
}
# Procrastinate's own schema: its job queue's timers, on its own tables.
THIRD_PARTY_MIGRATIONS = {"supabase/migrations/20261110210000_procrastinate_schema.sql"}


def python_hits(source: str) -> list[tuple[int, str]]:
    """(line, enclosing function) of each system-time read in Python source, once per
    read: a string constant with two SQL reads counts twice."""
    tree = ast.parse(source)
    names: dict[str, tuple[str, ...]] = {}  # local name -> the module or member it is
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in ("datetime", "time"):
                    names[a.asname or a.name] = (a.name,)
        elif isinstance(node, ast.ImportFrom) and node.module in ("datetime", "time"):
            for a in node.names:
                names[a.asname or a.name] = (node.module, a.name)
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    calls = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    owner: dict[int, str] = {}

    def mark(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = scope
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                inner = f"{scope}.{child.name}" if scope else child.name
            owner[id(child)] = inner
            mark(child, inner)

    mark(tree, "")
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        hit = 0
        if isinstance(node, ast.Attribute):
            base = node.value
            what: tuple[str, ...] = ()
            if isinstance(base, ast.Name):
                what = names.get(base.id, ())
            elif isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name):
                module = names.get(base.value.id)
                if module and len(module) == 1:
                    what = (module[0], base.attr)
            hit = int(
                node.attr in _CLOCK_ATTRS.get(what, set())
                or (what == ("time",) and node.attr in _TIME_FUNCS)
                or (id(node) in calls and node.attr in _CALLED_NAMES)
            )
        elif isinstance(node, ast.Name):
            what = names.get(node.id, ())
            hit = int(len(what) == 2 and what[0] == "time" and what[1] in _TIME_FUNCS)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            hit = 0 if id(node) in docstrings else len(SQL.findall(node.value))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            hit = int(
                node.func.id == "getattr"
                and len(node.args) > 1
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in _GETATTR_NAMES
            )
        out += [(getattr(node, "lineno", 0), owner.get(id(node), ""))] * hit
    return sorted(out)


def migration_hits(sql: str) -> list[tuple[int, str, str]]:
    """(line, table, column) of each system-time read in a migration, comments left out."""
    out: list[tuple[int, str, str]] = []
    table = ""
    for n, raw in enumerate(sql.splitlines(), start=1):
        line = raw.split("--", 1)[0]
        named = re.search(
            r"(?:create|alter) table (?:only )?(?:if (?:not )?exists )?(?:\w+\.)?(\w+)", line, re.I
        )
        if named:
            table = named.group(1)
        if SQL.search(line):
            added = re.search(r"add column (?:if not exists )?(\w+)", line, re.I)
            column = added.group(1) if added else (line.split() or [""])[0]
            out.append((n, table, column))
    return out


def _is_test(path: Path) -> bool:
    return (
        ".test." in path.name
        or ".spec." in path.name
        or "__tests__" in path.parts
        or "fixtures" in path.parts
    )


def _python_found() -> Counter[tuple[str, str]]:
    found: Counter[tuple[str, str]] = Counter()
    for path in sorted((REPO / "backend" / "app").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel == CLOCK:
            continue
        for _, function in python_hits(path.read_text(encoding="utf-8")):
            found[(rel, function)] += 1
    return found


def test_only_the_clock_reads_the_system_time_in_python() -> None:
    found = _python_found()
    wrong = {key: n for key, n in found.items() if key not in ALLOWED or ALLOWED[key][0] != n}
    assert wrong == {}, (
        "Ask app/db/clock.py (grant_now) for a grant's time, or add a machine-time use to "
        f"ALLOWED with its exact count and reason: {wrong}"
    )


def test_every_allowed_use_still_appears() -> None:
    found = _python_found()
    assert [key for key in ALLOWED if key not in found] == []


def test_the_migrations_default_only_real_time_columns_to_now() -> None:
    wrong: list[str] = []
    for path in sorted((REPO / "supabase" / "migrations").glob("*.sql")):
        rel = path.relative_to(REPO).as_posix()
        if rel in THIRD_PARTY_MIGRATIONS:
            continue
        for n, table, column in migration_hits(path.read_text(encoding="utf-8")):
            if (table, column) not in ALLOWED_DEFAULTS:
                wrong.append(f"{rel}:{n} ({table}.{column})")
    assert wrong == [], f"a grant date must come from the clock, not a default: {wrong}"


def test_the_frontend_never_reads_the_browser_clock() -> None:
    found = [
        f"{path.relative_to(REPO).as_posix()}:{n}"
        for ext in FRONTEND_TYPES
        for path in sorted((REPO / "frontend" / "src").rglob(ext))
        if not _is_test(path)
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if FRONTEND.search(line)
    ]
    assert found == [], f"show the server's time, not the browser's: {found}"


PYTHON_DODGES = [
    "from datetime import datetime\nx = datetime.now(UTC)",
    "from datetime import datetime\nx = datetime.now (UTC)",
    "from datetime import datetime as dt\nx = dt.now(UTC)",
    "import datetime as d\nx = d.datetime.now()",
    "import datetime\nx = datetime.datetime.utcnow()",
    "from datetime import date\nx = date.today()",
    "from datetime import date as D\nx = D.today()",
    "from datetime import datetime\nf = datetime.now\nf()",
    "from datetime import datetime\ngetattr(datetime, 'now')()",
    "import sqlalchemy as sa\nx = sa.func.now()",
    "from sqlalchemy import func\nx = func.current_timestamp()",
    "from datetime import *\nx = datetime.now()",
    "from datetime import datetime\nD = datetime\nx = D.now()",
    "x = __import__('datetime').datetime.now()",
    "x = type(stamp).now()",
    "import time\nx = time.time()",
    "import time\nx = time.time_ns()",
    "from time import time\nx = time()",
    "q = 'select now()'",
    "q = 'select now ()'",
    "q = 'select statement_timestamp()'",
    "q = 'select transaction_timestamp()'",
    "q = 'select timeofday()'",
    "q = \"select 'now'::timestamptz\"",
    "q = 'select current_time'",
    "q = 'select localtime'",
    "q = 'select current_timestamp'",
    "q = f'select {x}, clock_timestamp()'",
]
PYTHON_FINE = [
    "x = clock.grant_now(conn, grant.id)",
    "x = i.now",
    "from datetime import datetime\ny = datetime.fromisoformat(s)",
    'def f():\n    """Uses now() in its docstring."""\n',
]
FRONTEND_DODGES = [
    "const t = Date.now();",
    "const d = new Date();",
    "const d = new Date;",
    "const d = Date();",
    "const d = new window.Date();",
    "const d = new globalThis.Date();",
    "const d = new Date(Date.now());",
    "const t = performance.now();",
    "const t = performance.timeOrigin;",
    "const t = Temporal.Now.instant();",
]
FRONTEND_FINE = ["new Date(value)", "new Date(row.at)", "formatDate(x)"]


def test_the_check_catches_every_dodge() -> None:
    assert [s for s in PYTHON_DODGES if not python_hits(s)] == []
    assert [s for s in PYTHON_FINE if python_hits(s)] == []
    assert [s for s in FRONTEND_DODGES if not FRONTEND.search(s)] == []
    assert [s for s in FRONTEND_FINE if FRONTEND.search(s)] == []
    assert migration_hits("create table public.x (\n  at timestamptz default now()\n);") == [
        (2, "x", "at")
    ]
    assert migration_hits("-- default now()\nselect 1;") == []
    altered = "create table public.records (\n  id text\n);\nalter table public.statuses\n"
    altered += "  add column created_at timestamptz default now();"
    assert migration_hits(altered) == [(5, "statuses", "created_at")]
