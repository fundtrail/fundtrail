"""The prerun (decision 0027, ruling 47, first version).

A prerun is the sample's whole expected run-through, saved: its timeline played from the
first event to the last with the real agent, in a seeding workspace of its own, while
that workspace's sample accountant makes the scripted decisions through the app's ordinary
paths (one skipping move to the end, then the agent's runs drained). The grant it played is
kept as the saved result.

- **Its version** is a hash of the sample's folder, the rulebook, the agent's prompts and
  its model. A prerun is used only at the current version.
- **The release gate:** a prerun is released only when, at every time in the sample's
  answer key, the checks give the key's bucket.
- **Loading:** a sample grant opened from a prerun stays on the run-through while every
  accountant decision on it is the sample accountant's scripted one. While it is, a move
  copies the saved result up to the move's time at once, with new IDs and this
  workspace's sample accountant as the author of the decisions; nothing runs. Once it's
  off (the user decides something, or a move passes a scripted step without skipping it),
  the agent works live from there.

Made by a person with `uv run python -m app.samples.prerun make <sample> --owner <user id>`:
it makes paid model calls, so it never runs in CI. It prints the calls and the cost.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, LiteralString

from psycopg.types.json import Jsonb

from app.contracts.charges import Charge
from app.contracts.checks import ChecksInput
from app.contracts.evidence import EvidenceFile, storage_path
from app.contracts.mail import HeldFile
from app.contracts.records import Author, Record
from app.contracts.runs import RunStatus, Trigger
from app.contracts.workspaces import Grant, SampleChoice
from app.db import sample_store, store
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


def version(sample: str, data_dir: Path = DATA_DIR) -> str:
    """A hash of everything a prerun's result rests on: the sample's folder, the rulebook,
    the agent's prompts and its model."""
    from app.agent.model import MODEL

    h = hashlib.sha256()

    def add(label: str, data: bytes) -> None:
        h.update(f"{label}\0{len(data)}\0".encode())
        h.update(data)

    folder = data_dir / "samples" / sample
    for f in sorted(p for p in folder.rglob("*") if p.is_file()):
        add(f"sample/{f.relative_to(folder)}", f.read_bytes())
    for f in sorted(p for p in (AGENT_DIR / "rulebooks").rglob("*") if p.is_file()):
        add(f"rulebook/{f.name}", f.read_bytes())
    add("prompts", (AGENT_DIR / "prompts.py").read_bytes())
    add("model", MODEL.encode())
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


# Making one.


class SpendCapReached(Exception):
    """The prerun's spend cap: no further run may start. Not worth retrying."""

    retryable = False
    log = None


class CappedAgent:
    """The agent with a spend cap (`cap`, dollars): it adds up what each run spent, from the
    usage in the run's debug log, and starts no run once what's spent plus `reserve` (what
    one more run might cost) would pass the cap. Each refused run fails at once, with no
    model call, so the walk still reaches its end and nothing is left half done."""

    def __init__(
        self, inner: Any, cap: float, reserve: float, prices: dict[str, float] | None = None
    ) -> None:
        self.inner = inner
        self.cap = cap
        self.reserve = reserve
        self.prices = prices or PRICES
        self.spent = 0.0
        self.stopped = False

    def _add(self, log: Any) -> None:
        if not isinstance(log, bytes):
            return
        try:
            usage = json.loads(log).get("usage", {})
        except ValueError:
            return
        self.spent += sum(
            int(usage.get(name, 0) or 0) * price / 1_000_000 for name, price in self.prices.items()
        )

    def run(self, agent_input: Any) -> Any:
        if self.spent + self.reserve > self.cap:
            self.stopped = True
            raise SpendCapReached(
                f"the prerun's spend cap: ${self.spent:.2f} spent, "
                f"and another run could pass ${self.cap:.2f}"
            )
        try:
            result = self.inner.run(agent_input)
        except Exception as error:
            self._add(getattr(error, "log", None))  # a failed try's calls count too
            raise
        self._add(result.log)
        return result


def usage_of(p: Platform, grant_id: str, prices: dict[str, float] | None = None) -> dict[str, Any]:
    """The model calls and tokens of every run on the grant, from the runs' debug logs, and
    what they cost at `prices` (dollars per million tokens)."""
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


def make(
    p: Platform,
    sample: str,
    owner_id: str,
    *,
    drain: Callable[[], None],
    prices: dict[str, float] | None = None,
    capped: CappedAgent | None = None,
) -> Prerun:
    """Play the sample's whole timeline in a new seeding workspace, the sample accountant
    making every scripted step, the agent's runs drained by `drain`; then check it against
    the answer key and save it, not yet released."""
    from .player import items_for, move, open_sample

    choice = SampleChoice.LARGER_LIVE if sample == LARGER_SAMPLE else SampleChoice.SMALL_LIVE
    made_at = version(sample)
    with transaction(p.pool) as conn:
        workspace = store.create_workspace(conn, owner_id, f"Prerun of {sample} {made_at[:8]}")
    grant = open_sample(p, owner_id, workspace.id, choice)
    end = max(i.at for i in items_for(sample)) + timedelta(days=1)
    move(p, owner_id, grant, end, skip=True)
    drain()
    with transaction(p.pool) as conn:
        walking = sample_store.walk_target(conn, grant.id) is not None
        last = sample_store.last_move(conn, grant.id)
        assert last is not None  # the move just made
        left = [s for s in sample_store.move_scripted(conn, last.id) if s.state != "done"]
    checked, wrong = key_check(p, grant.id, sample)
    usage = usage_of(p, grant.id, prices)
    if capped is not None and capped.stopped:
        usage["stopped_at_cap"] = True
    if walking:
        wrong = [*wrong, "the walk didn't reach the sample's end: a step is still waiting"]
    if last.walk_stopped:
        wrong = [*wrong, last.walk_stopped]
    wrong = [*wrong, *(f"scripted step {s.step} at {s.at.isoformat()} was {s.state}" for s in left)]
    with transaction(p.pool) as conn:
        row = conn.execute(
            f"""insert into public.sample_preruns
                  (sample, version, grant_id, checked, wrong, usage)
                values (%s, %s, %s, %s, %s, %s) returning {_COLUMNS}""",
            (sample, made_at, grant.id, checked, Jsonb(wrong), Jsonb(usage)),
        ).fetchone()
    assert row is not None
    return _prerun(row)


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
    """The prerun a grant is still on the run-through of, or None. A decision by anyone but
    the workspace's sample accountant takes it off for good."""
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
        take_off(conn, grant.id)
        return None
    return get(conn, row["prerun_id"])


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
    (and their originals), held mail, charges, records and the agent's runs, in the
    prerun's stored order. Decisions are authored by the target workspace's sample
    accountant, and each record's read point is mapped onto what the target holds. The
    scripted steps it brings are recorded under `move_id`. The caller holds the target's
    lock, sets its clock and works out its statuses."""
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
    ids = {x.id for x in (*files, *charges, *records)} | {h.id for h in held}

    def remap(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: remap(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
        if isinstance(value, list):
            return [remap(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(value, str):
            if value in ids:
                return new_id(value)
            if value == src:
                return target.id
            if value == source.workspace_id:
                return target.workspace_id
        return value

    # Held mail first: a let-in record names its message.
    for h in held:
        if not within(h.held_at):
            continue
        held_id = new_id(h.id)
        copied: list[HeldFile] = []
        for n, f in enumerate(h.files):
            path = f"{target.workspace_id}/{target.id}/held-{held_id}/{n}-{f.name}"
            p.storage.put(path, p.storage.get(f.storage_path), f.media_type)
            copied.append(f.model_copy(update={"storage_path": path}))
        store.insert_held_mail(
            conn,
            h.model_copy(
                update={
                    "id": held_id,
                    "workspace_id": target.workspace_id,
                    "grant_id": target.id,
                    "files": tuple(copied),
                }
            ),
        )

    # The new stored order of what's on the target, by the prerun's.
    seqs: dict[int, int] = {}
    for x in (
        *store.list_files(conn, target.id, store.END_OF_TIME),
        *store.list_charges(conn, target.id, store.END_OF_TIME),
        *store.list_records(conn, target.id),
    ):
        old = next((o for o in (*files, *charges, *records) if new_id(o.id) == x.id), None)
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
    items += [(r.stored_seq or 0, r) for r in records if within(r.written_at)]
    for old_seq, item in sorted(items, key=lambda x: x[0]):
        if isinstance(item, EvidenceFile):
            fid = new_id(item.id)
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
                        "parent_id": new_id(item.parent_id) if item.parent_id else None,
                        "stored_seq": None,
                    }
                ),
            )
            seqs[old_seq] = stored("evidence_files", fid)
        elif isinstance(item, Charge):
            cid = new_id(item.id)
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
            [saved] = store.insert_records(conn, [Record.model_validate(raw)])
            assert saved.stored_seq is not None
            seqs[old_seq] = saved.stored_seq

    # The agent's runs, done as they were, for what each event shows it wrote.
    for run in reversed(store.list_runs(conn, src)):
        if not within(run.clock_now) or run.status not in (RunStatus.DONE, RunStatus.FAILED):
            continue
        trigger = Trigger(
            kind=run.trigger.kind, id=remap(run.trigger.id) if run.trigger.id else None
        )
        copy = store.insert_run(conn, target.workspace_id, target.id, trigger, run.clock_now)
        point = read_point(run.read_through_seq)
        if point is not None:
            store.set_read_point(conn, copy.id, point)
        store.set_run(conn, copy.id, run.status, finished=True, summary=run.summary)

    loaded = Loaded()
    for s in _scripted_of(conn, src):
        if s.state != "done" or not within(s.at):
            continue
        made = sample_store.Scripted(
            s.step,
            move_id,
            s.at,
            "done",
            record_id=new_id(s.record_id) if s.record_id else None,
            file_id=new_id(s.file_id) if s.file_id else None,
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


def drain_jobs(database_url: str) -> None:
    """Run the job worker until no agent run waits."""
    import psycopg

    from app.db.jobs import QUEUE, TASK_NAME
    from app.db.worker import open_worker_app

    async def go() -> None:
        async with open_worker_app(database_url) as app:
            await app.run_worker_async(
                queues=[QUEUE], concurrency=1, wait=False, install_signal_handlers=False
            )

    while True:
        asyncio.run(go())
        with psycopg.connect(database_url) as conn:
            row = conn.execute(
                "select count(*) from procrastinate_jobs"
                " where task_name = %s and status in ('todo', 'doing')",
                (TASK_NAME,),
            ).fetchone()
        if row is None or row[0] == 0:
            return


def _report(prerun: Prerun) -> str:
    u = prerun.usage
    lines = [
        f"prerun {prerun.id} of {prerun.sample} at version {prerun.version[:12]}",
        f"expected buckets: {prerun.checked} checked, {len(prerun.wrong)} not matched",
        *(["stopped at the spend cap: nothing after it ran"] if u.get("stopped_at_cap") else []),
        *(f"  {w}" for w in prerun.wrong),
        f"agent runs: {u.get('runs', 0)}, model calls: {u.get('calls', 0)}",
        "tokens: " + ", ".join(f"{k} {u.get(k, 0)}" for k in PRICES),
        f"cost: ${u.get('cost_dollars', 0):.2f} ({PRICES_SOURCE})",
        "released" if prerun.released else "not released",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.samples.prerun",
        description="Make or release a sample's prerun. It makes paid model calls.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    make_cmd = sub.add_parser("make", help="play the sample with the real agent and save it")
    make_cmd.add_argument("sample")
    make_cmd.add_argument(
        "--owner", required=True, help="the user ID that owns the seeding workspace"
    )
    make_cmd.add_argument("--release", action="store_true", help="release it if it matches")
    make_cmd.add_argument(
        "--cap", type=float, required=True, help="the spend cap, in dollars (estimated)"
    )
    make_cmd.add_argument(
        "--reserve",
        type=float,
        default=1.50,
        help="dollars kept back for the next run: none starts once spent + reserve > cap",
    )
    make_cmd.add_argument("--prices", help="JSON of dollars per million tokens, by usage field")
    release_cmd = sub.add_parser("release", help="release a prerun that matches")
    release_cmd.add_argument("prerun_id")
    args = parser.parse_args(argv)

    from app.agent import check_no_tracing
    from app.db.config import Settings
    from app.db.platform import set_platform
    from app.db.worker import platform_from_env

    check_no_tracing()
    settings = Settings.from_env()
    p = platform_from_env(settings)
    set_platform(p)
    if args.command == "release":
        print(_report(release(p, args.prerun_id)))
        return 0
    prices = {**PRICES, **json.loads(args.prices)} if args.prices else PRICES
    # The agent's model calls go to ANTHROPIC_BASE_URL when it's set (the SDK reads it).
    print(f"model calls go to {os.environ.get('ANTHROPIC_BASE_URL') or 'api.anthropic.com'}")
    capped = CappedAgent(p.agent, args.cap, args.reserve, prices)
    p.agent = capped
    made = make(
        p,
        args.sample,
        args.owner,
        drain=lambda: drain_jobs(settings.database_url),
        prices=prices,
        capped=capped,
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
