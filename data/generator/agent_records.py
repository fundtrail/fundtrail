"""The agent's expected records for a sample, for the checks-only do-everything play.

Issue 165, step 3. The checks-only play feeds these hand-written records to the
checks in place of the live agent's, then asserts the answer key's buckets. Each
record is shaped as the contract's `Record` (backend/app/contracts/records.py):
the envelope, author `agent`, and `data` of one kind. Every value the key
expects is here with its citation, plus what the checks need that the key
doesn't list: the links' checklist items and parts, the share behind part of a
bill, and an Allowable answer written again each time something new is linked.

IDs are placeholders the play maps to its own: the workspace is `ws-sample`, the
grant `grant-<sample>`, a file `file-<name>`, a charge `chg-<line ID>`, and each
record `rec-...`. Citations are counted, not typed: a text or email file gets a
`char_location`, a PDF a `page_location` (the row as the page gives it, with the
pages the typeset PDF puts it on), and an image an `image_box`: the box of the
string drawn on it that holds the value. Confirmations aren't here: they're the
accountant's, in `user_actions.json`.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from model import Grant, iso

ALLOWABLE = "Is this cost necessary and reasonable, and is it for this project?"
PHOTO_SUFFIXES = (".jpg", ".jpeg", ".png")
# A bill's total is cited on its total's row ("Total due"), not on a subtotal of the
# same amount.
TOTAL_ROW = re.compile(r"\btotal\b", re.IGNORECASE)
WORKSPACE = "ws-sample"

# Default checklist items by account code prefix and document (W2's table on main,
# backend/app/checks/account_groups.py). The longest prefix wins.
DEFAULT_ITEMS: list[tuple[str, str, str]] = [
    # (account prefix, kind of document, default item key)
    ("50", "appointment", "appointment_letter"),
    ("50", "effort", "effort_report"),
    ("51", "appointment", "appointment_letter"),
    ("51", "effort", "effort_report"),
    ("550", "bill", "bill"),
    ("5671", "bill", "payment_record"),
    ("5721", "expense", "expense_report"),
    ("5721", "bill", "bills"),
    ("590", "bill", "usage_statement"),
    ("53", "rate", "benefit_rate"),
]


def long_date(d: date) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def date_texts(d: date) -> list[str]:
    return [long_date(d), f"{d:%m/%d/%Y}", f"{d.day} {d:%b} {d.year}", d.isoformat()]


def money_texts(cents: int) -> list[str]:
    dollars, rest = divmod(abs(cents), 100)
    sign = "-" if cents < 0 else ""
    out = [f"{sign}${dollars:,}.{rest:02d}"]
    if rest == 0:
        out.append(f"{sign}${dollars:,}")
    return out


def money_in(line: str, cents: int) -> str | None:
    for t in money_texts(cents):
        if re.search(re.escape(t) + r"(?![\d,]|\.\d)", line):
            return t
    return None


def standalone(number: int, line: str) -> bool:
    """Whether a whole number stands on its own in a line, not inside "96-reaction"
    or "$10,000.00"."""
    return re.search(rf"(?<![\w$.,-]){number}(?![\w.,-])", line) is not None


def spaced(text: str) -> str:
    """Text as a PDF's page gives it: runs of spaces as one. The text renderers pad a
    table's cells with spaces, and a typeset page sets them in columns."""
    return " ".join(text.split())


def value_box(words: list, text: str) -> tuple[float, float, float, float]:
    """The box around a value on its row of a picture, as (left, top, right, bottom).

    `words` are the row's words and their boxes (left, top, width, height). The value's
    words are found among them, and the box is the one around those. A value that
    isn't whole words of the row gets the box of the whole row."""
    want = text.split()
    printed = [word for word, _ in words]
    at = next(
        (
            i
            for i in range(len(printed) - len(want) + 1)
            if want and printed[i : i + len(want)] == want
        ),
        None,
    )
    chosen = words if at is None else words[at : at + len(want)]
    if not chosen:
        raise LookupError(f"no words on the row for {text!r}")
    left = min(b[0] for _, b in chosen)
    top = min(b[1] for _, b in chosen)
    right = max(b[0] + b[2] for _, b in chosen)
    bottom = max(b[1] + b[3] for _, b in chosen)
    return round(left, 4), round(top, 4), round(right, 4), round(bottom, 4)


class Builder:
    def __init__(self, g: Grant, key: dict) -> None:
        self.g = g
        self.key = key
        self.docs = {d.name: d for d in g.docs}
        self.lines = {ln.line_id: ln for ln in g.lines}
        self.records: list[dict] = []
        self.rec_by_file: dict[str, str] = {}
        self.budget_rec: dict[str, str] = {}
        self.part_by_file: dict[str, dict] = {}
        self.grant_id = f"grant-{g.slug}"

    # ------------------------------------------------------------ citations

    def file_id(self, name: str) -> str:
        return f"file-{name}"

    def charge_id(self, line_id: str) -> str:
        return f"chg-{line_id}"

    def find(self, name: str, test, prefer: str | re.Pattern | None = None) -> tuple[int, str]:
        """The first line of a file passing `test`, or the first that also holds `prefer`,
        which is text to find in the line whatever its case, or a pattern."""
        rows = self.docs[name].text.split("\n")
        hits = [(i, r) for i, r in enumerate(rows) if test(r)]
        if not hits:
            raise LookupError(f"{name}: no line passes the test")
        if isinstance(prefer, re.Pattern):
            preferred = [h for h in hits if prefer.search(h[1])]
        else:
            preferred = [h for h in hits if prefer and prefer.casefold() in h[1].casefold()]
        return preferred[0] if preferred else hits[0]

    def citation(self, name: str, index: int, text: str = "") -> dict:
        doc = self.docs[name]
        rows = doc.text.split("\n")
        row = rows[index]
        passage = row.strip()
        if doc.words is not None:
            # A scan or a photo of a typeset page: the box around the value's own words
            # on this row, so a total's box sits on the total and not on a line's
            # amount that happens to be the same.
            left, top, right, bottom = value_box(doc.words[index] or [], text)
            box = {
                "type": "image_box",
                "page": 1,
                "left": left,
                "top": top,
                "width": round(right - left, 4),
                "height": round(bottom - top, 4),
            }
            return {
                "file_id": self.file_id(name),
                "passage": None,
                "location": box,
                "match": "exact",
            }
        if name.endswith(".pdf"):
            # The pages the typeset PDF puts the row on (typeset.locate). Pages count
            # from 1, and the end is exclusive.
            assert doc.pages is not None, f"{name}: a cited PDF has to be a typeset one"
            first, last = doc.pages[index] or (1, 1)
            location = {
                "type": "page_location",
                "start_page_number": first,
                "end_page_number": last + 1,
            }
            return {
                "file_id": self.file_id(name),
                "passage": spaced(passage),
                "location": location,
                "match": "exact",
            }
        if name.endswith(PHOTO_SUFFIXES):
            # The box of the drawn string, which is this row of the image's text.
            assert doc.boxes is not None, f"{name}: a cited image has to be a drawn one"
            left, top, width, height = doc.boxes[index]
            box = {
                "type": "image_box",
                "page": 1,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
            }
            return {
                "file_id": self.file_id(name),
                "passage": None,
                "location": box,
                "match": "exact",
            }
        start = sum(len(r) + 1 for r in rows[:index]) + (len(row) - len(row.lstrip()))
        location = {
            "type": "char_location",
            "start_char_index": start,
            "end_char_index": start + len(passage),
        }
        return {
            "file_id": self.file_id(name),
            "passage": passage,
            "location": location,
            "match": "exact",
        }

    def cited(self, name: str, value, text: str, index: int) -> dict:
        if name.endswith(".pdf") or self.docs[name].words is not None:
            # A page gives single spaces. A PDF's passage has them, and the value's text
            # has to be in it.
            value = spaced(value) if value == text else value
            text = spaced(text)
        return {"value": value, "text": text, "citation": self.citation(name, index, text)}

    def cited_text(self, name: str, value: str, prefer: str | None = None) -> dict:
        i, row = self.find(name, lambda r: value.casefold() in r.casefold(), prefer)
        start = row.casefold().index(value.casefold())
        return self.cited(name, value, row[start : start + len(value)], i)

    def cited_date(self, name: str, iso_date: str, prefer: str | None = None) -> dict:
        d = date.fromisoformat(iso_date)
        texts = date_texts(d)
        i, row = self.find(name, lambda r: any(t in r for t in texts), prefer)
        return self.cited(name, iso_date, next(t for t in texts if t in row), i)

    def cited_money(self, name: str, cents: int, prefer: str | re.Pattern | None = None) -> dict:
        i, row = self.find(name, lambda r: money_in(r, cents) is not None, prefer)
        return self.cited(name, cents, money_in(row, cents), i)

    # ------------------------------------------------------------ records

    def add(self, rec_id: str, written_at: datetime, data: dict, replaces: str | None = None):
        rec = {
            "id": rec_id,
            "workspace_id": WORKSPACE,
            "grant_id": self.grant_id,
            "author": "agent",
            "written_at": iso(written_at),
        }
        if replaces:
            rec["replaces_id"] = replaces
        rec["data"] = data
        self.records.append(rec)
        return rec_id

    def terms_and_facts(self) -> None:
        letter_dated = {}
        for n, r in enumerate(self.key["records"]):
            kind, name, f = r["kind"], r["file"], r["fields"]
            at = self.g.file_arrival(name)
            data: dict = {"kind": kind}
            if "dated" in f and kind != "bill":
                data["dated"] = self.cited_date(name, f["dated"], "Amendment Date")
                letter_dated[name] = data["dated"]
            if kind == "period_of_performance":
                if "start" in f:
                    data["start"] = self.cited_date(name, f["start"], "Start Date")
                data["end"] = self.cited_date(name, f["end"], "End Date")
            elif kind == "notice":
                for field, prefer in (
                    ("amendment_number", "Amendment Number"),
                    ("amendment_type", "Amendment Type"),
                ):
                    data[field] = self.cited_text(name, f[field], prefer)
                for field, prefer in (
                    ("obligated_by_amendment", "Obligated by this"),
                    ("obligated_to_date", "Obligated to Date"),
                ):
                    if field in f:
                        data[field] = self.cited_money(name, int(f[field]), prefer)
            elif kind == "budget_line":
                i, row = self.budget_row(name, f["name"])
                data["name"] = self.cited(name, f["name"], f["name"], i)
                data["amount"] = self.cited(
                    name, int(f["amount"]), money_in(row, int(f["amount"])), i
                )
                data["category"] = f["category"]
                # The first notice's line: the one a charge is assigned to.
                self.budget_rec.setdefault(f["name"], f"rec-budget-line-{n}")
            elif kind == "person":
                data["name"] = self.cited_text(name, f["name"])
                if "email" in f:
                    data["email"] = self.cited_text(name, f["email"])
                data["role"] = self.cited_text(name, f["role"], f["name"])
            elif kind == "bill":
                data["total"] = self.cited_money(name, int(f["total"]), TOTAL_ROW)
                if "vendor" in f:
                    data["vendor"] = self.cited_text(name, f["vendor"])
                if "dated" in f:
                    data["dated"] = self.cited_date(name, f["dated"], "date")
                items = sorted(
                    {int(k.split("[")[1].split("]")[0]) for k in f if k.startswith("items[")}
                )
                if items:
                    data["items"] = [
                        {
                            "description": self.cited_text(name, f[f"items[{j}].description"]),
                            "amount": self.cited_money(
                                name,
                                int(f[f"items[{j}].amount"]),
                                f[f"items[{j}].description"][:20],
                            ),
                        }
                        for j in items
                    ]
                self.part_by_file[name] = data["total"]["citation"]
            elif kind == "rate":
                data.update(self.rate(name, f))
            elif kind == "approval_rule":
                data.update(self.approval_rule(name, f))
            elif kind == "approval":
                data["approver_email"] = self.cited_text(name, f["approver_email"], "From:")
                data["covers"] = self.cited_text(name, self.approved_line(name))
                if "approved_on" in f:
                    data["approved_on"] = self.cited_date(name, f["approved_on"], "Date:")
                self.part_by_file[name] = data["covers"]["citation"]
            elif kind == "note":
                data.update(self.note(name))
                self.part_by_file[name] = data["statement"]["citation"]
            else:
                raise ValueError(f"no expected record of kind {kind} in a sample")
            rec_id = f"rec-budget-line-{n}" if kind == "budget_line" else f"rec-{kind}-{n}"
            if kind in ("bill", "note", "approval"):
                self.rec_by_file[name] = rec_id
            self.add(rec_id, at, data)

    def approval_rule(self, name: str, f: dict) -> dict:
        """The participant support condition: what it applies to, who approves, and
        its scope, each cited to the clause's words."""
        data = {
            "applies_to": self.cited_text(name, "participant support", "may not be diverted"),
            "approver": self.cited_text(name, "Program Officer", "cognizant"),
        }
        if "scope" in f:
            i, row = self.find(name, lambda r: "diverted" in r)
            data["scope"] = self.cited(name, f["scope"], "diverted", i)
        return data

    def rate(self, name: str, f: dict) -> dict:
        """One rate term from a rate agreement.

        A fixed row holds its group, rate and dates. A provisional term (no end) has
        its start cited from the PROV row and its group and rate from the latest
        fixed row for that group, which the PROV row says to keep using (PR 232).
        """
        start = date.fromisoformat(f["effective_from"])
        group = f["name"]
        if "effective_to" not in f:
            i_start, _ = self.find(
                name, lambda r: r.startswith("PROV.") and f"{start:%m/%d/%Y}" in r
            )
            fixed = [
                (i, r)
                for i, r in enumerate(self.docs[name].text.split("\n"))
                if r.startswith("FIXED") and r.rstrip().endswith(group)
            ]
            i, line = fixed[-1]
            return {
                "name": self.cited(name, group, group, i),
                "rate": self.cited(name, f["rate"], line.split()[3], i),
                "applies_to": self.cited(name, f["applies_to"], group, i),
                "effective_from": self.cited(
                    name, f["effective_from"], f"{start:%m/%d/%Y}", i_start
                ),
            }
        end = date.fromisoformat(f["effective_to"])

        def row(r: str) -> bool:
            return r.startswith("FIXED") and f"{start:%m/%d/%Y}" in r and r.rstrip().endswith(group)

        i, line = self.find(name, row)
        percent = line.split()[3]
        return {
            "name": self.cited(name, group, group, i),
            "rate": self.cited(name, f["rate"], percent, i),
            "applies_to": self.cited(name, f["applies_to"], group, i),
            "effective_from": self.cited(name, f["effective_from"], f"{start:%m/%d/%Y}", i),
            "effective_to": self.cited(name, f["effective_to"], f"{end:%m/%d/%Y}", i),
        }

    def approved_line(self, name: str) -> str:
        _, row = self.find(name, lambda r: r.strip().startswith("Approved."))
        return row.strip()

    def budget_row(self, name: str, line_name: str) -> tuple[int, str]:
        rows = self.docs[name].text.split("\n")
        start = rows.index("BUDGET")
        for i in range(start, len(rows)):
            plain = re.sub(r"\s+\$[\d,]+\s*$", "", rows[i]).strip()
            plain = re.sub(r"^[A-M]\.\s+", "", plain)
            if plain == line_name and "$" in rows[i]:
                return i, rows[i]
        raise LookupError(f"{name}: no budget row {line_name!r}")

    def note(self, name: str) -> dict:
        """A note's label, statement and, where the document states one, its period."""
        text = self.docs[name].text
        if name.startswith("effort_report"):
            i, row = self.find(name, lambda r: r.startswith("Reporting period:"))
            m = re.search(r"Reporting period: (.+?) to (.+)$", row)
            return {
                "label": "Certified effort report",
                "statement": self.cited(name, row.strip(), row.strip(), i),
                "period": self.period(name, i, m.group(1), m.group(2)),
            }
        if name.startswith("appointment_letter"):
            i, row = self.find(name, lambda r: r.startswith("Appointment period:"))
            m = re.search(r"Appointment period: (.+?) through (.+)$", row)
            return {
                "label": "Appointment letter",
                "statement": self.cited(name, row.strip(), row.strip(), i),
                "period": self.period(name, i, m.group(1), m.group(2)),
            }
        if name.startswith("expense_report"):
            i, row = self.find(name, lambda r: r.startswith("Purpose of trip:"))
            return {
                "label": "Travel expense report",
                "statement": self.cited(name, row.strip(), row.strip(), i),
            }
        if name.startswith("rate_agreement"):
            i, row = self.find(
                name, lambda r: r.startswith("FIXED") and "7/1/2025" in r and "Limited" in r
            )
            return {
                "label": "Fringe benefit rate agreement",
                "statement": self.cited(name, row.strip(), row.strip(), i),
            }
        if name.startswith("cost_transfer_justification"):
            i, row = self.find(name, lambda r: r.startswith("Why the transfer is needed:"))
            return {
                "label": "Cost transfer justification",
                "statement": self.cited(name, row.strip(), row.strip(), i),
            }
        if re.search(r"\b\d+ of (the )?\d+\b", text):
            i, row = self.find(name, lambda r: re.search(r"\b\d+ of (the )?\d+\b", r) is not None)
            return {
                "label": "Basis for splitting a shared bill",
                "statement": self.cited(name, row.strip(), row.strip(), i),
            }
        raise ValueError(f"{name}: no note shape for this file")

    def period(self, name: str, i: int, start: str, end: str) -> dict:
        def parse(t: str) -> str:
            return datetime.strptime(t.strip(), "%B %d, %Y").date().isoformat()

        return {
            "start": self.cited(name, parse(start), start.strip(), i),
            "end": self.cited(name, parse(end), end.strip(), i),
        }

    def default_item(self, line_id: str, name: str) -> str | None:
        if self.lines[line_id].original_line_id and name.startswith("cost_transfer_justification"):
            return "justification"
        account = self.lines[line_id].account.split(" ")[0]
        record = self.rec_by_file[name]
        kind = (
            "rate"
            if name.startswith("rate_agreement")
            else "appointment"
            if name.startswith("appointment_letter")
            else "effort"
            if name.startswith("effort_report")
            else "expense"
            if name.startswith("expense_report")
            else "bill"
            if record.startswith("rec-bill")
            else None
        )
        best = None
        for prefix, doc_kind, item in DEFAULT_ITEMS:
            if account.startswith(prefix) and doc_kind == kind:
                if best is None or len(prefix) > len(best[0]):
                    best = (prefix, item)
        return best[1] if best else None

    def share(self, line_id: str, name: str, amount: int) -> dict | None:
        """A share and its cited basis, for part of a bill that a linked note explains."""
        total = next(
            int(r["fields"]["total"])
            for r in self.key["records"]
            if r["file"] == name and r["kind"] == "bill"
        )
        if abs(amount) >= abs(total):
            return None
        notes = [
            lk["file"]
            for lk in self.key["links"]
            if lk["line_id"] == line_id and "amount_cents" not in lk
        ]
        for note in notes:
            text = self.docs[note].text
            m = re.search(r"\b(\d+) of (?:the )?(\d+)\b", text)
            if not m:
                continue
            whole = int(m.group(2))
            for k in range(1, whole):
                if abs(total * k / whole - amount) <= 1:
                    i_share, _ = self.find(note, lambda r, k=k: standalone(k, r))
                    i_whole, _ = self.find(note, lambda r, whole=whole: standalone(whole, r))
                    return {
                        "share": self.cited(note, str(k), str(k), i_share),
                        "out_of": self.cited(note, str(whole), str(whole), i_whole),
                        "total": self.cited_money(name, total, TOTAL_ROW),
                    }
        return None

    def links_budgets_answers(self) -> None:
        by_line: dict[str, list[dict]] = {}
        for lk in self.key["links"]:
            by_line.setdefault(lk["line_id"], []).append(lk)
        arrival = {ln.line_id: self.g.line_arrival(ln) for ln in self.g.lines}
        for line_id, links in by_line.items():
            written: list[tuple[datetime, str, str]] = []
            for n, lk in enumerate(links):
                name = lk["file"]
                at = max(arrival[line_id], self.g.file_arrival(name))
                data: dict = {
                    "kind": "link",
                    "record_id": self.rec_by_file[name],
                    "charge_id": self.charge_id(line_id),
                }
                if "amount_cents" in lk:
                    data["amount_cents"] = lk["amount_cents"]
                data["part"] = self.part_by_file[name]
                item = self.default_item(line_id, name)
                if item:
                    data["default_item"] = item
                data["reason"] = f"The ledger line {line_id} and {name} name the same cost."
                if "amount_cents" in lk:
                    share = self.share(line_id, name, lk["amount_cents"])
                    if share:
                        data["share"] = share
                rec_id = self.add(f"rec-link-{line_id}-{n}", at, data)
                written.append((at, rec_id, name))
            # An Allowable answer each time something new is linked, replacing the last.
            answer = next(
                (
                    a
                    for a in self.key["answers"]
                    if a["line_id"] == line_id and a["question"] == "allowable"
                ),
                None,
            )
            if answer is None:
                continue
            previous = None
            for k, at in enumerate(sorted({w[0] for w in written})):
                linked = [w for w in written if w[0] <= at]
                data = {
                    "kind": "judgment",
                    "charge_id": self.charge_id(line_id),
                    "question": "allowable",
                    "text": ALLOWABLE,
                    "answer": answer["answer"],
                    "reasoning": "The evidence shows a cost for this project's work, at an "
                    "ordinary price.",
                    "quotes": [self.part_by_file[w[2]] for w in linked],
                    "rests_on": [w[1] for w in linked],
                }
                rule = self.g.agent_extras.get("rules", {}).get(line_id)
                if rule:
                    data["rule"] = rule
                    data["reasoning"] = f"The evidence shows a cost that rule {rule} doesn't allow."
                previous = self.add(f"rec-allowable-{line_id}-{k}", at, data, previous)
        for b in self.key["budget_lines"]:
            line_id = b["line_id"]
            self.add(
                f"rec-budget-{line_id}",
                arrival[line_id],
                {
                    "kind": "budget_assignment",
                    "charge_id": self.charge_id(line_id),
                    "record_id": self.budget_rec[b["budget_line"]],
                    "reason": f"The charge is for {b['budget_line']}.",
                },
            )

    def suggestions(self) -> None:
        extras = self.g.agent_extras
        for n, (bill, note, other) in enumerate(extras.get("remainders", [])):
            other_award = self.cited_text(note, other)
            self.add(
                f"rec-remainder-{n}",
                max(self.g.file_arrival(bill), self.g.file_arrival(note)),
                {
                    "kind": "remainder",
                    "record_id": self.rec_by_file[bill],
                    "other_award": other_award,
                    "reason": f"The rest of the bill is for {other}, as the email says.",
                    "quotes": [other_award["citation"]],
                },
            )
        for n, (copy, original) in enumerate(extras.get("duplicates", [])):
            self.add(
                f"rec-duplicate-{n}",
                max(self.g.file_arrival(copy), self.g.file_arrival(original)),
                {
                    "kind": "duplicate",
                    "copy_file_id": self.file_id(copy),
                    "original_file_id": self.file_id(original),
                    "reason": "The same invoice number, date, items and total.",
                },
            )


# Within one moment a run writes what's pointed to first: terms, then facts, then
# links and assignments, then answers and suggestions (the order a run writes them).
KIND_ORDER = {
    "period_of_performance": 0,
    "notice": 0,
    "budget_line": 0,
    "person": 0,
    "approval_rule": 0,
    "rate": 0,
    "bill": 1,
    "note": 1,
    "approval": 1,
    "link": 2,
    "budget_assignment": 3,
    "judgment": 4,
    "remainder": 5,
    "duplicate": 5,
}


def build(g: Grant, key: dict) -> dict:
    b = Builder(g, key)
    b.terms_and_facts()
    b.links_budgets_answers()
    b.suggestions()
    records = sorted(
        b.records, key=lambda r: (r["written_at"], KIND_ORDER[r["data"]["kind"]], r["id"])
    )
    return {
        "sample": g.slug,
        "ids": {
            "workspace": WORKSPACE,
            "grant": b.grant_id,
            "file": "file-<file name>",
            "charge": "chg-<ledger line ID>",
        },
        "records": records,
    }
