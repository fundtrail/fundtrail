"""The eval runner (docs/eval.md, decision 0026): plays each case through the app and scores it.

Each case in `eval/cases/` is played on a fresh grant in a throwaway Postgres database, through
the app's ordinary paths: its files arrive as an upload or Gmail stores them, its ledger lines
as a ledger upload reads them, the clock replays each arrival in order (decision 0023), the job
worker runs the real agent on every run the clock queues, and the accountant's scripted steps
go through the records route's path. At each time the key names a bucket, the real checks put
the charge in one. At the end, the agent's current records are compared with the key.

Each expected item is right, missing or wrong (decision 0026, contracts.md section 14). No
partial credit: a link with the wrong amount is a missing link and a wrong one.

Run it from backend/, with a Postgres server where the user may create databases:

    cd backend && uv run python ../eval/run.py --cap-usd 10
    cd backend && uv run python ../eval/run.py --case credit-memo-spaced-dash --cap-usd 2
    cd backend && uv run python ../eval/run.py --fake    # no model calls: a fake model

The database server comes from --database-url or TEST_DATABASE_URL. The model key comes from
the environment as the app reads it (never printed), and ANTHROPIC_BASE_URL, when set, is where
the calls go. The runner reads nothing else from the environment: the database server is
only ever a local one (it refuses any other host, a hostaddr, a service, and a PGHOST that
isn't local), and while it runs it drops DATABASE_URL, the Supabase settings and the Gmail and
Drive settings from its own environment. Its job worker runs agent runs only, never the
periodic tasks (the Gmail and Drive checker among them).

Before each model call the runner checks the spend cap. It works out the call's worst case from
the request itself: its max_tokens of output, and its input (the larger of the last call's
input and a count from the request's size, priced as a cache write, the dearest input). It
refuses the call when the spend so far plus that worst case would pass the cap, which fails
that run, and stops the eval there.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time as clock_time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

EVAL = Path(__file__).resolve().parent
CASES = EVAL / "cases"
BACKEND = EVAL.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# claude-opus-5-5, dollars per million tokens. A cache write is the 5-minute one.
PRICE = {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0}
# A request's input tokens, counted from its size: at most one token per this many
# characters of its JSON, which overcounts, as a worst case should.
CHARS_PER_TOKEN = 3

# The files of a case that aren't evidence.
CASE_META = {"answer_key.json", "arrivals.json", "README.md"}


# Spending.


class CapReached(Exception):
    """A model call refused before it starts, because it could pass the spend cap."""

    retryable = False


@dataclass
class Usage:
    calls: int = 0
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    usd: float = 0.0

    def minus(self, other: Usage) -> Usage:
        return Usage(
            calls=self.calls - other.calls,
            input=self.input - other.input,
            output=self.output - other.output,
            cache_read=self.cache_read - other.cache_read,
            cache_write=self.cache_write - other.cache_write,
            usd=self.usd - other.usd,
        )

    def copy(self) -> Usage:
        return Usage(**asdict(self))


def call_cost(input: int, output: int, cache_read: int, cache_write: int) -> float:
    return (
        input * PRICE["input"]
        + output * PRICE["output"]
        + cache_read * PRICE["cache_read"]
        + cache_write * PRICE["cache_write"]
    ) / 1e6


def request_tokens(request: Any) -> int:
    """An upper count of a request's input tokens, from the size of its JSON."""
    body = {
        "system": getattr(request, "system", None),
        "tools": getattr(request, "tools", None),
        "messages": getattr(request, "messages", None),
    }
    return len(json.dumps(body, default=str)) // CHARS_PER_TOKEN + 1


class Meter:
    """Wraps the agent's model client: counts each call's tokens and estimated cost, and
    refuses a call before it starts when its worst case could pass the cap."""

    def __init__(self, model: Callable[[Any], Any], cap_usd: float):
        self.model = model
        self.cap_usd = cap_usd
        self.used = Usage()
        self.last_input = 0  # the last call's input tokens: uncached, cache read and written
        self.stopped = False
        self._lock = threading.Lock()

    def worst_case(self, request: Any) -> float:
        """The most this call could cost: its max_tokens of output, and its input priced as a
        cache write, the dearest input."""
        tokens_in = max(self.last_input, request_tokens(request))
        return (
            int(getattr(request, "max_tokens", 0)) * PRICE["output"]
            + tokens_in * PRICE["cache_write"]
        ) / 1e6

    def __call__(self, request: Any) -> Any:
        with self._lock:
            worst = self.worst_case(request)
            if self.stopped or self.used.usd + worst > self.cap_usd:
                self.stopped = True
                raise CapReached(
                    f"spend cap ${self.cap_usd:.2f}: ${self.used.usd:.4f} spent, and the next "
                    f"call could cost up to ${worst:.4f}"
                )
        message = self.model(request)
        u = message.usage
        got = {
            "input": u.input_tokens or 0,
            "output": u.output_tokens or 0,
            "cache_read": getattr(u, "cache_read_input_tokens", None) or 0,
            "cache_write": getattr(u, "cache_creation_input_tokens", None) or 0,
        }
        cost = call_cost(**got)
        with self._lock:
            self.used.calls += 1
            self.used.input += got["input"]
            self.used.output += got["output"]
            self.used.cache_read += got["cache_read"]
            self.used.cache_write += got["cache_write"]
            self.used.usd += cost
            self.last_input = got["input"] + got["cache_read"] + got["cache_write"]
        return message


class EvalAgent:
    """The app's agent (`app.agent.run_agent`), with its model calls going through the meter.
    The same as the platform's ModuleAgent otherwise."""

    def __init__(self, meter: Meter):
        self.meter = meter

    def run(self, agent_input: Any, /) -> Any:
        from app.agent import run_agent
        from app.db.ports import AgentResult

        result = run_agent(agent_input, model=self.meter)
        return AgentResult(
            records=list(result.records),
            messages=list(result.messages),
            summary=result.summary,
            log=result.log,
            other_open_questions=list(result.other_open_questions),
        )


def fake_model(request: Any) -> Any:
    """A model that writes nothing: every turn ends with a short reply. For the runner's own
    tests and a free smoke run."""
    from anthropic.types import Message, TextBlock
    from anthropic.types import Usage as SdkUsage

    return Message(
        id=f"msg_{uuid.uuid4().hex[:12]}",
        type="message",
        role="assistant",
        model="claude-opus-5-5",
        content=[TextBlock(type="text", text="Nothing to add.", citations=None)],
        stop_reason="end_turn",
        stop_sequence=None,
        usage=SdkUsage(input_tokens=1000, output_tokens=100),
    )


# Storage the agent reads files from, in memory.


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, path: str, data: bytes, media_type: str, /) -> None:
        if path in self.objects:
            raise RuntimeError("already stored")
        self.objects[path] = (data, media_type)

    def get(self, path: str, /) -> bytes:
        return self.objects[path][0]

    def signed_url(self, path: str, expires_in: int, /) -> str:
        return f"memory://{path}"


# The throwaway database.


# The settings the app reads for a hosted project, and for the real Gmail and Drive. The
# runner never uses them, and drops them from its own environment while it runs, so nothing it
# imports can read them either.
HOSTED_SETTINGS = (
    "DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_SECRET",
    "GOOGLE_TOKEN_FILE",
    "FUNDTRAIL_MAILBOX",
)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCAL_ADDRESSES = {"127.0.0.1", "::1"}


class NotLocal(Exception):
    """The database server isn't on this machine."""


def _local_host(host: str) -> bool:
    return host in LOCAL_HOSTS or host.startswith("/")


def check_local(server_url: str, environ: dict[str, str] | None = None) -> None:
    """Refuse a database server that isn't on this machine: the eval only ever makes and
    drops throwaway databases on a local server. libpq connects to `hostaddr` over `host`,
    reads a `service` from a file, and fills an empty host from PGHOST, so each is checked."""
    from psycopg import conninfo

    env = os.environ if environ is None else environ
    params = {k: str(v) for k, v in conninfo.conninfo_to_dict(server_url).items()}
    why = None
    if params.get("service") or env.get("PGSERVICE"):
        why = "a service, whose host is in a file"
    hosts = [h.strip() for h in (params.get("host") or env.get("PGHOST") or "").split(",")]
    addresses = [
        a.strip() for a in (params.get("hostaddr") or env.get("PGHOSTADDR") or "").split(",")
    ]
    if any(h and not _local_host(h) for h in hosts):
        why = "a host that isn't this machine"
    if any(a and a not in LOCAL_ADDRESSES for a in addresses):
        why = "a hostaddr that isn't this machine"
    if why:
        raise NotLocal(
            "The eval runs only against a Postgres server on this machine "
            f"(localhost, 127.0.0.1, ::1 or a socket), never a hosted one; this names {why}."
        )


@contextmanager
def without_hosted_settings() -> Iterator[None]:
    """Drop the hosted and the Gmail and Drive settings while the eval runs, then put them back."""
    saved = {name: os.environ.pop(name) for name in HOSTED_SETTINGS if name in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


@contextmanager
def throwaway_database(server_url: str) -> Iterator[str]:
    """A fresh database with the Supabase stubs and every migration, dropped afterwards."""
    from typing import LiteralString, cast

    import psycopg
    from psycopg import conninfo, sql

    check_local(server_url)

    from tests.db.conftest import SUPABASE_STUBS
    from tests.db.conftest import _migration_files as migration_files  # noqa: PLC2701

    name = f"fundtrail_eval_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(server_url, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
        url = conninfo.make_conninfo(server_url, dbname=name)
        try:
            with psycopg.connect(url, autocommit=True) as conn:
                conn.execute(SUPABASE_STUBS)
                for path in migration_files():
                    conn.execute(cast(LiteralString, path.read_text()))
            yield url
        finally:
            admin.execute(
                sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name))
            )


def drain(database_url: str) -> None:
    """Run the job worker until no agent run waits for it, as the worker process would, but
    with no periodic tasks: the Gmail and Drive checker, the daily recheck and the others never
    run in the eval. Anything but an agent run on the queue fails the eval."""
    import psycopg
    from procrastinate.periodic import PeriodicRegistry

    from app.db.jobs import QUEUE, TASK_NAME
    from app.db.worker import open_worker_app

    async def go() -> None:
        async with open_worker_app(database_url) as app:
            app.periodic_registry = PeriodicRegistry()
            await app.run_worker_async(
                queues=[QUEUE],
                concurrency=1,
                wait=False,
                listen_notify=False,
                install_signal_handlers=False,
            )

    for _ in range(50):
        asyncio.run(go())
        with psycopg.connect(database_url) as conn:
            other = conn.execute(
                "select distinct task_name from procrastinate_jobs where task_name <> %s",
                (TASK_NAME,),
            ).fetchall()
            if other:
                names = ", ".join(sorted(r[0] for r in other))
                raise RuntimeError(f"the eval's worker queued tasks it never runs: {names}")
            row = conn.execute(
                "select count(*) from procrastinate_jobs"
                " where task_name = %s and status in ('todo', 'doing')",
                (TASK_NAME,),
            ).fetchone()
        if row is None or row[0] == 0:
            return
        clock_time.sleep(0.2)
    raise RuntimeError("the worker didn't finish the queued runs")


# A case as the app's timeline reads it.


def case_folder(case_dir: Path, into: Path) -> Path:
    """The case in the sample pack layout: `timeline.json` (its file and ledger line arrivals),
    `user_actions.json` (the accountant's steps), its files and its ledger."""
    arrivals = json.loads((case_dir / "arrivals.json").read_text())
    folder = into / case_dir.name
    folder.mkdir(parents=True)
    for f in case_dir.iterdir():
        if f.is_file() and f.name not in CASE_META:
            shutil.copy(f, folder / f.name)
    events = [e for e in arrivals["events"] if e["kind"] != "accountant"]
    actions = [
        {k: v for k, v in e.items() if k != "kind"}
        for e in arrivals["events"]
        if e["kind"] == "accountant"
    ]
    (folder / "timeline.json").write_text(json.dumps({"sample": case_dir.name, "events": events}))
    (folder / "user_actions.json").write_text(json.dumps({"actions": actions}))
    return folder


# Scoring (contracts.md section 14, decision 0026).


def norm(value: Any) -> str:
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, date | datetime):
        value = value.isoformat()
    if isinstance(value, Decimal):
        value = format(value, "f")
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


@dataclass(frozen=True)
class GotRecord:
    kind: str
    file: str | None
    fields: dict[str, str]

    def show(self) -> str:
        return f"{self.kind} from {self.file}: " + ", ".join(
            f"{k}={v}" for k, v in sorted(self.fields.items()) if k != "kind"
        )


@dataclass(frozen=True)
class GotLink:
    file: str | None
    line_id: str | None
    amount_cents: int | None

    def show(self) -> str:
        amount = "" if self.amount_cents is None else f" for {self.amount_cents}"
        return f"link {self.file} -> {self.line_id}{amount}"


@dataclass(frozen=True)
class GotBudget:
    line_id: str | None
    budget_line: str | None

    def show(self) -> str:
        return f"budget line {self.budget_line!r} for {self.line_id}"


@dataclass(frozen=True)
class GotAnswer:
    line_id: str | None
    question: str
    about_file: str | None
    answer: str

    def show(self) -> str:
        about = f" about {self.about_file}" if self.about_file else ""
        return f"{self.question}{about} on {self.line_id}: {self.answer}"


@dataclass(frozen=True)
class GotItem:
    """A checklist item the agent added: its charge, its amount, and the rate it comes from."""

    line_id: str | None
    needed: str
    amount_cents: int | None
    rate_file: str | None = None
    quantity: Decimal | None = None
    rate: Decimal | None = None

    def show(self) -> str:
        amount = "" if self.amount_cents is None else f" for {self.amount_cents}"
        rate = (
            f", {self.quantity} at {self.rate} from {self.rate_file}"
            if self.rate is not None
            else ""
        )
        return f"checklist item {self.needed!r} on {self.line_id}{amount}{rate}"


@dataclass
class Got:
    """What the agent left: its current records, as the key compares them."""

    records: list[GotRecord] = field(default_factory=list[GotRecord])
    links: list[GotLink] = field(default_factory=list[GotLink])
    budget_lines: list[GotBudget] = field(default_factory=list[GotBudget])
    answers: list[GotAnswer] = field(default_factory=list[GotAnswer])
    checklist_items: list[GotItem] = field(default_factory=list[GotItem])
    values_not_found: int = 0


@dataclass
class Tally:
    right: int = 0
    missing: list[str] = field(default_factory=list[str])
    wrong: list[str] = field(default_factory=list[str])


@dataclass
class CaseScore:
    case: str
    buckets: Tally = field(default_factory=Tally)
    links: Tally = field(default_factory=Tally)
    budget_lines: Tally = field(default_factory=Tally)
    answers: Tally = field(default_factory=Tally)
    records: Tally = field(default_factory=Tally)
    checklist_items: Tally = field(default_factory=Tally)
    # The parts of the agent's work this case's key doesn't score, and the agent's items
    # its key leaves unscored (ruling 81).
    unscored_parts: list[str] = field(default_factory=list[str])
    not_scored: list[str] = field(default_factory=list[str])
    # Every bucket read, as "<line> at <time>: <bucket>", in the order the key names them.
    bucket_values: list[str] = field(default_factory=list[str])
    false_clears: list[str] = field(default_factory=list[str])
    agent_false_clears: list[str] = field(default_factory=list[str])
    unsure: list[str] = field(default_factory=list[str])
    values_not_found: int = 0
    steps_left_for_user: list[str] = field(default_factory=list[str])
    usage: Usage = field(default_factory=Usage)
    stopped: bool = False
    seconds: float = 0.0


def _pair(expected: Sequence[Any], got: Sequence[Any], same: Callable[[Any, Any], bool]):
    """Each expected item matched to at most one agent item, and each agent item to at most
    one expected item, as many as can be (a maximum matching, so a loose expected item can't
    take the agent item a stricter one needed): the matched pairs, the expected items with no
    match, and the agent items that matched nothing."""
    fits = [[j for j, g in enumerate(got) if same(e, g)] for e in expected]
    owner: dict[int, int] = {}  # agent item -> expected item

    def place(i: int, seen: set[int]) -> bool:
        for j in fits[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or place(owner[j], seen):
                owner[j] = i
                return True
        return False

    for i in range(len(expected)):
        place(i, set())
    matched = {i: j for j, i in owner.items()}
    pairs = [(expected[i], got[matched[i]]) for i in range(len(expected)) if i in matched]
    missing = [expected[i] for i in range(len(expected)) if i not in matched]
    return pairs, missing, [g for j, g in enumerate(got) if j not in owner]


def _show_key_record(e: dict[str, Any]) -> str:
    fields = ", ".join(f"{k}={v}" for k, v in e["fields"].items())
    return f"{e['kind']} from {e['file']}: {fields}"


def _selected(entry: dict[str, Any], part: str, g: Any) -> bool:
    """Whether a key's not_scored entry picks this agent item (ruling 81)."""
    if entry["part"] != part:
        return False
    file = {
        "records": "file",
        "links": "file",
        "answers": "about_file",
        "checklist_items": "rate_file",
    }.get(part)
    checks = {
        "line_id": getattr(g, "line_id", None),
        "file": getattr(g, file, None) if file else None,
        "kind": getattr(g, "kind", None),
        "question": getattr(g, "question", None),
    }
    return all(checks[k] == v for k, v in entry.items() if k != "part")


def score_agent(key: dict[str, Any], got: Got, out: CaseScore) -> None:
    """The agent's part: records, links, budget lines, answers and, when the key has them,
    checklist items (decision 0026, 3 to 6). An agent item the key leaves unscored is
    neither right nor wrong (ruling 81)."""
    unscored = key.get("not_scored", [])

    def score(
        part: str,
        expected: Sequence[Any],
        items: Sequence[Any],
        same: Callable,
        show_expected: Callable[[Any], str],
    ) -> None:
        kept = []
        for g in items:
            if any(_selected(e, part, g) for e in unscored):
                out.not_scored.append(g.show())
            else:
                kept.append(g)
        pairs, missing, wrong = _pair(expected, kept, same)
        tally: Tally = getattr(out, part)
        tally.right = len(pairs)
        tally.missing = [show_expected(e) for e in missing]
        tally.wrong = [g.show() for g in wrong]

    def record_same(e: dict[str, Any], g: GotRecord) -> bool:
        return (
            e["kind"] == g.kind
            and e["file"] == g.file
            and all(norm(v) == g.fields.get(k) for k, v in e["fields"].items())
        )

    score("records", key["records"], got.records, record_same, _show_key_record)

    def link_same(e: dict[str, Any], g: GotLink) -> bool:
        return (
            e["file"] == g.file
            and e["line_id"] == g.line_id
            and e.get("amount_cents") == g.amount_cents
        )

    score(
        "links",
        key["links"],
        got.links,
        link_same,
        lambda e: GotLink(e["file"], e["line_id"], e.get("amount_cents")).show(),
    )

    def budget_same(e: dict[str, Any], g: GotBudget) -> bool:
        return e["line_id"] == g.line_id and norm(e["budget_line"]) == norm(g.budget_line or "")

    score(
        "budget_lines",
        key["budget_lines"],
        got.budget_lines,
        budget_same,
        lambda e: GotBudget(e["line_id"], e["budget_line"]).show(),
    )

    def answer_same(e: dict[str, Any], g: GotAnswer) -> bool:
        return (
            e["line_id"] == g.line_id
            and e["question"] == g.question
            and (e.get("about_file") is None or e.get("about_file") == g.about_file)
            and e["answer"] == g.answer
        )

    score(
        "answers",
        key["answers"],
        got.answers,
        answer_same,
        lambda e: GotAnswer(e["line_id"], e["question"], e.get("about_file"), e["answer"]).show(),
    )
    for g in got.answers:
        e = next(
            (
                e
                for e in key["answers"]
                if (e["line_id"], e["question"]) == (g.line_id, g.question)
                and (not e.get("about_file") or e["about_file"] == g.about_file)
            ),
            None,
        )
        if e is None:
            continue
        if g.answer == "supports" and e["answer"] in ("contradicts", "unsure"):
            out.agent_false_clears.append(f"{g.show()} (key: {e['answer']})")
        if g.answer == "unsure" and e["answer"] != "unsure":
            out.unsure.append(f"{g.show()} (key: {e['answer']})")

    def item_same(e: dict[str, Any], g: GotItem) -> bool:
        if e["line_id"] != g.line_id:
            return False
        if "amount_cents" in e and e["amount_cents"] != g.amount_cents:
            return False
        rate = e.get("rate")
        return rate is None or (
            g.rate_file == e.get("file")
            and g.quantity == Decimal(rate["quantity"])
            and g.rate == Decimal(rate["rate"])
        )

    def item_expected(e: dict[str, Any]) -> str:
        rate = e.get("rate")
        return GotItem(
            e["line_id"],
            e["needed"],
            e.get("amount_cents"),
            e.get("file") if rate else None,
            Decimal(rate["quantity"]) if rate else None,
            Decimal(rate["rate"]) if rate else None,
        ).show()

    if "checklist_items" in key:
        score(
            "checklist_items", key["checklist_items"], got.checklist_items, item_same, item_expected
        )
    else:
        out.unscored_parts.append("checklist_items")
    out.values_not_found = got.values_not_found


def score_bucket(expected: dict[str, Any], got: str | None, out: CaseScore, why: str = "") -> None:
    """One bucket the key names at one time (decision 0026, 1). `why` is the checks' reasons."""
    what = f"{expected['line_id']} at {expected['at']}"
    want = expected["bucket"]
    out.bucket_values.append(f"{what}: {got}")
    if got is None:
        out.buckets.missing.append(f"{what}: no bucket (key: {want})")
    elif got == want:
        out.buckets.right += 1
    else:
        because = f", because: {why}" if why else ""
        out.buckets.wrong.append(f"{what}: {got} (key: {want}){because}")
        if got == "evidence_complete":
            out.false_clears.append(f"{what}: evidence_complete (key: {want})")


# Reading what the app holds.


def _field_values(model: Any, prefix: str = "") -> Iterator[tuple[str, Any, Any]]:
    """Every value in a record's data by its path, with its citation for a cited value."""
    from pydantic import BaseModel

    from app.contracts.records import Citation, Cited

    for name, value in model:
        path = f"{prefix}{name}"
        if isinstance(value, Cited):
            yield path, value.value, value.citation
        elif isinstance(value, Citation):
            continue
        elif isinstance(value, BaseModel):
            yield from _field_values(value, f"{path}.")
        elif isinstance(value, tuple):
            for i, item in enumerate(value):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
                if isinstance(item, Cited):
                    yield f"{path}[{i}]", item.value, item.citation
                elif isinstance(item, BaseModel) and not isinstance(item, Citation):
                    yield from _field_values(item, f"{path}[{i}].")
        elif value is not None:
            yield path, value, None


def case_namer(files: Sequence[Any], names: dict[str, str]) -> Callable[[Any], str | None]:
    """The case file a stored file came from, as the key names it: found by its bytes, or by
    its parent's for an email's attachment (the key cites the email). The stored name is used
    for a file that isn't the case's."""
    by_id = {f.id: f for f in files}

    def case_name(f: Any) -> str | None:
        while f.parent_id and f.parent_id in by_id:
            f = by_id[f.parent_id]
        return names.get(f.sha256, f.name)

    return case_name


def what_the_agent_left(
    records: Sequence[Any], files: Sequence[Any], charges: Sequence[Any], case_name: Callable
) -> Got:
    """The agent's current records on the grant, as the key compares them."""
    from app.contracts.records import (
        FACT_KINDS,
        TERM_KINDS,
        Author,
        BudgetAssignment,
        ChecklistItem,
        Judgment,
        Link,
        Match,
        citations,
    )
    from app.contracts.rules import RecordState

    state = RecordState(records, files)
    by_id = {r.id: r for r in records}
    name = {f.id: case_name(f) for f in files}
    line = {c.id: c.ledger_line_id for c in charges}

    def file_of(r: Any) -> str | None:
        for c in citations(r.data):
            return name.get(c.file_id)
        return name.get(getattr(r.data, "file_id", None) or "")

    got = Got()
    for r in state.current():
        if r.author != Author.AGENT:
            continue
        d = r.data
        if r.kind in TERM_KINDS or r.kind in FACT_KINDS:
            fields: dict[str, str] = {}
            for path, value, citation in _field_values(d):
                fields[path] = norm(value)
                if citation is not None and citation.match == Match.NOT_FOUND:
                    got.values_not_found += 1
            got.records.append(GotRecord(norm(r.kind), file_of(r), fields))
        elif isinstance(d, Link):
            fact = by_id.get(d.record_id)
            got.links.append(
                GotLink(file_of(fact) if fact else None, line.get(d.charge_id), d.amount_cents)
            )
        elif isinstance(d, BudgetAssignment):
            term = by_id.get(d.record_id)
            term_name = getattr(term.data, "name", None) if term else None
            got.budget_lines.append(
                GotBudget(
                    line.get(d.charge_id),
                    getattr(term_name, "value", term_name) if term_name is not None else None,
                )
            )
        elif isinstance(d, ChecklistItem):
            rate_file, quantity, rate = None, None, None
            if d.rate is not None:
                quantity = Decimal(str(d.rate.quantity.value))
                if d.rate.rate is not None:
                    rate = Decimal(str(d.rate.rate.value))
                    c = d.rate.rate.citation
                    rate_file = name.get(c.file_id) if c is not None else None
                elif d.rate.rate_id is not None and (term := by_id.get(d.rate.rate_id)):
                    rate = Decimal(str(term.data.rate.value))
                    rate_file = file_of(term)
            got.checklist_items.append(
                GotItem(line.get(d.charge_id), d.needed, d.amount_cents, rate_file, quantity, rate)
            )
        elif isinstance(d, Judgment) and d.charge_id is not None:
            about = by_id.get(d.record_id) if d.record_id else None
            got.answers.append(
                GotAnswer(
                    line.get(d.charge_id),
                    d.question.value,
                    file_of(about) if about else name.get(d.file_id or ""),
                    d.answer.value,
                )
            )
    return got


def bucket_at(p: Any, grant: Any, line_id: str, at: datetime) -> tuple[str | None, str]:
    """The real checks' bucket for a line at `at`, over everything on the grant then, as the
    key writes it (the bucket's value, or "reversed" for a fully reversed charge), with the
    checks' reasons for it."""
    from app.contracts.checks import ChecksInput
    from app.db import store
    from app.db.pool import transaction

    with transaction(p.pool) as conn:
        charges = store.list_charges(conn, grant.id, at)
        output = p.checks.run_checks(
            ChecksInput(
                now=at,
                charges=tuple(charges),
                files=tuple(store.list_files(conn, grant.id, at)),
                records=tuple(store.list_records(conn, grant.id, at)),
                failed_runs=tuple(store.failed_runs(conn, grant.id)),
                skipped_files=tuple(store.list_skipped(conn, grant.id, at)),
            )
        )
    return bucket_of(output, charges, line_id)


def bucket_of(output: Any, charges: Sequence[Any], line_id: str) -> tuple[str | None, str]:
    """A line's bucket in the checks' output as the key writes it: the bucket's value, or
    "reversed" for a fully reversed charge (decision 0026), with the checks' reasons."""
    charge = next((c for c in charges if c.ledger_line_id == line_id), None)
    if charge is None:
        return None, ""
    status = next((s for s in output.charges if s.charge_id == charge.id), None)
    if status is None:
        return None, ""
    why = "; ".join(r.text for r in status.reasons)
    return ("reversed" if status.reversed else status.bucket.value), why


# Playing a case.


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def play_case(
    p: Any, database_url: str, case_dir: Path, folder: Path, user_id: str, workspace_id: str
) -> CaseScore:
    from app.db import clock, store
    from app.db.actions import WriteRejected, add_record
    from app.db.pool import transaction
    from app.samples import player
    from app.samples.pack import load_folder
    from app.samples.script import WriteRecord, resolve

    meter: Meter = p.agent.meter
    started = clock_time.monotonic()
    before = meter.used.copy()
    key = json.loads((case_dir / "answer_key.json").read_text())
    pack = load_folder(folder)
    out = CaseScore(case=case_dir.name)

    steps: list[tuple[datetime, int, Any]] = [(e.at, 0, e) for e in pack.events]
    steps += [(a.at, 2, a) for a in pack.actions]
    steps += [(_time(b["at"]), 3, b) for b in key["buckets"]]
    steps.sort(key=lambda s: (s[0], s[1]))
    times = sorted({s[0] for s in steps})

    grant = None
    for at in times:
        here = [s for s in steps if s[0] == at]
        events = [s[2] for s in here if s[1] == 0]
        with transaction(p.pool) as conn:
            if grant is None:
                grant = store.create_grant(conn, workspace_id)
                store.get_grant(conn, grant.id, lock=True)
                old = None
            else:
                store.get_grant(conn, grant.id, lock=True)
                old = clock.grant_now(conn, grant.id)
            # The player's own storing step: each file as its channel stores it (a Gmail
            # file through the known-sender hold), each ledger line as an upload reads it.
            player.store_events(p, conn, grant, pack, [e.id for e in events])
            if old is None or at > old:
                clock.set_and_replay(p, conn, grant, old, at)
        drain(database_url)
        if meter.stopped:
            out.stopped = True
            break
        for _, _, action in (s for s in here if s[1] == 2):
            with transaction(p.pool) as conn:
                step = resolve(p, conn, grant, pack, action, at)
            if not isinstance(step, WriteRecord):
                out.steps_left_for_user.append(
                    f"{action.action} at {action.at.isoformat()}: its target isn't there"
                )
                continue
            try:
                add_record(p, grant, user_id, step.data, step.replaces_id)
            except WriteRejected as error:
                out.steps_left_for_user.append(f"{action.action}: refused: {error}")
            drain(database_url)
        for _, _, b in (s for s in here if s[1] == 3):
            got, why = bucket_at(p, grant, b["line_id"], at)
            score_bucket(b, got, out, why)

    if grant is not None:
        with transaction(p.pool) as conn:
            final = clock.grant_now(conn, grant.id)
            records = store.list_records(conn, grant.id, final)
            files = store.list_files(conn, grant.id, final)
            charges = store.list_charges(conn, grant.id, final)
        names = {pack.sha256(e.name): e.name for e in pack.events if e.kind.value == "file"}
        score_agent(
            key, what_the_agent_left(records, files, charges, case_namer(files, names)), out
        )
    out.usage = meter.used.minus(before)
    out.seconds = clock_time.monotonic() - started
    return out


@dataclass
class Run:
    cases: list[CaseScore]
    usage: Usage
    cap_usd: float
    model: str
    base_url: str | None
    started_at: str
    stopped: bool


def run_eval(
    server_url: str, case_names: Sequence[str] | None, cap_usd: float, model: Callable[[Any], Any]
) -> Run:
    """Play every case (or the named ones) on its own grant, in one throwaway database."""
    from app.contracts.workspaces import User
    from app.db import store
    from app.db.platform import Platform, set_platform
    from app.db.pool import open_pool, transaction
    from app.db.ports import ModuleChecks, NoPings

    check_local(server_url)
    dirs = sorted(d for d in CASES.iterdir() if (d / "answer_key.json").is_file())
    if case_names:
        unknown = set(case_names) - {d.name for d in dirs}
        if unknown:
            raise SystemExit(f"no such case: {', '.join(sorted(unknown))}")
        dirs = [d for d in dirs if d.name in case_names]
    meter = Meter(model, cap_usd)
    started = datetime.now(UTC).isoformat(timespec="seconds")
    scores: list[CaseScore] = []
    with (
        without_hosted_settings(),
        throwaway_database(server_url) as url,
        tempfile.TemporaryDirectory() as tmp,
    ):
        pool = open_pool(url, max_size=4)
        p = Platform(
            pool=pool,
            checks=ModuleChecks(),
            agent=EvalAgent(meter),
            storage=MemoryStorage(),
            pinger=NoPings(),
            run_retry_wait_seconds=0,
        )
        set_platform(p)
        try:
            user_id = str(uuid.uuid4())
            with transaction(pool) as conn:
                conn.execute("insert into auth.users (id) values (%s)", (user_id,))
                store.upsert_user(conn, User(id=user_id, email="eval.accountant@fundtrail.example"))
                workspace = store.create_workspace(conn, user_id, "Eval")
            for case_dir in dirs:
                if meter.stopped:
                    scores.append(CaseScore(case=case_dir.name, stopped=True))
                    continue
                folder = case_folder(case_dir, Path(tmp))
                scores.append(play_case(p, url, case_dir, folder, user_id, workspace.id))
        finally:
            set_platform(None)
            pool.close()
    return Run(
        cases=scores,
        usage=meter.used,
        cap_usd=cap_usd,
        model="claude-opus-5-5" if model is not fake_model else "fake",
        base_url=None if model is fake_model else os.environ.get("ANTHROPIC_BASE_URL"),
        started_at=started,
        stopped=meter.stopped,
    )


# The report.

PARTS = ("buckets", "links", "budget_lines", "answers", "records", "checklist_items")


def report(run: Run) -> str:
    lines = [
        f"Eval run {run.started_at}: model {run.model}, cap ${run.cap_usd:.2f}"
        + (f", calls through {run.base_url}" if run.base_url else ""),
        "",
    ]
    totals = {part: [0, 0, 0] for part in PARTS}
    for c in run.cases:
        lines.append(f"## {c.case}" + ("  (stopped at the spend cap)" if c.stopped else ""))
        for part in PARTS:
            t: Tally = getattr(c, part)
            lines.append(
                f"  {part:<13} right {t.right:>3}   missing {len(t.missing):>3}   "
                f"wrong {len(t.wrong):>3}"
            )
            totals[part][0] += t.right
            totals[part][1] += len(t.missing)
            totals[part][2] += len(t.wrong)
        lines.append(
            f"  false clears {len(c.false_clears)}, the agent's false clears "
            f"{len(c.agent_false_clears)}, unsure where the key has an answer {len(c.unsure)}, "
            f"values not found in their file {c.values_not_found}"
        )
        u = c.usage
        lines.append(
            f"  calls {u.calls}, tokens in {u.input} out {u.output} cache read {u.cache_read} "
            f"cache write {u.cache_write}, estimated ${u.usd:.4f}, {c.seconds:.0f}s"
        )
        for part in PARTS:
            t = getattr(c, part)
            lines += [f"  missing {part}: {m}" for m in t.missing]
            lines += [f"  wrong {part}: {w}" for w in t.wrong]
        lines += [f"  false clear: {f}" for f in c.false_clears]
        lines += [f"  the agent's false clear: {f}" for f in c.agent_false_clears]
        lines += [f"  unsure: {f}" for f in c.unsure]
        lines += [f"  left for the user: {s}" for s in c.steps_left_for_user]
        lines += [f"  not scored, by the key: {s}" for s in c.not_scored]
        if c.unscored_parts:
            lines.append(f"  not in this key, so not scored: {', '.join(c.unscored_parts)}")
        lines.append("")
    lines.append("## All cases")
    for part in PARTS:
        r, m, w = totals[part]
        lines.append(f"  {part:<13} right {r:>3}   missing {m:>3}   wrong {w:>3}")
    lines.append(
        f"  false clears {sum(len(c.false_clears) for c in run.cases)}, the agent's false "
        f"clears {sum(len(c.agent_false_clears) for c in run.cases)}"
    )
    u = run.usage
    lines.append(
        f"  calls {u.calls}, tokens in {u.input} out {u.output} cache read {u.cache_read} "
        f"cache write {u.cache_write}, estimated ${u.usd:.4f} of the ${run.cap_usd:.2f} cap"
        + (" (stopped at the cap)" if run.stopped else "")
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--case", action="append", help="a case to run (default: all)")
    parser.add_argument("--cap-usd", type=float, default=10.0, help="the spend cap, in dollars")
    parser.add_argument("--database-url", default=os.environ.get("TEST_DATABASE_URL"))
    parser.add_argument("--fake", action="store_true", help="a fake model: no calls, no cost")
    parser.add_argument("--out", type=Path, help="where to save the results as JSON")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("give --database-url or set TEST_DATABASE_URL")
    if args.fake:
        model: Callable[[Any], Any] = fake_model
    else:
        from app.agent.model import AnthropicModel

        model = AnthropicModel()
    run = run_eval(args.database_url, args.case, args.cap_usd, model)
    print(report(run))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(asdict(run), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
