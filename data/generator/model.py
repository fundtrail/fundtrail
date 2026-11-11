"""The seed's building blocks: a grant's files, ledger lines and answer key.

A `Grant` collects its scheduled events (files and ledger lines, each with its
arrival time), the user actions its answer key assumes, and the key itself in
the format of docs/contracts.md section 14. `write()` puts the documents and
`ledger.csv` on disk, and `write_key()` writes `timeline.json` (scheduled
events only), `user_actions.json` and `answer_key.json` beside them.

A timeline never holds a user decision. Confirming terms or delivering a file
is the user's, so it lives in `user_actions.json`, the script the key assumes.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from names import LEGACY, Org

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
    # "user": the user is expected to bring this file in (ruling 44). Its `at` is
    # its date: from then it waits under the timeline's Now until the user
    # delivers it. The clock never delivers it. In the play the key assumes,
    # the user delivers it on that date, so `at` is also when it arrives.
    deliver: str | None = None
    # For a typeset PDF: the first and last page each row of `text` is on, counted
    # from 1, and None for a blank row (typeset.locate). None for any other file.
    pages: list[tuple[int, int] | None] | None = None
    # For a picture of paper (images.py), a photo or a scan: for each row of `text`, its
    # words and each one's box on the picture as (left, top, width, height) in fractions
    # of it, and None for a blank row. None for any other file.
    words: list[list[tuple[str, tuple[float, float, float, float]]] | None] | None = None


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
    user_actions: list[dict] = field(default_factory=list)
    # When the whole ledger file arrives, for a grant whose ledger is one
    # scheduled event. Each line then arrives at the later of this and 00:00 UTC
    # on its posting date (decision 0023). None: each line is its own event.
    ledger_at: datetime | None = None
    starts_at: datetime | None = None
    # A short label for each highlight event (ruling 58), by file name, line ID, or
    # "ledger.csv" for a ledger event.
    highlights: dict[str, str] = field(default_factory=dict)
    # A Gmail file from an unknown sender is held until the accountant lets it in
    # (ruling 59): the file name, and when the script lets it in.
    held: dict[str, datetime] = field(default_factory=dict)
    # For agent_records.py: the rule an answer names, by line ID; each remainder
    # suggestion as (bill, the note that names the other award, that award); each
    # duplicate mark as (copy, original).
    agent_extras: dict = field(default_factory=dict)
    records: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    budget_lines: list[dict] = field(default_factory=list)
    answers: list[dict] = field(default_factory=list)
    buckets: list[dict] = field(default_factory=list)
    ordinary: list[Ordinary] = field(default_factory=list)
    # (confirmed at, new end date): a later end date confirmed by the accountant
    extensions: list[tuple[datetime, date]] = field(default_factory=list)
    horizon: datetime | None = None
    # A sample's documents are typeset PDFs (ordinary.put). The unused seed grants
    # keep the plain text and the typewriter PDFs they were built with.
    typeset: bool = False
    # The university, the funder's officials and the airline its documents name. The
    # samples set names.SAMPLES; the unused seed grants keep the placeholder names.
    org: Org = LEGACY
    # The documents that arrive as a scan or a phone photo of their typeset page, by
    # file name: an images.Scan or an images.Photo (issue 312).
    pictures: dict = field(default_factory=dict)
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
        deliver: str | None = None,
    ) -> Doc:
        assert all(d.name != name for d in self.docs), f"{self.slug}: {name} twice"
        if isinstance(content, str):
            data, shown = content.encode("utf-8"), content
        else:
            assert text is not None, f"{name}: binary content needs its text"
            data, shown = content, text
        d = Doc(name, data, shown, arrives, source, sender, note, deliver)
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

    def confirm(self, file: str, when: datetime, note: str, highlight: str | None = None) -> None:
        """The user confirms the terms read from a file: a user action, not an event."""
        self.script("confirm_terms", when, note, highlight, file=file)

    def deliver_file(
        self, file: str, when: datetime, note: str, highlight: str | None = None
    ) -> None:
        """The user brings in a file marked for them to deliver, by upload."""
        self.script("deliver_file", when, note, highlight, file=file)

    def script(
        self, action: str, when: datetime, note: str, highlight: str | None = None, **refs: str
    ) -> None:
        """A step of the accountant script (ruling 47). `refs` are stable references
        (a ledger line ID, a file name, a record kind) and the expected decision or
        values, never record IDs. `highlight` marks the step as a highlight's own, the
        user's part of it, with the label that highlight's timeline event carries
        (ruling 77): Next highlight leaves the step to the user."""
        step = {"at": when, "action": action, **refs}
        if highlight:
            step["highlight"] = highlight
        self.user_actions.append({**step, "note": note})

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

    def file_arrival(self, name: str) -> datetime:
        """When a file reaches the grant in the play the key assumes: when it's let in
        if it's held, else its scheduled time."""
        return self.held.get(name) or next(d.at for d in self.docs if d.name == name)

    def expected(self, o: Ordinary, when: datetime) -> str:
        if not (self.start <= o.line.transaction_date <= self.end_in_force(when)):
            return POSSIBLE_CONFLICT
        arrived = {d.name: self.file_arrival(d.name) for d in self.docs}
        if any(n not in arrived or arrived[n] > when for n in o.needs):
            return MISSING_EVIDENCE
        return EVIDENCE_COMPLETE

    def line_arrival(self, ln: Line) -> datetime:
        if self.ledger_at is not None:
            return max(self.ledger_at, midnight(ln.posting_date))
        return ln.arrives or midnight(ln.posting_date)

    def expect_ordinary(self) -> None:
        """Writes each ordinary charge's buckets: once it arrives, then at each change.

        The first check is at noon UTC on the day the line arrives. After that, a
        check follows one hour after each event that can change the bucket: one
        of its files arriving, or an extension being confirmed.
        """
        arrived = {d.name: self.file_arrival(d.name) for d in self.docs}
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

    def timeline_events(self) -> list[dict]:
        """The scheduled events, in time order. No user action is among them."""
        events: list[tuple[datetime, int, dict]] = []
        for d in self.docs:
            ev: dict = {"at": d.at, "kind": "file", "file": d.name, "source": d.source}
            if d.sender:
                ev["sender"] = d.sender
            if d.deliver:
                ev["deliver"] = d.deliver
            if d.name in self.highlights:
                ev["highlight"] = self.highlights[d.name]
            if d.note:
                ev["note"] = d.note
            events.append((d.at, 0, ev))
        if self.ledger_at is not None:
            ev = {
                "at": self.ledger_at,
                "kind": "ledger",
                "file": "ledger.csv",
                "note": "The ledger file arrives. Each line posts on its date.",
            }
            if "ledger.csv" in self.highlights:
                ev["highlight"] = self.highlights["ledger.csv"]
            events.append((self.ledger_at, 1, ev))
        else:
            for ln in self.lines:
                ev = {"at": self.line_arrival(ln), "kind": "ledger_line", "line_id": ln.line_id}
                if ln.line_id in self.highlights:
                    ev["highlight"] = self.highlights[ln.line_id]
                if ln.note:
                    ev["note"] = ln.note
                events.append((self.line_arrival(ln), 1, ev))
        events.sort(key=lambda e: (e[0], e[1], e[2].get("file") or e[2].get("line_id") or ""))
        return [{**ev, "at": iso(ev["at"])} for _, _, ev in events]

    def first_event_at(self) -> datetime:
        times = [d.at for d in self.docs] + [self.line_arrival(ln) for ln in self.lines]
        return min(times)

    def last_event_at(self) -> datetime:
        times = [d.at for d in self.docs] + [self.line_arrival(ln) for ln in self.lines]
        return max(times)

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

    def timeline_json(self) -> str:
        head = {
            "sample": self.slug,
            "starts_at": iso(self.starts_at or self.first_event_at()),
            "events": self.timeline_events(),
        }
        return dump_list_obj(head, "events")

    def user_actions_json(self) -> str:
        actions = sorted(
            self.user_actions,
            key=lambda a: (a["at"], a["action"], a.get("line_id", ""), a.get("file", "")),
        )
        body = {"sample": self.slug, "actions": [{**a, "at": iso(a["at"])} for a in actions]}
        return dump_list_obj(body, "actions")

    def write_key(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "answer_key.json").write_text(self.key_json(), encoding="utf-8")
        (folder / "timeline.json").write_text(self.timeline_json(), encoding="utf-8")
        (folder / "user_actions.json").write_text(self.user_actions_json(), encoding="utf-8")


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
