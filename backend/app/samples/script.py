"""The accountant script's steps, worked out against what's on a sample grant (ruling 47,
first version).

`resolve` turns one scripted step into the write the app's ordinary paths take: a record,
a file to bring in, or a sign-off. Its target is found by the step's stable references (a
ledger line ID on this grant, ruling 56; a file by its bytes on this grant; a record kind;
the checks' reason), never a record ID. A step whose target isn't there, because the agent
did otherwise or hasn't got to it, resolves to None: it's left for the user.

The same resolution serves the sample accountant when the user skips the human steps,
and the user in the do-everything play.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.contracts.charges import Charge
from app.contracts.checks import Bucket, ChecksInput, Problem
from app.contracts.records import (
    TERM_KINDS,
    Author,
    Bill,
    Judgment,
    Link,
    MailAction,
    MailDecision,
    Question,
    Record,
    RecordKind,
    citations,
)
from app.contracts.rules import RecordState
from app.contracts.workspaces import Grant
from app.db import store
from app.db.held_mail import still_held_mail
from app.db.platform import Platform
from app.db.store import Conn

from .pack import SamplePack, UserAction


@dataclass(frozen=True)
class WriteRecord:
    """A record the accountant writes, through the records route's path."""

    data: dict[str, Any]
    replaces_id: str | None = None


@dataclass(frozen=True)
class DeliverFile:
    """A file the user brings in, as an upload."""

    name: str


@dataclass(frozen=True)
class SignOff:
    note: str


Step = WriteRecord | DeliverFile | SignOff


@dataclass
class _Grant:
    """What's on the grant at the step's time."""

    pack: SamplePack
    charges: list[Charge]
    records: list[Record]
    state: RecordState
    copies: dict[str, list[str]]  # sha256 -> every file with it, first arrived first

    def file_id(self, name: str | None) -> str | None:
        return next(iter(self.copies.get(self.pack.sha256(name), [])), None) if name else None

    def file_ids(self, name: str) -> list[str]:
        """Every file on the grant with this file's bytes: the file and any copy of it."""
        return self.copies.get(self.pack.sha256(name), [])

    def charge_id(self, line_id: str | None) -> str | None:
        # Ruling 56: a line ID names a charge on this grant only.
        return next((c.id for c in self.charges if c.ledger_line_id == line_id), None)

    def cites(self, r: Record, file_id: str) -> bool:
        """Whether a record is about a file: it cites it, names it, or marks it as a copy
        (a duplicate's copy_file_id)."""
        return any(c.file_id == file_id for c in citations(r.data)) or file_id in (
            getattr(r.data, "file_id", None),
            getattr(r.data, "copy_file_id", None),
        )


def _on_grant(conn: Conn, grant: Grant, pack: SamplePack, at: datetime) -> _Grant:
    files = sorted(store.list_files(conn, grant.id, at), key=lambda f: f.arrived_at)
    records = store.list_records(conn, grant.id, at)
    copies: dict[str, list[str]] = {}
    for f in files:
        copies.setdefault(f.sha256, []).append(f.id)
    return _Grant(
        pack=pack,
        charges=store.list_charges(conn, grant.id, at),
        records=records,
        state=RecordState(records, files),
        copies=copies,
    )


def _waiting_by_agent(g: _Grant) -> list[Record]:
    return [r for r in g.state.waiting() if r.author == Author.AGENT]


def _confirm_terms(g: _Grant, a: UserAction) -> Step | None:
    file_id = g.file_id(a.file)
    ids = [
        r.id
        for r in _waiting_by_agent(g)
        if file_id is not None and r.kind in TERM_KINDS and g.cites(r, file_id)
    ]
    return WriteRecord({"kind": "confirmation", "record_ids": ids}) if ids else None


def _decide_suggestion(g: _Grant, a: UserAction) -> Step | None:
    charge_id = g.charge_id(a.line_id)
    file_id = g.file_id(a.file)
    ids = [
        r.id
        for r in _waiting_by_agent(g)
        if r.kind == RecordKind(a.suggestion or "")
        and (a.line_id is None or (charge_id is not None and r.charge_id == charge_id))
        and (a.file is None or (file_id is not None and g.cites(r, file_id)))
    ]
    if not ids:
        return None
    decision = "confirmed" if a.decision == "accept" else "rejected"
    return WriteRecord({"kind": "confirmation", "record_ids": ids, "decision": decision})


def _answer_flag(g: _Grant, a: UserAction) -> Step | None:
    charge_id = g.charge_id(a.line_id)
    flag = next(
        (
            r
            for r in reversed(g.state.current())
            if isinstance(r.data, Judgment)
            and r.data.question == Question.FLAG
            and r.author == Author.AGENT
            and charge_id is not None
            and r.data.charge_id == charge_id
        ),
        None,
    )
    if flag is None:
        return None
    assert isinstance(flag.data, Judgment)
    data = flag.data.model_dump(mode="json", include={"charge_id", "record_id", "file_id", "text"})
    data |= {
        "kind": "judgment",
        "question": "flag",
        "answer": a.answer,
        "reasoning": a.note or "The accountant's answer, from the sample's script.",
    }
    return WriteRecord(data, replaces_id=flag.id)


def _cents(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _enter_share(g: _Grant, a: UserAction) -> Step | None:
    """The accountant types the share of a bill a line takes (decision 0021): the agent's
    link from the bill to the line, again, with the typed share, its basis and the amount
    it works out to."""
    charge_id = g.charge_id(a.line_id)
    file_id = g.file_id(a.file)
    if charge_id is None or file_id is None or a.share is None or a.out_of is None:
        return None
    bills = {
        r.id: r.data for r in g.state.current() if isinstance(r.data, Bill) and g.cites(r, file_id)
    }
    link = next(
        (
            r
            for r in reversed(g.state.current())
            if isinstance(r.data, Link)
            and r.data.charge_id == charge_id
            and r.data.record_id in bills
        ),
        None,
    )
    if link is None:
        return None
    assert isinstance(link.data, Link)
    bill = bills[link.data.record_id]
    assert isinstance(bill, Bill)
    total = bill.total.value
    data = link.data.model_dump(
        mode="json", exclude={"stated_amount", "share", "amount_cents", "reason"}
    )
    data |= {
        "amount_cents": _cents(Decimal(total) * a.share / a.out_of),
        "share": {
            "share": {"value": str(a.share), "text": str(a.share)},
            "out_of": {"value": str(a.out_of), "text": str(a.out_of)},
            "total": {"value": total, "text": bill.total.text},
            "note": a.basis,
        },
        "reason": a.basis,
    }
    return WriteRecord(data, replaces_id=link.id)


def _let_in_mail(conn: Conn, grant: Grant, g: _Grant, a: UserAction, at: datetime) -> Step | None:
    sha = g.pack.sha256(a.file or "")
    held = next(
        (h for h in still_held_mail(conn, grant, at, g.state) if h.files[0].sha256 == sha),
        None,
    )
    if held is None:
        return None
    data = MailDecision(held_mail_id=held.id, action=MailAction.LET_IN)
    return WriteRecord(data.model_dump(mode="json"))


def _accept_reason(
    p: Platform, conn: Conn, grant: Grant, g: _Grant, a: UserAction, at: datetime
) -> Step | None:
    output = p.checks.run_checks(
        ChecksInput(
            now=at,
            charges=tuple(g.charges),
            files=tuple(store.list_files(conn, grant.id, at)),
            records=tuple(g.records),
            failed_runs=tuple(store.failed_runs(conn, grant.id)),
            skipped_files=tuple(store.list_skipped(conn, grant.id, at)),
        )
    )
    subject: dict[str, str] = {}
    problems: list[Problem] = []
    if a.line_id is not None:
        charge_id = g.charge_id(a.line_id)
        status = next((s for s in output.charges if s.charge_id == charge_id), None)
        if charge_id is None or status is None:
            return None
        subject = {"charge_id": charge_id}
        problems = [r for r in status.reasons if r.bucket != Bucket.EVIDENCE_COMPLETE]
    elif a.file is not None:
        # The file and every copy of it: a second copy carries the same-file problem.
        found = [
            (s.file_id, x)
            for s in output.records
            if s.file_id in g.file_ids(a.file)
            for x in s.problems
            if _matches(x, a)
        ]
        if not found:
            return None
        file_id, reason = found[0]
        return _accepted(a, reason, {"file_id": file_id or ""})
    else:
        problems = [p for s in output.grants if s.grant_id == grant.id for p in s.problems]
    reason = next((x for x in problems if _matches(x, a)), None)
    return _accepted(a, reason, subject) if reason is not None else None


def _matches(x: Problem, a: UserAction) -> bool:
    return (
        x.check == a.check
        and (a.problem is None or x.problem == a.problem)
        and x.accepted_by is None
    )


def _accepted(a: UserAction, reason: Problem, subject: dict[str, str]) -> WriteRecord:
    return WriteRecord(
        {
            "kind": "accepted_reason",
            **subject,
            "reason": {"check": reason.check, "problem": reason.problem},
            "note": a.note,
            "rests_on": list(reason.record_ids),
        }
    )


def resolve(
    p: Platform, conn: Conn, grant: Grant, pack: SamplePack, a: UserAction, at: datetime
) -> Step | None:
    """The write one scripted step takes at `at`, or None when its target isn't there."""
    g = _on_grant(conn, grant, pack, at)
    match a.action:
        case "confirm_terms":
            return _confirm_terms(g, a)
        case "deliver_file":
            return None if g.file_id(a.file) is not None else DeliverFile(a.file or "")
        case "decide_suggestion":
            return _decide_suggestion(g, a)
        case "answer_flag":
            return _answer_flag(g, a)
        case "enter_share":
            return _enter_share(g, a)
        case "let_in_mail":
            return _let_in_mail(conn, grant, g, a, at)
        case "accept_reason":
            return _accept_reason(p, conn, grant, g, a, at)
        case "sign_off":
            return SignOff(a.note or "")
        case _:
            raise ValueError(f"no step called {a.action!r}")
