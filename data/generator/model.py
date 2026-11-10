"""The seed's building blocks: a grant's files, ledger lines and answer key.

A `Grant` collects what arrives (files and ledger lines, each with its arrival
time), what the accountant does in the script the key assumes, and the key
itself in the format of docs/contracts.md section 14. `write()` puts it on disk
the way an eval case is laid out: the documents, `ledger.csv`,
`answer_key.json` and `arrivals.json` side by side.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

EVIDENCE_COMPLETE = "evidence_complete"
POSSIBLE_CONFLICT = "possible_conflict"
MISSING_EVIDENCE = "missing_evidence"
NEEDS_HUMAN = "needs_human"


def at(d: date, hour: int = 12, minute: int = 0) -> datetime:
    return datetime.combine(d, time(hour, minute), tzinfo=UTC)


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def midnight(d: date) -> datetime:
    return at(d, 0, 0)


def business_day(d: date) -> date:
    """The same day, or the Monday after a weekend."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


@dataclass
class Doc:
    name: str
    data: bytes
    text: str  # what a reader sees: the text, or the words drawn on a photo
    at: datetime
    source: str  # gmail, drive or upload
    sender: str | None = None
    note: str | None = None


@dataclass
class Line:
    line_id: str
    transaction_date: date
    posting_date: date
    amount_cents: int
    description: str
    account: str
    vendor: str = ""
    reference: str = ""
    original_line_id: str = ""
    note: str | None = None
    arrives: datetime | None = None  # set when the ledger is uploaded, not seeded


@dataclass
class Ordinary:
    """An ordinary charge whose bucket follows from its evidence alone.

    `needs` are the files that fill its checklist. Its bucket at a time is
    Possible conflict when its date is outside the period in force, Missing
    evidence while any of `needs` hasn't arrived, and Evidence complete after.
    """

    line: Line
    needs: list[str]


@dataclass
class Grant:
    slug: str
    award_number: str
    start: date
    end: date
    docs: list[Doc] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    accountant: list[dict] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    budget_lines: list[dict] = field(default_factory=list)
    answers: list[dict] = field(default_factory=list)
    buckets: list[dict] = field(default_factory=list)
    ordinary: list[Ordinary] = field(default_factory=list)
    # (confirmed at, new end date): a later end date confirmed by the accountant
    extensions: list[tuple[datetime, date]] = field(default_factory=list)
    horizon: datetime | None = None
    _seq: int = 0

    # ------------------------------------------------------------ building

    def next_line_id(self) -> str:
        self._seq += 1
        return f"L-{self.award_number[-4:]}-{self._seq:04d}"

    def doc(
        self,
        name: str,
        content: str | bytes,
        arrives: datetime,
        source: str,
        *,
        sender: str | None = None,
        note: str | None = None,
        text: str | None = None,
    ) -> Doc:
        assert all(d.name != name for d in self.docs), f"{self.slug}: {name} twice"
        if isinstance(content, str):
            data, shown = content.encode("utf-8"), content
        else:
            assert text is not None, f"{name}: binary content needs its text"
            data, shown = content, text
        d = Doc(name, data, shown, arrives, source, sender, note)
        self.docs.append(d)
        return d

    def line(
        self,
        transaction_date: date,
        posting_date: date,
        amount_cents: int,
        description: str,
        account: str,
        *,
        vendor: str = "",
        reference: str = "",
        note: str | None = None,
    ) -> Line:
        ln = Line(
            self.next_line_id(),
            transaction_date,
            posting_date,
            amount_cents,
            description,
            account,
            vendor,
            reference,
            note=note,
        )
        self.lines.append(ln)
        return ln

    def confirm(self, file: str, when: datetime, note: str) -> None:
        self.accountant.append(
            {
                "at": when,
                "kind": "accountant",
                "action": "confirm_terms",
                "file": file,
                "note": note,
            }
        )

    def record(self, kind: str, file: str, **fields: str) -> None:
        self.records.append({"kind": kind, "file": file, "fields": dict(fields)})

    def link(self, file: str, line: Line, amount_cents: int | None = None) -> None:
        item: dict = {"file": file, "line_id": line.line_id}
        if amount_cents is not None:
            item["amount_cents"] = amount_cents
        self.links.append(item)

    def budget(self, line: Line, name: str) -> None:
        self.budget_lines.append({"line_id": line.line_id, "budget_line": name})

    def answer(self, line: Line, question: str, answer: str, about_file: str | None = None) -> None:
        item = {"line_id": line.line_id, "question": question}
        if about_file:
            item["about_file"] = about_file
        item["answer"] = answer
        self.answers.append(item)

    def bucket(self, line: Line, when: datetime, bucket: str) -> None:
        self.buckets.append({"line_id": line.line_id, "at": when, "bucket": bucket})

    # ------------------------------------------------------------ ordinary charges

    def end_in_force(self, when: datetime) -> date:
        end = self.end
        for confirmed, new_end in self.extensions:
            if confirmed <= when:
                end = new_end
        return end

    def expected(self, o: Ordinary, when: datetime) -> str:
        if not (self.start <= o.line.transaction_date <= self.end_in_force(when)):
            return POSSIBLE_CONFLICT
        arrived = {d.name: d.at for d in self.docs}
        if any(n not in arrived or arrived[n] > when for n in o.needs):
            return MISSING_EVIDENCE
        return EVIDENCE_COMPLETE

    def line_arrival(self, ln: Line) -> datetime:
        return ln.arrives or midnight(ln.posting_date)

    def expect_ordinary(self) -> None:
        """Writes each ordinary charge's buckets: once it arrives, then at each change.

        The first check is at noon UTC on the day the line arrives. After that, a
        check follows one hour after each event that can change the bucket: one
        of its files arriving, or an extension being confirmed.
        """
        arrived = {d.name: d.at for d in self.docs}
        for o in self.ordinary:
            first = self.line_arrival(o.line)
            first = max(first + timedelta(hours=1), at(first.date()))
            events = sorted(
                {arrived[n] for n in o.needs if n in arrived and arrived[n] > first}
                | {c for c, _ in self.extensions if c > first}
            )
            last = None
            for when in [first, *(e + timedelta(hours=1) for e in events)]:
                if self.horizon and when > self.horizon:
                    break
                b = self.expected(o, when)
                if b != last:
                    self.bucket(o.line, when, b)
                    last = b

    # ------------------------------------------------------------ writing

    def ledger_csv(self) -> str:
        buf = io.StringIO()
        cols = [
            "line_id",
            "transaction_date",
            "posting_date",
            "amount",
            "description",
            "account",
            "vendor",
            "reference",
            "original_line_id",
        ]
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(cols)
        for ln in sorted(self.lines, key=lambda x: (x.posting_date, x.line_id)):
            dollars, cents = divmod(abs(ln.amount_cents), 100)
            amount = f"{'-' if ln.amount_cents < 0 else ''}{dollars}.{cents:02d}"
            w.writerow(
                [
                    ln.line_id,
                    ln.transaction_date.isoformat(),
                    ln.posting_date.isoformat(),
                    amount,
                    ln.description,
                    ln.account,
                    ln.vendor,
                    ln.reference,
                    ln.original_line_id,
                ]
            )
        return buf.getvalue()

    def arrival_events(self) -> list[dict]:
        events: list[tuple[datetime, int, dict]] = []
        for d in self.docs:
            ev: dict = {"at": d.at, "kind": "file", "file": d.name, "source": d.source}
            if d.sender:
                ev["sender"] = d.sender
            if d.note:
                ev["note"] = d.note
            events.append((d.at, 0, ev))
        for ln in self.lines:
            ev = {"at": self.line_arrival(ln), "kind": "ledger_line", "line_id": ln.line_id}
            if ln.note:
                ev["note"] = ln.note
            events.append((self.line_arrival(ln), 1, ev))
        for a in self.accountant:
            events.append((a["at"], 2, dict(a)))
        events.sort(key=lambda e: (e[0], e[1], e[2].get("file") or e[2].get("line_id") or ""))
        out = []
        for _, _, ev in events:
            ev = dict(ev)
            ev["at"] = iso(ev["at"])
            out.append(ev)
        return out

    def write(self, folder: Path, *, ledger_name: str = "ledger.csv") -> None:
        folder.mkdir(parents=True, exist_ok=True)
        for d in self.docs:
            (folder / d.name).write_bytes(d.data)
        (folder / ledger_name).write_text(self.ledger_csv(), encoding="utf-8")

    def key_json(self) -> str:
        order = {ln.line_id: i for i, ln in enumerate(self.lines)}
        buckets = sorted(self.buckets, key=lambda b: (order[b["line_id"]], b["at"]))
        key = {
            "case": self.slug,
            "award_number": self.award_number,
            "records": self.records,
            "links": self.links,
            "budget_lines": self.budget_lines,
            "answers": self.answers,
            "buckets": [{**b, "at": iso(b["at"])} for b in buckets],
        }
        return dump_key(key)

    def arrivals_json(self) -> str:
        return dump_list_obj({"case": self.slug, "events": self.arrival_events()}, "events")

    def write_key(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "answer_key.json").write_text(self.key_json(), encoding="utf-8")
        (folder / "arrivals.json").write_text(self.arrivals_json(), encoding="utf-8")


def _one_line(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False)


def dump_list_obj(obj: dict, list_key: str) -> str:
    """JSON with each item of one list on its own line, like the eval cases."""
    parts = []
    for k, v in obj.items():
        if k == list_key:
            items = ",\n".join(f"    {_one_line(i)}" for i in v)
            parts.append(f'  "{k}": [\n{items}\n  ]' if v else f'  "{k}": []')
        else:
            parts.append(f'  "{k}": {_one_line(v)}')
    return "{\n" + ",\n".join(parts) + "\n}\n"


def dump_key(key: dict) -> str:
    parts = []
    for k, v in key.items():
        if isinstance(v, list):
            items = ",\n".join(f"    {_one_line(i)}" for i in v)
            parts.append(f'  "{k}": [\n{items}\n  ]' if v else f'  "{k}": []')
        else:
            parts.append(f'  "{k}": {_one_line(v)}')
    return "{\n" + ",\n".join(parts) + "\n}\n"
