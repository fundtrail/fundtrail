"""The prerun (decision 0027, ruling 47, first version).

A prerun is the sample's whole expected run-through, saved: its timeline played from the
first event to the last with the real agent, in a seeding workspace of its own, while
that workspace's sample accountant makes the scripted decisions through the app's ordinary
paths (one skipping move to the end, then the agent's runs drained). The grant it played is
kept as the saved result.

- **Its version** is a hash of the sample's folder, the whole agent package (prompts, tool
  definitions, effort, turn limits and rulebooks) and the model. A prerun is used only at
  the current version: a grant on the run-through of a stale or withdrawn one goes live.
- **The seeding workspace** has no person in it, only its sample accountant, who makes the
  moves. Its agent runs go on a job queue of their own that only the command's in-process
  worker takes, with no periodic tasks: the app's worker never runs them, and the command
  never runs anyone else's.
- **The spend cap** is checked before every model call: a call whose worst case (its
  input, estimated from its size, and its whole output allowance) could take the spend
  past the cap is refused, and the run fails without it. Every call's usage counts,
  retries and refused saves included.
- **The release gate:** a prerun is released only when, at every time in the sample's
  answer key, the checks give the key's bucket, and nothing in it stopped, failed or was
  left undone.
- **Loading:** a sample grant opened from a prerun stays on the run-through until a person
  does anything on it (decides, uploads, delivers, asks). While it is, a move copies the
  saved result up to the move's time at once, with new IDs everywhere (inside text too,
  and the signed report's stored copy) and this workspace's sample accountant as the
  author of the decisions; nothing runs.

Made by a person with `uv run python -m app.samples.prerun make <sample> --owner <user id>
--cap <dollars>`, against a database and Supabase given explicitly in the environment, on
this machine unless `--allow-remote`. It makes paid model calls, so it never runs in CI.
It prints the calls, the tokens and the cost.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import signal
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, LiteralString
from urllib.parse import urlsplit

from psycopg.types.json import Jsonb

from app.contracts.charges import Charge
from app.contracts.checks import ChecksInput
from app.contracts.evidence import EvidenceFile, storage_path
from app.contracts.mail import HeldMail
from app.contracts.records import Author, Record, RecordKind
from app.contracts.runs import RunStatus, Trigger
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant, SampleChoice
from app.db import clock, sample_store, store
from app.db.held_mail import grant_held_mail
from app.db.platform import Platform
from app.db.pool import transaction
from app.db.store import Conn

from .pack import DATA_DIR, LARGER_SAMPLE

AGENT_DIR = Path(__file__).resolve().parents[1] / "agent"

# Dollars per million tokens for claude-opus-5-5, for an estimate only. Input $4, output $20
# and cache reads $0.20 are the first-party list prices in Anthropic's model table (as of
# 2026-11-03); cache writes aren't in that table and are taken at 1.25 times input (the
# five-minute write rate). Check the published pricing page before quoting the figure;
# the command takes other prices with --prices.
PRICES_SOURCE = (
    "estimate at claude-opus-5-5 list prices per million tokens (Anthropic's model table, "
    "2026-11-03): input $4, output $20, cache reads $0.20; cache writes assumed 1.25x input"
)
PRICES = {
    "input_tokens": 4.00,
    "output_tokens": 20.00,
    "cache_read_input_tokens": 0.20,
    "cache_creation_input_tokens": 5.00,
}


class NotReleasable(Exception):
    """The prerun doesn't match the sample's expected results, or isn't current."""


@dataclass(frozen=True)
class Prerun:
    id: str
    sample: str
    version: str
    grant_id: str
    released: bool
    checked: int
    wrong: list[str] = field(default_factory=list[str])
    usage: dict[str, Any] = field(default_factory=dict[str, Any])


# The version.


def version(sample: str, data_dir: Path = DATA_DIR, agent_dir: Path = AGENT_DIR) -> str:
    """A hash of everything a prerun's result rests on: the sample's folder, the agent
    package (its prompts, tool definitions, effort, turn limits and rulebooks) and the
    model."""
    from app.agent import model

    h = hashlib.sha256()

    def add(label: str, data: bytes) -> None:
        h.update(f"{label}\0{len(data)}\0".encode())
        h.update(data)

    folder = data_dir / "samples" / sample
    for f in sorted(p for p in folder.rglob("*") if p.is_file()):
        add(f"sample/{f.relative_to(folder)}", f.read_bytes())
    for f in sorted(p for p in agent_dir.rglob("*") if p.is_file()):
        if "__pycache__" not in f.parts:
            add(f"agent/{f.relative_to(agent_dir)}", f.read_bytes())
    add("model", model.MODEL.encode())
    return h.hexdigest()


# Saved preruns.

_COLUMNS = "id, sample, version, grant_id, released, checked, wrong, usage"


def _prerun(row: dict[str, Any]) -> Prerun:
    return Prerun(**row)


def get(conn: Conn, prerun_id: str) -> Prerun | None:
    row = conn.execute(
        f"select {_COLUMNS} from public.sample_preruns where id = %s", (prerun_id,)
    ).fetchone()
    return _prerun(row) if row else None


def current(conn: Conn, sample: str, data_dir: Path = DATA_DIR) -> Prerun | None:
    """The newest released prerun of the sample at its current version, if any."""
    row = conn.execute(
        f"""select {_COLUMNS} from public.sample_preruns
            where sample = %s and version = %s and released order by seq desc limit 1""",
        (sample, version(sample, data_dir)),
    ).fetchone()
    return _prerun(row) if row else None


def unavailable_reason(conn: Conn, sample: str | None = None) -> str | None:
    """Why the prerun choice can't be opened now, or None when it can."""
    from .player import PACK_FOR_CHOICE

    sample = sample or PACK_FOR_CHOICE[SampleChoice.LARGER_PRERUN]
    if current(conn, sample) is not None:
        return None
    return "The already-read sample isn't made for this version of the app yet."


# The release gate.


def key_check(p: Platform, grant_id: str, sample: str) -> tuple[int, list[str]]:
    """The answer key's buckets on a played grant: how many were checked, and the ones the
    checks don't give. A fully reversed charge reads as "reversed", as the key writes it."""
    from .player import pack_for

    key = json.loads((pack_for(sample).folder / "answer_key.json").read_text())
    wrong: list[str] = []
    for b in key["buckets"]:
        at = datetime.fromisoformat(b["at"])
        with transaction(p.pool) as conn:
            charges = store.list_charges(conn, grant_id, at)
            output = p.checks.run_checks(
                ChecksInput(
                    now=at,
                    charges=tuple(charges),
                    files=tuple(store.list_files(conn, grant_id, at)),
                    records=tuple(store.list_records(conn, grant_id, at)),
                    failed_runs=tuple(store.failed_runs(conn, grant_id)),
                    skipped_files=tuple(store.list_skipped(conn, grant_id, at)),
                )
            )
        charge = next((c for c in charges if c.ledger_line_id == b["line_id"]), None)
        status = next((s for s in output.charges if charge and s.charge_id == charge.id), None)
        got = None if status is None else ("reversed" if status.reversed else status.bucket.value)
        if got != b["bucket"]:
            wrong.append(f"{b['line_id']} at {b['at']}: {got} != {b['bucket']}")
    return len(key["buckets"]), wrong


def release(p: Platform, prerun_id: str) -> Prerun:
    """Release a prerun: only when it's current and matches every expected bucket."""
    with transaction(p.pool) as conn:
        found = get(conn, prerun_id)
        if found is None:
            raise NotReleasable(f"There's no prerun {prerun_id}.")
        if found.version != version(found.sample):
            raise NotReleasable("It was made at another version: make it again.")
        if found.usage.get("stopped_at_cap"):
            raise NotReleasable("It stopped at the spend cap before the sample's end.")
        if found.wrong or not found.checked:
            raise NotReleasable(f"It doesn't match the expected results: {found.wrong}")
        conn.execute("update public.sample_preruns set released = true where id = %s", (found.id,))
        return Prerun(**{**found.__dict__, "released": True})


# The spend cap, call by call.


class SpendCapReached(Exception):
    """The prerun's spend cap: this model call could take the spend past it. Not worth
    retrying."""

    retryable = False
    log = None


@dataclass
class Budget:
    """What the prerun's model calls have spent, against its cap (dollars), at `prices`
    (dollars per million tokens, by usage field). Every call counts, whatever became of its
    run: a failed try, a refused save or a retry."""

    cap: float
    prices: dict[str, float] = field(default_factory=lambda: dict(PRICES))
    spent: float = 0.0
    held: float = 0.0  # the worst case of the calls under way
    calls: int = 0
    tokens: dict[str, int] = field(default_factory=dict[str, int])
    stopped: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def worst_case(self, request: Any) -> float:
        """The most one call could cost: its input, at the dearer input rate, estimated at
        a token for every three characters of the request (an overestimate), and its whole
        output allowance."""
        size = len(json.dumps([request.system, request.tools, request.messages], default=str))
        prices = self.prices
        input_price = max(
            prices.get("input_tokens", 0.0), prices.get("cache_creation_input_tokens", 0.0)
        )
        output_price = self.prices.get("output_tokens", 0.0)
        return ((size // 3) * input_price + request.max_tokens * output_price) / 1_000_000

    def start(self, request: Any) -> float:
        """Hold a call's worst case, or refuse the call: raises SpendCapReached."""
        worst = self.worst_case(request)
        with self._lock:
            if self.spent + self.held + worst > self.cap:
                self.stopped = True
                raise SpendCapReached(
                    f"the prerun's spend cap: ${self.spent:.2f} of ${self.cap:.2f} spent, "
                    f"and this call could cost up to ${worst:.2f}"
                )
            self.held += worst
        return worst

    def finish(self, worst: float, usage: Any) -> None:
        """A call ended: let go of its worst case and add what it used (None: nothing)."""
        with self._lock:
            self.held -= worst
            if usage is None:
                return
            self.calls += 1
            for name, price in self.prices.items():
                n = int(getattr(usage, name, 0) or 0)
                self.tokens[name] = self.tokens.get(name, 0) + n
                self.spent += n * price / 1_000_000

    def totals(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            **{name: self.tokens.get(name, 0) for name in self.prices},
            "spent_dollars": round(self.spent, 4),
            "cap_dollars": self.cap,
        }


class CappedModel:
    """The agent's model client under the budget: no call starts that could pass the cap.
    A refused call raises SpendCapReached, which fails its run (not retried)."""

    def __init__(self, inner: Any, budget: Budget) -> None:
        self.inner = inner
        self.budget = budget

    def __call__(self, request: Any) -> Any:
        worst = self.budget.start(request)
        usage = None
        try:
            message = self.inner(request)
            usage = getattr(message, "usage", None)
            return message
        finally:
            self.budget.finish(worst, usage)


def usage_of(p: Platform, grant_id: str, prices: dict[str, float] | None = None) -> dict[str, Any]:
    """The model calls and tokens of the runs' saved logs on the grant (each run's last
    try), and what they cost at `prices` (dollars per million tokens). The budget counts
    every call; this is what the saved runs show."""
    prices = prices or PRICES
    with transaction(p.pool) as conn:
        runs = store.list_runs(conn, grant_id)
    totals: dict[str, Any] = {"runs": len(runs), "calls": 0} | dict.fromkeys(prices, 0)
    for run in runs:
        if run.log_path is None:
            continue
        try:
            log = json.loads(p.storage.get(run.log_path))
        except Exception:  # noqa: BLE001 - a missing log counts nothing
            continue
        totals["calls"] += sum(1 for e in log.get("events", []) if e.get("event") == "response")
        for name in prices:
            totals[name] += int(log.get("usage", {}).get(name, 0) or 0)
    totals["cost_dollars"] = round(
        sum(totals[name] * price / 1_000_000 for name, price in prices.items()), 2
    )
    return totals


# Making one.


def _seeding_workspace(conn: Conn, creator_id: str, name: str) -> tuple[str, str, str]:
    """A seeding workspace that no person can reach: made by `creator_id` (kept as who
    made it), whose owner membership is then removed, so only its sample accountant is a
    member. Its runs go on a queue of their own. Returns the workspace, its queue and its
    sample accountant."""
    workspace = store.create_workspace(conn, creator_id, name)
    conn.execute(
        "delete from public.workspace_members where workspace_id = %s and role = 'owner'",
        (workspace.id,),
    )
    queue = f"prerun-{uuid.uuid4().hex[:16]}"  # a Postgres channel name is short
    conn.execute(
        "insert into public.sample_seeding (workspace_id, queue) values (%s, %s)",
        (workspace.id, queue),
    )
    return workspace.id, queue, store.sample_accountant_id(conn, workspace.id)


def stop_seeding(conn: Conn, workspace_id: str, reason: str) -> None:
    """A seeding workspace's play stops for good: its walks stop and its queued jobs go,
    so nothing goes on after the command that played it."""
    queue = conn.execute(
        "select queue from public.sample_seeding where workspace_id = %s", (workspace_id,)
    ).fetchone()
    for g in store.list_grants(conn, workspace_id):
        if sample_store.walk_target(conn, g.id) is not None:
            sample_store.stop_walk(conn, g.id, clock.grant_now(conn, g.id), reason)
    if queue is not None:
        conn.execute(
            "delete from procrastinate_jobs where queue_name = %s and status in ('todo', 'doing')",
            (queue["queue"],),
        )


def make(
    p: Platform,
    sample: str,
    creator_id: str,
    *,
    drain: Callable[[str], None],
    prices: dict[str, float] | None = None,
    budget: Budget | None = None,
) -> Prerun:
    """Play the sample's whole timeline in a new seeding workspace, the sample accountant
    making every scripted step, the agent's runs drained by `drain` (given the seeding
    queue); then check it against the answer key and save it, not yet released. If
    anything stops it, the play is stopped for good before the error goes on."""
    from .player import items_for, move, open_sample

    choice = SampleChoice.LARGER_LIVE if sample == LARGER_SAMPLE else SampleChoice.SMALL_LIVE
    made_at = version(sample)
    with transaction(p.pool) as conn:
        workspace_id, queue, accountant = _seeding_workspace(
            conn, creator_id, f"Prerun of {sample} {made_at[:8]}"
        )
    try:
        grant = open_sample(p, accountant, workspace_id, choice)
        end = max(i.at for i in items_for(sample)) + timedelta(days=1)
        move(p, accountant, grant, end, skip=True, sign_off=True)  # no user is present
        drain(queue)
    except BaseException as error:
        with transaction(p.pool) as conn:
            stop_seeding(conn, workspace_id, f"The prerun command stopped: {type(error).__name__}.")
        raise
    with transaction(p.pool) as conn:
        walking = sample_store.walk_target(conn, grant.id) is not None
        last = sample_store.last_move(conn, grant.id)
        assert last is not None  # the move just made
        left = [s for s in sample_store.move_scripted(conn, last.id) if s.state != "done"]
        failed = store.failed_runs(conn, grant.id)
    checked, wrong = key_check(p, grant.id, sample)
    usage = usage_of(p, grant.id, prices)
    if budget is not None:
        usage["all_calls"] = budget.totals()
        if budget.stopped:
            usage["stopped_at_cap"] = True
    if walking:
        wrong = [*wrong, "the walk didn't reach the sample's end: a step is still waiting"]
    if last.walk_stopped:
        wrong = [*wrong, last.walk_stopped]
    wrong = [*wrong, *(f"scripted step {s.step} at {s.at.isoformat()} was {s.state}" for s in left)]
    wrong = [
        *wrong,
        *(f"agent run {r.id} ({r.trigger.kind.value}) failed: {r.error}" for r in failed),
    ]
    with transaction(p.pool) as conn:
        row = conn.execute(
            f"""insert into public.sample_preruns
                  (sample, version, grant_id, checked, wrong, usage)
                values (%s, %s, %s, %s, %s, %s) returning {_COLUMNS}""",
            (sample, made_at, grant.id, checked, Jsonb(wrong), Jsonb(usage)),
        ).fetchone()
    assert row is not None
    return _prerun(row)


def cleanup(p: Platform) -> list[str]:
    """Remove the seeding workspaces no prerun was saved from (a command that stopped):
    their grants, files' rows and jobs. Returns the workspaces removed. Run it only while
    no prerun command is running."""
    with transaction(p.pool) as conn:
        rows = conn.execute(
            """select s.workspace_id from public.sample_seeding s
               where not exists (
                 select 1 from public.sample_preruns r
                   join public.grants g on g.id = r.grant_id
                 where g.workspace_id = s.workspace_id)"""
        ).fetchall()
        gone = [r["workspace_id"] for r in rows]
        for workspace_id in gone:
            stop_seeding(conn, workspace_id, "Removed: no prerun was saved from it.")
            conn.execute("delete from public.workspaces where id = %s", (workspace_id,))
    return gone


# The run-through.


def start_run_through(conn: Conn, grant_id: str, prerun_id: str) -> None:
    conn.execute(
        """insert into public.sample_runthrough (grant_id, prerun_id) values (%s, %s)
           on conflict (grant_id) do update
             set prerun_id = excluded.prerun_id, off = false, salt = gen_random_uuid()::text""",
        (grant_id, prerun_id),
    )


def take_off(conn: Conn, grant_id: str) -> None:
    conn.execute("update public.sample_runthrough set off = true where grant_id = %s", (grant_id,))


def run_through(conn: Conn, grant: Grant) -> Prerun | None:
    """The prerun a grant is still on the run-through of, or None. Off once a person did
    anything on the grant (sample_store.user_acted), or a decision is anyone's but the
    sample accountant's, or the prerun was withdrawn or isn't at the current version. It
    only reads: the caller takes the grant off when it moves."""
    row = conn.execute(
        "select prerun_id, off from public.sample_runthrough where grant_id = %s", (grant.id,)
    ).fetchone()
    if row is None or row["off"]:
        return None
    accountant = store.sample_accountant_id(conn, grant.workspace_id)
    users = {
        r.author_user_id for r in store.list_records(conn, grant.id) if r.author == Author.USER
    }
    if users - {accountant}:
        return None
    saved = get(conn, row["prerun_id"])
    if saved is None or not saved.released or saved.version != version(saved.sample):
        return None
    return saved


def is_on_run_through(conn: Conn, grant: Grant) -> bool | None:
    """For the panel: None on a sample grant not opened from a prerun."""
    row = conn.execute(
        "select 1 from public.sample_runthrough where grant_id = %s", (grant.id,)
    ).fetchone()
    return None if row is None else run_through(conn, grant) is not None


# Loading: the saved result, copied up to a time with new IDs.


@dataclass
class Loaded:
    """What a load copied that the move lists: the scripted steps it brought, by step."""

    scripted: list[sample_store.Scripted] = field(default_factory=list[sample_store.Scripted])


_MESSAGE_COLUMNS = (
    "id, workspace_id, grant_id, charge_id, record_id, author, author_user_id, run_id, text, "
    "written_at"
)


def load(
    p: Platform,
    conn: Conn,
    target: Grant,
    prerun: Prerun,
    after: datetime | None,
    until: datetime,
    move_id: int,
) -> Loaded:
    """Copy what the prerun's grant had in (after, until] onto `target`, with new IDs: files
    (and their originals), held mail, charges, records, the agent's runs and its thread
    messages, in the prerun's stored order. Every seeding ID is replaced, inside longer
    text too (a report's storage path, a sign-off snapshot's row keys), and a signed
    report's stored PDF is copied to the target's own path. Decisions are authored by the
    target workspace's sample accountant, and each record's read point is mapped onto what
    the target holds. The scripted steps it brings are recorded under `move_id`. The caller
    holds the target's lock, sets its clock and works out its statuses."""
    src = prerun.grant_id
    source = store.get_grant(conn, src)
    assert source is not None
    accountant = store.sample_accountant_id(conn, target.workspace_id)
    row = conn.execute(
        "select salt from public.sample_runthrough where grant_id = %s", (target.id,)
    ).fetchone()
    assert row is not None, "a grant loads only while it's on a run-through"
    salt = row["salt"]

    def new_id(old: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"fundtrail-prerun/{salt}/{old}"))

    def within(at: datetime) -> bool:
        return (after is None or at > after) and at <= until

    files = store.list_files(conn, src, store.END_OF_TIME)
    charges = store.list_charges(conn, src, store.END_OF_TIME)
    records = store.list_records(conn, src)
    held = grant_held_mail(conn, source, store.END_OF_TIME)
    runs = store.list_runs(conn, src)
    messages = [
        ThreadMessage.model_validate(r)
        for r in conn.execute(
            f"""select {_MESSAGE_COLUMNS} from public.thread_messages
                where grant_id = %s and author = 'agent' order by written_at, created_at, id""",
            (src,),
        ).fetchall()
    ]
    renamed = {x.id: new_id(x.id) for x in (*files, *charges, *records, *held, *messages)}
    renamed |= {src: target.id, source.workspace_id: target.workspace_id}
    seeding_ids = re.compile("|".join(re.escape(k) for k in sorted(renamed, key=len, reverse=True)))

    def remap(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: remap(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
        if isinstance(value, list):
            return [remap(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(value, str):
            return seeding_ids.sub(lambda m: renamed[m.group(0)], value)
        return value

    # Held mail first: a let-in record names its message.
    for h in held:
        if not within(h.held_at):
            continue
        copied = remap(h.model_dump(mode="json"))
        for n, f in enumerate(h.files):
            path = f"{target.workspace_id}/{target.id}/held-{copied['id']}/{n}-{f.name}"
            p.storage.put(path, p.storage.get(f.storage_path), f.media_type)
            copied["files"][n]["storage_path"] = path
        store.insert_held_mail(conn, HeldMail.model_validate(copied))

    # The new stored order of what's on the target, by the prerun's.
    seqs: dict[int, int] = {}
    old_by_new = {renamed[o.id]: o for o in (*files, *charges, *records)}
    for x in (
        *store.list_files(conn, target.id, store.END_OF_TIME),
        *store.list_charges(conn, target.id, store.END_OF_TIME),
        *store.list_records(conn, target.id),
    ):
        old = old_by_new.get(x.id)
        if old is not None and old.stored_seq is not None and x.stored_seq is not None:
            seqs[old.stored_seq] = x.stored_seq

    def read_point(old: int | None) -> int | None:
        if old is None:
            return None
        return max((new for o, new in seqs.items() if o <= old), default=0)

    def stored(table: LiteralString, row_id: str) -> int:
        row = conn.execute(
            f"select stored_seq from public.{table} where id = %s", (row_id,)
        ).fetchone()
        assert row is not None
        return int(row["stored_seq"])

    items: list[tuple[int, EvidenceFile | Charge | Record]] = [
        (f.stored_seq or 0, f) for f in files if within(f.arrived_at)
    ]
    items += [(c.stored_seq or 0, c) for c in charges if within(c.arrived_at)]
    # The sign-off is never loaded: the user always signs off themselves (ruling 77). Its
    # stored report and snapshot go with it.
    signed = {r.id for r in records if r.kind is RecordKind.SIGN_OFF}
    items += [
        (r.stored_seq or 0, r) for r in records if within(r.written_at) and r.id not in signed
    ]
    for old_seq, item in sorted(items, key=lambda x: x[0]):
        if isinstance(item, EvidenceFile):
            fid = renamed[item.id]
            path = storage_path(target.workspace_id, target.id, fid, item.name)
            p.storage.put(path, p.storage.get(item.storage_path), item.media_type)
            store.insert_file(
                conn,
                item.model_copy(
                    update={
                        "id": fid,
                        "workspace_id": target.workspace_id,
                        "grant_id": target.id,
                        "storage_path": path,
                        "parent_id": renamed[item.parent_id] if item.parent_id else None,
                        "stored_seq": None,
                    }
                ),
            )
            seqs[old_seq] = stored("evidence_files", fid)
        elif isinstance(item, Charge):
            cid = renamed[item.id]
            store.insert_charges(
                conn,
                [
                    item.model_copy(
                        update={
                            "id": cid,
                            "workspace_id": target.workspace_id,
                            "grant_id": target.id,
                            "stored_seq": None,
                        }
                    )
                ],
            )
            seqs[old_seq] = stored("charges", cid)
        else:
            raw = remap(item.model_dump(mode="json", exclude={"stored_seq"}))
            raw["read_through_seq"] = read_point(item.read_through_seq)
            if item.author == Author.USER:
                raw["author_user_id"] = accountant
            old_report = getattr(item.data, "report_path", None)
            if old_report:
                # The signed report's stored copy, at the path the remapped record names.
                report = p.storage.get(old_report)
                p.storage.put(raw["data"]["report_path"], report, "application/pdf")
            [saved] = store.insert_records(conn, [Record.model_validate(raw)])
            assert saved.stored_seq is not None
            seqs[old_seq] = saved.stored_seq

    # The agent's runs, done as they were, for what each event shows it wrote.
    run_ids: dict[str, str] = {}
    for run in reversed(runs):
        if not within(run.clock_now) or run.status not in (RunStatus.DONE, RunStatus.FAILED):
            continue
        trigger = Trigger(
            kind=run.trigger.kind, id=remap(run.trigger.id) if run.trigger.id else None
        )
        copy = store.insert_run(conn, target.workspace_id, target.id, trigger, run.clock_now)
        run_ids[run.id] = copy.id
        point = read_point(run.read_through_seq)
        if point is not None:
            store.set_read_point(conn, copy.id, point)
        store.set_run(
            conn, copy.id, run.status, finished=True, summary=run.summary, error=run.error
        )

    # What the agent wrote in threads, under the copied runs.
    store.insert_messages(
        conn,
        [
            ThreadMessage.model_validate(
                {**remap(m.model_dump(mode="json")), "run_id": run_ids[m.run_id]}
            )
            for m in messages
            if within(m.written_at) and m.run_id in run_ids
        ],
    )

    loaded = Loaded()
    for s in _scripted_of(conn, src):
        if s.state != "done" or not within(s.at) or s.record_id in signed:
            continue
        made = sample_store.Scripted(
            s.step,
            move_id,
            s.at,
            "done",
            record_id=renamed.get(s.record_id) if s.record_id else None,
            file_id=renamed.get(s.file_id) if s.file_id else None,
        )
        sample_store.insert_scripted(conn, target.id, made)
        loaded.scripted.append(made)
    return loaded


def _scripted_of(conn: Conn, grant_id: str) -> Sequence[sample_store.Scripted]:
    rows = conn.execute(
        """select step, move_id, at, state, record_id, file_id from public.sample_scripted
           where grant_id = %s order by at, step""",
        (grant_id,),
    ).fetchall()
    return [sample_store.Scripted(**r) for r in rows]


# The command.


def drain_jobs(database_url: str, queue: str) -> None:
    """Run the agent runs on the seeding queue, in this process, until none is left: no
    other queue, and none of the app's periodic tasks. A retry waiting for its time is
    waited for."""
    import psycopg
    from procrastinate.periodic import PeriodicRegistry

    from app.db.worker import open_worker_app

    async def go() -> None:
        async with open_worker_app(database_url) as app:
            periodic, app.periodic_registry = app.periodic_registry, PeriodicRegistry()
            try:
                await app.run_worker_async(
                    queues=[queue],
                    concurrency=1,
                    wait=False,
                    listen_notify=False,
                    install_signal_handlers=False,
                )
            finally:
                app.periodic_registry = periodic

    while True:
        asyncio.run(go())
        with psycopg.connect(database_url) as conn:
            row = conn.execute(
                "select count(*) from procrastinate_jobs"
                " where queue_name = %s and status in ('todo', 'doing')",
                (queue,),
            ).fetchone()
        if row is None or row[0] == 0:
            return
        time.sleep(2)  # a retry waits for its time


def _report(prerun: Prerun) -> str:
    u = prerun.usage
    every = u.get("all_calls")
    lines = [
        f"prerun {prerun.id} of {prerun.sample} at version {prerun.version[:12]}",
        f"expected buckets: {prerun.checked} checked; {len(prerun.wrong)} differences",
        *(["stopped at the spend cap: no call ran after it"] if u.get("stopped_at_cap") else []),
        *(f"  {w}" for w in prerun.wrong),
    ]
    if every is not None:
        lines += [
            f"every model call, retries and refused saves included: {every['calls']}",
            "  tokens: " + ", ".join(f"{k} {every.get(k, 0)}" for k in PRICES),
            f"  spent: ${every['spent_dollars']:.2f} of the ${every['cap_dollars']:.2f} cap "
            f"({PRICES_SOURCE})",
        ]
    lines += [
        f"agent runs: {u.get('runs', 0)}; their saved logs show {u.get('calls', 0)} model calls",
        "  tokens: " + ", ".join(f"{k} {u.get(k, 0)}" for k in PRICES),
        f"  cost: ${u.get('cost_dollars', 0):.2f} ({PRICES_SOURCE})",
        "released" if prerun.released else "not released",
    ]
    return "\n".join(lines)


LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _check_targets(allow_remote: bool) -> None:
    """The command runs only against a database and Supabase given in the environment,
    on this machine unless `allow_remote`. Nothing is read from a .env file."""
    for name in ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        if not os.environ.get(name):
            raise SystemExit(f"{name} isn't set: give it in the command's environment.")
    for name in ("DATABASE_URL", "SUPABASE_URL"):
        host = urlsplit(os.environ[name]).hostname or ""
        if not allow_remote and host not in LOCAL_HOSTS and not host.endswith(".localhost"):
            raise SystemExit(
                f"{name} points at {host or 'no host'}, not this machine. "
                "Pass --allow-remote to run against it."
            )


def _stop_on_term() -> None:
    """A terminated command stops as an interrupted one does, so the play stops for good."""

    def interrupt(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.samples.prerun",
        description="Make or release a sample's prerun. It makes paid model calls.",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="run against a database or Supabase that isn't on this machine",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    make_cmd = sub.add_parser("make", help="play the sample with the real agent and save it")
    make_cmd.add_argument("sample")
    make_cmd.add_argument(
        "--owner",
        required=True,
        help="the user ID kept as who made it; it gets no access to the seeding workspace",
    )
    make_cmd.add_argument("--release", action="store_true", help="release it if it matches")
    make_cmd.add_argument(
        "--cap",
        type=float,
        required=True,
        help="the spend cap, in dollars: no model call starts that could pass it",
    )
    make_cmd.add_argument("--prices", help="JSON of dollars per million tokens, by usage field")
    release_cmd = sub.add_parser("release", help="release a prerun that matches")
    release_cmd.add_argument("prerun_id")
    sub.add_parser(
        "cleanup",
        help="remove seeding workspaces no prerun was saved from (run with no command running)",
    )
    args = parser.parse_args(argv)
    _check_targets(args.allow_remote)

    from app.agent import check_no_tracing
    from app.agent.model import AnthropicModel
    from app.db.config import Settings
    from app.db.platform import set_platform
    from app.db.ports import ModuleAgent
    from app.db.worker import platform_from_env

    check_no_tracing()
    settings = Settings.from_env()
    p = platform_from_env(settings)
    set_platform(p)
    if args.command == "release":
        print(_report(release(p, args.prerun_id)))
        return 0
    if args.command == "cleanup":
        for workspace_id in cleanup(p):
            print(f"removed seeding workspace {workspace_id}")
        return 0
    prices = {**PRICES, **json.loads(args.prices)} if args.prices else dict(PRICES)
    # The agent's model calls go to ANTHROPIC_BASE_URL when it's set (the SDK reads it).
    print(f"model calls go to {os.environ.get('ANTHROPIC_BASE_URL') or 'api.anthropic.com'}")
    budget = Budget(cap=args.cap, prices=prices)
    p.agent = ModuleAgent(model=CappedModel(AnthropicModel(), budget))
    _stop_on_term()
    made = make(
        p,
        args.sample,
        args.owner,
        drain=lambda queue: drain_jobs(settings.database_url, queue),
        prices=prices,
        budget=budget,
    )
    if args.release:
        try:
            made = release(p, made.id)
        except NotReleasable as error:
            print(f"not released: {error}")
    print(_report(made))
    return 0 if made.released or not args.release else 1


if __name__ == "__main__":
    raise SystemExit(main())
