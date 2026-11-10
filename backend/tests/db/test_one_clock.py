"""One clock per grant: only app/db/clock.py asks the system what time it is for a grant.

Fails on a direct system-time call anywhere in the backend's app code or the frontend's
source, outside clock.py and the machine-time uses listed below (stored order, run timing,
retry backoff, the signed-link expiry, Drive's settle check). Tests are not scanned. A
listed use that no longer appears fails too, so the list stays honest.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CLOCK = "backend/app/db/clock.py"

PYTHON = re.compile(
    r"datetime\.(now|today|utcnow)\(|\butcnow\(|date\.today\(|\btime\.time\("
    # SQL in app queries
    r"|\bnow\(\)|\bcurrent_timestamp\b|\bcurrent_date\b|\bclock_timestamp\(|\blocaltimestamp\b",
    re.IGNORECASE,
)
FRONTEND = re.compile(r"\bDate\.now\(|\bnew Date\(\s*\)|\bperformance\.now\(")

# Machine time, never a grant's time: (file, text on the line) -> why.
ALLOWED: dict[tuple[str, str], str] = {
    ("backend/app/db/store.py", "clock_timestamp()"): "stored order of records and messages",
    ("backend/app/db/store.py", "started_at = case"): "run timing, in real time",
    ("backend/app/db/store.py", "finished_at = case"): "run timing, in real time",
    ("backend/app/db/jobs.py", "RetryDecision(retry_at=datetime.now(UTC)"): "retry backoff",
    ("backend/app/api/routes.py", "expires_at = datetime.now(UTC)"): "signed-link expiry",
    ("backend/app/ingest/checker.py", "real_now = real_now or datetime.now(UTC)"): (
        "Drive's settle check, against Drive's own real modified times"
    ),
}


def _is_test(path: Path) -> bool:
    name = path.name
    return (
        ".test." in name
        or ".spec." in name
        or "__tests__" in path.parts
        or "fixtures" in path.parts
    )


def _sources() -> list[tuple[Path, re.Pattern[str]]]:
    python = [(p, PYTHON) for p in (REPO / "backend" / "app").rglob("*.py")]
    frontend = [
        (p, FRONTEND)
        for ext in ("*.ts", "*.tsx", "*.js", "*.jsx")
        for p in (REPO / "frontend" / "src").rglob(ext)
        if not _is_test(p)
    ]
    return python + frontend


def _hits() -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for path, pattern in _sources():
        rel = path.relative_to(REPO).as_posix()
        if rel == CLOCK:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.search(line):
                out.append((rel, n, line.strip()))
    return out


def _allowed(rel: str, line: str) -> bool:
    return any(rel == f and text in line for f, text in ALLOWED)


def test_only_the_clock_reads_the_system_time() -> None:
    found = [f"{rel}:{n}: {line}" for rel, n, line in _hits() if not _allowed(rel, line)]
    assert found == [], (
        "Ask app/db/clock.py (grant_now) for a grant's time, or add a machine-time use "
        f"to ALLOWED with its reason: {found}"
    )


def test_every_allowed_use_still_appears() -> None:
    hits = _hits()
    unused = [
        key for key in ALLOWED if not any(rel == key[0] and key[1] in line for rel, _, line in hits)
    ]
    assert unused == [], f"remove these from ALLOWED: {unused}"


def test_the_check_catches_a_direct_call() -> None:
    assert PYTHON.search("now = datetime.now(UTC)")
    assert PYTHON.search("today = date.today()")
    assert PYTHON.search('conn.execute("select now()")')
    assert PYTHON.search("t = time.time()")
    assert FRONTEND.search("const t = Date.now();")
    assert FRONTEND.search("const d = new Date();")
    assert not FRONTEND.search("new Date(value)")
    assert not PYTHON.search("now = clock.grant_now(conn, grant.id)")
