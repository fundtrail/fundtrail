"""The plays of a sample's timeline (issue 165), for the tests and the on-demand command.

- **Doing nothing.** No user action: step the clock through every scheduled event to the
  last, and let the agent's runs go. Nothing may fail.
- **Doing everything, checks only.** The accountant script (`user_actions.json`) through
  the API's ordinary routes at its times, and in place of the live agent, the sample's
  hand-written agent records (`agent_records.json`) stored at their times. At each time in
  the answer key, the real checks give the key's bucket.

`agent_records.json` uses placeholder IDs: `ws-sample`, `grant-<sample>`,
`file-<file name>`, `chg-<ledger line ID>` and `rec-...`. A play maps each to its own on
the grant it plays: a file by its bytes (sha256) on that grant, a charge by its ledger line
on that grant (line IDs are unique per grant, ruling 56), a record to a new ID. Nothing is
stored with a placeholder ID, so two copies of a sample never collide.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.contracts.charges import Charge
from app.contracts.checks import Bucket, ChecksInput, ChecksOutput
from app.contracts.records import Record
from app.contracts.rules import run_read_point
from app.contracts.workspaces import Grant
from app.db import store
from app.db.platform import Platform
from app.db.pool import transaction
from app.samples import player
from app.samples.pack import SamplePack, UserAction


def _time(text: str) -> datetime:
    return datetime.fromisoformat(text)


@dataclass
class Mapping:
    """Placeholder IDs to the play's own, worked out as the records need them."""

    pack: SamplePack
    grant: Grant
    records: dict[str, str] = field(default_factory=dict[str, str])

    def __call__(self, conn: store.Conn, value: str) -> str:
        if value == "ws-sample":
            return self.grant.workspace_id
        if value == f"grant-{self.pack.sample}":
            return self.grant.id
        if value.startswith("file-"):
            sha = self.pack.sha256(value.removeprefix("file-"))
            files = sorted(
                store.list_files(conn, self.grant.id, store.END_OF_TIME), key=lambda f: f.arrived_at
            )
            found = next((f.id for f in files if f.sha256 == sha), None)
            assert found is not None, f"{value} isn't on the grant yet"
            return found
        if value.startswith("chg-"):
            line_id = value.removeprefix("chg-")
            charges = store.list_charges(conn, self.grant.id, store.END_OF_TIME)
            found = next((c.id for c in charges if c.ledger_line_id == line_id), None)
            assert found is not None, f"{value} isn't on the grant yet"
            return found
        if value.startswith("rec-"):
            return self.records.setdefault(value, str(uuid.uuid4()))
        return value


# The fields that hold one ID, and the ones that hold a list of them, in contract records.
_ID_FIELDS = {
    "id",
    "workspace_id",
    "grant_id",
    "replaces_id",
    "record_id",
    "charge_id",
    "file_id",
    "copy_file_id",
    "original_file_id",
    "item_record_id",
    "reuses_id",
    "held_mail_id",
    "thread_message_id",
}
_ID_LIST_FIELDS = {"rests_on", "record_ids"}


def _mapped(raw: Any, to: Callable[[str], str]) -> Any:
    """`raw` with every ID field's placeholder mapped (passages and other text untouched)."""
    if isinstance(raw, dict):
        out: dict[str, Any] = {}
        for k, v in raw.items():  # pyright: ignore[reportUnknownVariableType]
            if k in _ID_FIELDS and isinstance(v, str):
                out[k] = to(v)
            elif k in _ID_LIST_FIELDS and isinstance(v, list):
                out[k] = [to(x) if isinstance(x, str) else x for x in v]  # pyright: ignore[reportUnknownVariableType]
            else:
                out[k] = _mapped(v, to)
        return out
    if isinstance(raw, list):
        return [_mapped(v, to) for v in raw]  # pyright: ignore[reportUnknownVariableType]
    return raw


def _pointed_first(raw: list[Any]) -> list[Any]:
    """The records of one moment in the file's order, except that a record comes after any
    record of that moment it points to, as a run writes a note before linking it."""
    ids = {r["id"] for r in raw}
    done: set[str] = set()
    out: list[Any] = []
    waiting = list(raw)
    while waiting:
        for r in waiting:
            points_to = {r["data"].get("record_id"), r.get("replaces_id")}
            points_to |= set(r["data"].get("rests_on") or ())
            needs = points_to & ids
            if needs <= done:
                out.append(r)
                done.add(r["id"])
                waiting.remove(r)
                break
        else:
            raise AssertionError("agent_records.json: records that point at each other")
    return out


def store_agent_records(p: Platform, grant: Grant, mapping: Mapping, raw: list[Any]) -> None:
    """Store the agent's records as a run at their time would: in order, each with the read
    point of everything stored on the grant by then."""
    with transaction(p.pool) as conn:
        store.get_grant(conn, grant.id, lock=True)
        records = [
            Record.model_validate(_mapped(r, lambda v: mapping(conn, v)))
            for r in _pointed_first(raw)
        ]
        at = max(r.written_at for r in records)
        read_point = run_read_point(
            store.list_records(conn, grant.id),
            store.list_charges(conn, grant.id, at),
            store.list_files(conn, grant.id, at),
        )
        store.insert_records(
            conn, [r.model_copy(update={"read_through_seq": read_point}) for r in records]
        )


# A key's bucket for a fully reversed charge (decision 0020): the checks keep its bucket
# and mark it reversed, so the key says "reversed" where Bucket has no such value.
REVERSED = "reversed"


def bucket_at(p: Platform, grant: Grant, line_id: str, at: datetime) -> str | None:
    """The real checks' bucket for a line at `at`, over everything visible then, as the key
    writes it: the bucket's value, or "reversed" for a fully reversed charge."""
    charges, output = checks_at(p, grant, at)
    charge = next(c for c in charges if c.ledger_line_id == line_id)
    status = next((s for s in output.charges if s.charge_id == charge.id), None)
    if status is None:
        return None
    return REVERSED if status.reversed else status.bucket.value


def checks_at(p: Platform, grant: Grant, at: datetime) -> tuple[list[Charge], ChecksOutput]:
    """The checks' output at `at`, over everything on the grant visible then."""
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
    return charges, output


@dataclass(frozen=True)
class Step:
    at: datetime
    # At one moment: the steps that bring files in (a delivery, a let-in), then the
    # agent's records (which read them), then the user's other actions (which decide on
    # them), then the key's checks.
    order: int
    kind: str
    payload: Any


def steps(pack: SamplePack) -> list[Step]:
    """Everything a do-everything play does, in time order."""
    agent = json.loads((pack.folder / "agent_records.json").read_text())["records"]
    key = json.loads((pack.folder / "answer_key.json").read_text())["buckets"]
    by_time: dict[datetime, list[Any]] = {}
    for r in agent:
        by_time.setdefault(_time(r["written_at"]), []).append(r)
    out = [Step(at, 1, "agent", records) for at, records in by_time.items()]
    brings_files = {"deliver_file", "let_in_mail"}
    out += [Step(a.at, 0 if a.action in brings_files else 2, "user", a) for a in pack.actions]
    out += [Step(_time(b["at"]), 3, "key", b) for b in key]
    return sorted(out, key=lambda s: (s.at, s.order))


@dataclass
class Result:
    checked: int = 0
    wrong: list[str] = field(default_factory=list[str])


Act = Callable[[Grant, UserAction, Mapping], None]


def play_everything(
    p: Platform, user_id: str, grant: Grant, act: Act, *, after_each_move: Callable[[], None]
) -> Result:
    """The checks-only do-everything play on an opened sample grant. `act` performs one of
    the user's actions through the API; `after_each_move` runs anything the move queued.

    It doesn't drain the agent runs the moves queue unless `after_each_move` does: the
    records come from agent_records.json, and the key's buckets are worked out by the
    checks directly, so the play needs no run to finish."""
    assert grant.sample is not None
    pack = player.pack_for(grant.sample.sample)
    mapping = Mapping(pack, grant)
    result = Result()
    with transaction(p.pool) as conn:
        now = store.get_grant(conn, grant.id)
    assert now is not None and now.clock_now is not None
    clock_at = now.clock_now
    for step in steps(pack):
        if step.at > clock_at:
            player.move(p, user_id, grant, step.at)
            clock_at = step.at
            after_each_move()
        if step.kind == "agent":
            store_agent_records(p, grant, mapping, step.payload)
        elif step.kind == "user":
            act(grant, step.payload, mapping)
        else:
            result.checked += 1
            got = bucket_at(p, grant, step.payload["line_id"], step.at)
            want = step.payload["bucket"]
            assert want == REVERSED or Bucket(want), want
            if got != want:
                result.wrong.append(f"{step.payload['line_id']} at {step.at}: {got} != {want}")
    return result


def act_through_api(api: Any) -> Act:
    """The user's scripted steps through the API's ordinary routes, as the test user: each
    resolved against the grant (app.samples.script), then written as the screens would.
    In a checks-only play every step's target is there."""
    import mimetypes

    from app.samples.script import DeliverFile, SignOff, WriteRecord, resolve
    from tests.db.platform_fixtures import run_worker_until_idle

    def act(grant: Grant, action: UserAction, mapping: Mapping) -> None:
        with transaction(api.platform.pool) as conn:
            step = resolve(api.platform, conn, grant, mapping.pack, action, action.at)
        assert step is not None, f"{action.action} at {action.at}: its target isn't there"
        if isinstance(step, WriteRecord):
            body = {"data": step.data, "replaces_id": step.replaces_id}
            response = api.client.post(
                f"/grants/{grant.id}/records", json=body, headers=api.headers
            )
        elif isinstance(step, DeliverFile):
            data = mapping.pack.file_bytes(step.name)
            media_type = mimetypes.guess_type(step.name)[0] or "application/octet-stream"
            response = api.client.post(
                f"/grants/{grant.id}/evidence",
                files={"file": (step.name, data, media_type)},
                headers=api.headers,
            )
        else:
            assert isinstance(step, SignOff)
            # A sign-off waits for the agent: let the queued runs go first.
            run_worker_until_idle(str(api.platform.pool.conninfo))
            response = api.client.post(
                f"/grants/{grant.id}/records",
                json={"data": {"kind": "sign_off", "note": step.note}},
                headers=api.headers,
            )
        assert response.status_code == 201, response.text

    return act


def play_nothing(
    p: Platform, user_id: str, grant: Grant, *, after_each_move: Callable[[], None]
) -> int:
    """The do-nothing play: step through every item to the end. Returns how many moves."""
    moves = 0
    while True:
        view_items = player.items_for(grant.sample.sample if grant.sample else "")
        with transaction(p.pool) as conn:
            now = store.get_grant(conn, grant.id)
        assert now is not None and now.clock_now is not None
        if not any(i.at > now.clock_now for i in view_items):
            return moves
        player.move(p, user_id, grant, None)
        moves += 1
        after_each_move()
