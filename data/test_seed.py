"""Checks the demo seed and the from-scratch seed pack.

- The files on disk are exactly what data/generator/build.py makes (photos
  aside, which depend on the machine's fonts), so nobody edits one by hand.
- Each ledger follows docs/contracts.md section 13, each answer key section 14,
  and each arrival schedule the eval cases' format with decision 0023's rule
  for when a ledger line arrives.
- Every value a key expects is written in its file. PDFs are read back from
  their text, and photos from the words the generator drew on them.
- The synthetic-data rule (CLAUDE.md): award numbers start with SYN-, email
  addresses are at .example, and nothing has an em dash or an en dash.
- What decision 0024 asks of the seed: an opening date, a grant near the end
  of its period, arrivals after the opening date, a cost two grants share,
  every charge with an expected bucket or listed as left out, and a pack with
  an award letter, a ledger, emails, invoices, a photo and later lines.

Uses only the standard library, and borrows the eval cases' checks from
eval/test_cases.py. Run it with `python3 data/test_seed.py`, or with pytest.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parent
DEMO = DATA / "demo"
SCRATCH = DATA / "from-scratch"
GENERATOR = DATA / "generator"

_spec = importlib.util.spec_from_file_location(
    "eval_case_checks", DATA.parent / "eval" / "test_cases.py"
)
assert _spec and _spec.loader
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

META_FILES = {"answer_key.json", "arrivals.json", "README.md"}
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png"}
# The contract code names the sixth sub-line of Other Direct Costs
# other_direct_costs_other (issue 14); eval/test_cases.py still says "other".
CATEGORIES = (ev.CATEGORIES - {"other"}) | {"other_direct_costs_other"}
ODC_SUBLINES = (ev.ODC_SUBLINE_CATEGORIES - {"other"}) | {"other_direct_costs_other"}
MAX_FILE_BYTES = 200_000
# Each account group's NSF categories, by account code prefix, longest prefix
# first. This is the test's own copy: domain.md's starting groups, with the
# categories from the account groups table proposed in pull request 30. Replace
# it with that table once it's on main.
ACCOUNT_CATEGORIES: tuple[tuple[str, frozenset[str]], ...] = tuple(
    sorted(
        [
            ("50", frozenset({"senior_personnel", "other_personnel"})),
            ("51", frozenset({"senior_personnel", "other_personnel"})),
            ("53", frozenset({"fringe_benefits"})),
            ("538", frozenset({"fringe_benefits", "other_direct_costs_other"})),
            ("5742", frozenset({"fringe_benefits", "other_direct_costs_other"})),
            ("5721", frozenset({"travel"})),
            ("5722", frozenset({"travel"})),
            *((p, frozenset({"materials_and_supplies"})) for p in ("550", "551", "552", "553")),
            ("541", frozenset({"equipment"})),
            ("542", frozenset({"equipment"})),
            ("5671", frozenset({"participant_support"})),
            ("5672", frozenset({"other_direct_costs"})),
            ("564", frozenset({"other_direct_costs"})),
            ("590", frozenset({"other_direct_costs"})),
            ("59005", frozenset({"materials_and_supplies"})),
            ("59006", frozenset({"materials_and_supplies"})),
            ("59007", frozenset({"participant_support"})),
            ("59008", frozenset({"travel"})),
            ("59012", frozenset({"equipment"})),
            ("59013", frozenset({"equipment"})),
            *((f"578{d}", frozenset({"subawards"})) for d in "123456789"),
            ("925", frozenset({"subawards"})),
        ],
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)
# Section 1's fields, plus `scope` on an approval rule (the contract change in
# issue 39): `every_charge`, or `moved_out` for a rule about moving money out of
# participant support. It's the agent's reading of the rule, not a value quoted
# from the letter.
RECORD_FIELDS = {
    **ev.RECORD_FIELDS,
    "approval_rule": ev.RECORD_FIELDS["approval_rule"] | {"scope"},
}
UNCITED_FIELDS = ev.UNCITED_FIELDS | {"scope"}
APPROVAL_SCOPES = {"every_charge", "moved_out"}
# The photos depend on the machine's fonts, so the generator's bytes can't be
# compared. Their hashes catch a photo swapped or edited by hand. After
# redrawing them on purpose, update these.
PHOTO_SHA256 = {
    "demo/coastal-microbial-genomics/taxi_receipt_ocean_sciences_2026.jpg": (
        "3210e49710071f2bfb82d3bf6a528c731ecc62a6f55baf2d6fac80c98217f310"
    ),
    "from-scratch/pack/hardware_receipt.jpg": (
        "384fbd3a259b36408c6e5ec0004ec178359e4be02ac8e90d0f5cfe659e953827"
    ),
}
TJ = re.compile(rb"\(((?:\\.|[^\\)])*)\)\s*Tj")


# ---------------------------------------------------------------- reading files


def pdf_text(data: bytes) -> str:
    """The text of a PDF the generator wrote: one Tj string per line."""
    assert data.startswith(b"%PDF-"), "not a PDF"
    lines = []
    for raw in TJ.findall(data):
        lines.append(re.sub(rb"\\(.)", rb"\1", raw).decode("latin-1"))
    return "\n".join(lines)


def generated() -> dict[Path, object]:
    """Runs the generator in memory: each folder's Grant, by the folder it writes."""
    sys.path.insert(0, str(GENERATOR))
    try:
        import demo
        import scratch
    finally:
        sys.path.pop(0)
    grants, left_out = demo.build()
    out: dict[Path, object] = {DEMO / g.slug: g for g in grants}
    out[SCRATCH] = scratch.build()
    out["left_out"] = left_out  # type: ignore[index]
    out["opening"] = demo.OPENING  # type: ignore[index]
    return out


_GENERATED: dict | None = None


def gen() -> dict:
    global _GENERATED
    if _GENERATED is None:
        _GENERATED = generated()
    return _GENERATED


def folders() -> list[tuple[Path, Path]]:
    """(where the key is, where the files are) for each grant and the pack."""
    out = [(p, p) for p in sorted(DEMO.iterdir()) if p.is_dir()]
    out.append((SCRATCH, SCRATCH / "pack"))
    return out


def texts(files: Path, grant) -> dict[str, str]:
    """What a reader sees in each evidence file, read back from disk."""
    photo_text = {d.name: d.text for d in grant.docs}
    out = {}
    for p in sorted(files.iterdir()):
        if not p.is_file() or p.name in META_FILES:
            continue
        data = p.read_bytes()
        if p.suffix == ".pdf":
            out[p.name] = pdf_text(data)
        elif p.suffix in PHOTO_SUFFIXES:
            out[p.name] = photo_text.get(p.name, "")
        else:
            out[p.name] = data.decode("utf-8")
    return out


# ---------------------------------------------------------------- checks


def check_generated(key_dir: Path, files: Path, grant, problems: list[str]) -> None:
    expected = {d.name: d.data for d in grant.docs}
    expected["ledger.csv"] = grant.ledger_csv().encode()
    on_disk = {p.name for p in files.iterdir() if p.is_file() and p.name not in META_FILES}
    for name in sorted(on_disk - set(expected)):
        problems.append(f"{name}: on disk but the generator doesn't make it")
    for name, data in expected.items():
        path = files / name
        if not path.is_file():
            problems.append(f"{name}: the generator makes it but it isn't on disk")
        elif Path(name).suffix in PHOTO_SUFFIXES:
            rel = path.relative_to(DATA).as_posix()
            if hashlib.sha256(path.read_bytes()).hexdigest() != PHOTO_SHA256.get(rel):
                problems.append(f"{rel}: isn't the photo the test knows (PHOTO_SHA256)")
        elif path.read_bytes() != data:
            problems.append(f"{name}: differs from the generator's output; run build.py")
    for fname, made in (
        ("answer_key.json", grant.key_json()),
        ("arrivals.json", grant.arrivals_json()),
    ):
        path = key_dir / fname
        if not path.is_file():
            problems.append(f"{fname} is missing")
        elif path.read_text(encoding="utf-8") != made:
            problems.append(f"{fname}: differs from the generator's output; run build.py")


def check_ledger(files: Path, problems: list[str]) -> dict[str, dict[str, str]]:
    path = files / "ledger.csv"
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = set(reader.fieldnames or [])
        rows = list(reader)
    if missing := ev.LEDGER_REQUIRED - header:
        problems.append(f"ledger.csv: missing columns {sorted(missing)}")
    if unknown := header - ev.LEDGER_REQUIRED - ev.LEDGER_OPTIONAL:
        problems.append(f"ledger.csv: unknown columns {sorted(unknown)}")
    lines: dict[str, dict[str, str]] = {}
    for n, row in enumerate(rows, start=2):
        where = f"ledger.csv row {n}"
        line_id = row["line_id"]
        if line_id in lines:
            problems.append(f"{where}: line_id {line_id} twice")
        for col in ev.LEDGER_REQUIRED:
            if not (row.get(col) or "").strip():
                problems.append(f"{where}: {col} is empty")
        t, p = date.fromisoformat(row["transaction_date"]), date.fromisoformat(row["posting_date"])
        if p < t:
            problems.append(f"{where}: posted before its transaction date")
        if not ev.DOLLARS.match(row["amount"]):
            problems.append(f"{where}: amount {row['amount']!r} isn't dollars and cents")
        code = row["account"].split(" ")[0]
        if not (re.fullmatch(r"5\d{4}", code) and code.startswith(ev.ACCOUNT_GROUP_PREFIXES)):
            problems.append(f"{where}: account {row['account']!r} isn't in domain.md's groups")
        lines[line_id] = row
    return lines


def check_arrivals(
    key_dir: Path, files: Path, lines: dict, ledger_upload: datetime | None, problems: list[str]
) -> dict[str, datetime]:
    sched = json.loads((key_dir / "arrivals.json").read_text(encoding="utf-8"))
    out: dict[str, datetime] = {}
    if set(sched) != {"case", "events"}:
        problems.append("arrivals.json: must have exactly case and events")
        return out
    documents = {p.name for p in files.iterdir() if p.is_file() and p.name not in META_FILES}
    documents.discard("ledger.csv")
    seen_files: dict[str, int] = {}
    seen_lines: dict[str, int] = {}
    last = None
    for i, e in enumerate(sched["events"]):
        where = f"arrivals.json events[{i}]"
        if not ev.ISO_TIME.match(str(e.get("at"))):
            problems.append(f"{where}: bad at")
            continue
        t = ev.parse_time(e["at"])
        if last and t < last:
            problems.append(f"{where}: events must be in time order")
        last = t
        kind = e.get("kind")
        if kind == "file":
            allowed = {"at", "kind", "file", "source", "sender", "note"}
            name = e.get("file")
            if name not in documents:
                problems.append(f"{where}: {name!r} isn't a document")
            seen_files[name] = seen_files.get(name, 0) + 1
            out[f"file:{name}"] = t
            if e.get("source") not in ev.SOURCES:
                problems.append(f"{where}: bad source")
            if e.get("source") == "gmail":
                if not str(e.get("sender", "")).endswith(".example"):
                    problems.append(f"{where}: a gmail arrival needs a .example sender")
            elif "sender" in e:
                problems.append(f"{where}: only a gmail arrival has a sender")
        elif kind == "ledger_line":
            allowed = {"at", "kind", "line_id", "note"}
            lid = e.get("line_id")
            seen_lines[lid] = seen_lines.get(lid, 0) + 1
            out[f"line:{lid}"] = t
            if lid not in lines:
                problems.append(f"{where}: {lid!r} isn't in ledger.csv")
                continue
            # Decision 0023: 00:00 UTC on its posting date if that's still ahead
            # of "now", and otherwise now. A seeded line arrives on its posting date.
            posting = ev.parse_time(f"{lines[lid]['posting_date']}T00:00:00Z")
            want = max(posting, ledger_upload) if ledger_upload else posting
            if t != want:
                problems.append(f"{where}: {lid} should arrive at {want:%Y-%m-%dT%H:%M:%SZ}")
        elif kind == "accountant":
            allowed = {"at", "kind", "action", "file", "note"}
            if e.get("action") not in ev.ACCOUNTANT_ACTIONS:
                problems.append(f"{where}: bad action")
            arrived = out.get(f"file:{e.get('file')}")
            if arrived is None or arrived >= t:
                problems.append(f"{where}: the accountant acts on a file that has arrived")
            out[f"{e.get('action')}:{e.get('file')}"] = t
        else:
            problems.append(f"{where}: bad kind {kind!r}")
            continue
        if extra := set(e) - allowed:
            problems.append(f"{where}: unknown fields {sorted(extra)}")
    for name in sorted(documents):
        if seen_files.get(name) != 1:
            problems.append(f"arrivals.json: {name} must arrive exactly once")
    for lid in sorted(lines):
        if seen_lines.get(lid) != 1:
            problems.append(f"arrivals.json: {lid} must arrive exactly once")
    return out


def check_record(rec: dict, i: int, text: dict[str, str], problems: list[str]) -> None:
    where = f"answer_key.json records[{i}]"
    if set(rec) != {"kind", "file", "fields"}:
        problems.append(f"{where}: must have exactly kind, file and fields")
        return
    kind, name, fields = rec["kind"], rec["file"], rec["fields"]
    if kind not in RECORD_FIELDS:
        problems.append(f"{where}: {kind!r} isn't a record kind read from a document")
        return
    if name not in text:
        problems.append(f"{where}: {name!r} isn't an evidence file")
        return
    body = ev.normalize(text[name])
    for field, value in fields.items():
        ftype = ev.field_type(field)
        if ftype not in RECORD_FIELDS[kind]:
            problems.append(f"{where}: {kind} has no field {field!r}")
        elif ftype == "category":
            if value not in CATEGORIES:
                problems.append(f"{where}: category {value!r} isn't one of {sorted(CATEGORIES)}")
        elif ftype in ev.DATE_FIELDS:
            d = date.fromisoformat(value)
            if not any(ev.normalize(r) in body for r in ev.date_renderings(d)):
                problems.append(f"{where}: {field} {value} isn't written in {name}")
        elif ftype in ev.MONEY_FIELDS:
            if not ev.CENTS.match(value) or not ev.money_written(int(value), body):
                problems.append(f"{where}: {field} {value} cents isn't written in {name}")
        elif ftype == "scope":
            if value not in APPROVAL_SCOPES:
                problems.append(f"{where}: scope must be one of {sorted(APPROVAL_SCOPES)}")
        elif ftype not in UNCITED_FIELDS and ev.normalize(value) not in body:
            problems.append(f"{where}: {field} {value!r} doesn't appear in {name}")
    if kind in ev.TERM_KINDS and "dated" not in fields:
        problems.append(f"{where}: a term should give its dated")


def check_key(
    key_dir: Path,
    lines: dict,
    arrivals: dict[str, datetime],
    text: dict[str, str],
    award_number: str,
    problems: list[str],
) -> None:
    key = json.loads((key_dir / "answer_key.json").read_text(encoding="utf-8"))
    check_key_data(key, lines, arrivals, text, award_number, problems)
    check_invariants(key, lines, arrivals, text, problems)


def check_key_data(
    key: dict,
    lines: dict,
    arrivals: dict[str, datetime],
    text: dict[str, str],
    award_number: str,
    problems: list[str],
) -> None:
    if set(key) != ev.KEY_FIELDS:
        problems.append(f"answer_key.json: fields must be exactly {sorted(ev.KEY_FIELDS)}")
        return
    if key["award_number"] != award_number or not award_number.startswith("SYN-"):
        problems.append("answer_key.json: award_number must be the grant's, starting SYN-")
    letters = [n for n in text if n.startswith("award_letter.")]
    if len(letters) != 1 or award_number not in text[letters[0]]:
        problems.append("the grant needs one award letter carrying its award number")
    kinds_by_file: dict[str, set[str]] = {}
    totals: dict[str, int] = {}
    budget_names: set[str] = set()
    categories: dict[str, str] = {}
    for i, rec in enumerate(key["records"]):
        check_record(rec, i, text, problems)
        kinds_by_file.setdefault(rec["file"], set()).add(rec["kind"])
        f = rec["fields"]
        if rec["kind"] == "bill":
            totals[rec["file"]] = int(f["total"])
        if rec["kind"] == "budget_line":
            budget_names.add(f["name"])
            categories[f["name"]] = f["category"]
    if letters:
        for name, parent in ev.budget_parents(text[letters[0]]).items():
            pc, c = categories.get(parent), categories.get(name)
            if pc == "other_direct_costs":
                if c not in ODC_SUBLINES:
                    problems.append(f"budget line {name!r} needs an Other Direct Costs sub-line")
            elif c != pc:
                problems.append(f"budget line {name!r} has {c!r}, its line {parent!r} has {pc!r}")

    linked: set[str] = set()
    files_by_line: dict[str, set[str]] = {}
    used: dict[str, int] = {}
    seen = set()
    for i, link in enumerate(key["links"]):
        where = f"answer_key.json links[{i}]"
        name, lid = link["file"], link["line_id"]
        if not {"file", "line_id"} <= set(link) <= {"file", "line_id", "amount_cents"}:
            problems.append(f"{where}: bad fields")
        if name not in kinds_by_file:
            problems.append(f"{where}: no expected record is read from {name!r}")
        if lid not in lines:
            problems.append(f"{where}: {lid!r} isn't in ledger.csv")
            continue
        if (name, lid) in seen:
            problems.append(f"{where}: the same link twice")
        seen.add((name, lid))
        linked.add(lid)
        files_by_line.setdefault(lid, set()).add(name)
        is_bill = "bill" in kinds_by_file.get(name, set())
        amount = link.get("amount_cents")
        if is_bill != isinstance(amount, int):
            problems.append(f"{where}: a link carries an amount exactly when it's to a bill")
        if is_bill and isinstance(amount, int):
            used[name] = used.get(name, 0) + amount
            if abs(amount) > abs(ev.cents_of(lines[lid])):
                problems.append(f"{where}: links more than the charge")
    for name, total in used.items():
        if name in totals and abs(total) > abs(totals[name]):
            problems.append(f"answer_key.json: links to {name} add up to more than its total")
    # The bills linked to a charge add up to it, except where the key says a
    # charge rests on part of a shared bill (it links the charge's amount).
    for lid in files_by_line:
        bills = sum(
            link["amount_cents"]
            for link in key["links"]
            if link["line_id"] == lid and "amount_cents" in link
        )
        if bills and bills != ev.cents_of(lines[lid]):
            problems.append(f"answer_key.json: bills linked to {lid} don't add up to it")

    assigned = set()
    for item in key["budget_lines"]:
        if item["line_id"] in assigned:
            problems.append(f"budget_lines: {item['line_id']} assigned twice")
        assigned.add(item["line_id"])
        if item["budget_line"] not in budget_names:
            problems.append(f"budget_lines: {item['budget_line']!r} isn't a budget line")
        if item["line_id"] not in lines:
            problems.append(f"budget_lines: {item['line_id']!r} isn't in ledger.csv")
    for ans in key["answers"]:
        if ans["question"] not in ev.QUESTIONS or ans["answer"] not in ev.ANSWERS:
            problems.append(f"answers: bad question or answer {ans}")
        if ans["question"] == "allowable" and ans["line_id"] not in linked:
            problems.append(f"answers: Allowable is only asked for {ans['line_id']} with evidence")

    confirmed = [t for k, t in arrivals.items() if k.startswith("confirm_terms:")]
    for item in key["buckets"]:
        where = f"buckets {item['line_id']} at {item['at']}"
        if item["bucket"] not in ev.BUCKETS:
            problems.append(f"{where}: bad bucket")
        t = ev.parse_time(item["at"])
        arrived = arrivals.get(f"line:{item['line_id']}")
        if arrived is None or t <= arrived:
            problems.append(f"{where}: must come after the line arrives")
        if not confirmed or t <= min(confirmed):
            problems.append(f"{where}: must come after the terms are confirmed")
        if item["bucket"] == "evidence_complete":
            for name in files_by_line.get(item["line_id"], set()):
                if t <= arrivals.get(f"file:{name}", t):
                    problems.append(f"{where}: complete before {name} arrives")


def check_synthetic(files: Path, text: dict[str, str], problems: list[str]) -> None:
    for p in sorted(files.iterdir()):
        if p.is_file() and p.stat().st_size > MAX_FILE_BYTES:
            problems.append(f"{p.name}: {p.stat().st_size} bytes, keep files small")
        if p.suffix in PHOTO_SUFFIXES and not p.read_bytes().startswith(b"\xff\xd8"):
            problems.append(f"{p.name}: isn't a JPEG")
    everything = dict(text)
    everything["ledger.csv"] = (files / "ledger.csv").read_text(encoding="utf-8")
    for name, body in everything.items():
        for address in ev.EMAIL.findall(body):
            if not address.lower().endswith(".example"):
                problems.append(f"{name}: email address {address} isn't at .example")
        for award in re.findall(r"\b[A-Z]{0,4}-?\d{7}\b", body):
            if not award.startswith("SYN-"):
                problems.append(f"{name}: {award} looks like an award number without SYN-")
        if "\N{EM DASH}" in body or "\N{EN DASH}" in body:
            problems.append(f"{name}: has an em dash or an en dash")
    for name in text:
        if name.startswith("award_letter."):
            pos = [text[name].find(s) for s in ev.AWARD_LETTER_SECTIONS]
            if -1 in pos or pos != sorted(pos):
                problems.append(f"{name}: needs the award notice's sections in order")


# ---------------------------------------------------------------- the rules behind the buckets

SHARE = re.compile(r"\b(\d+) of (?:the )?(\d+)\b")
AWARD = re.compile(r"syn-\d{7}")


def period_in_force(key: dict, arrivals: dict[str, datetime], when: datetime):
    """The period from the terms confirmed by `when`, the latest dated winning."""
    start = end = None
    start_dated = end_dated = ""
    for rec in key["records"]:
        if rec["kind"] != "period_of_performance":
            continue
        confirmed = arrivals.get(f"confirm_terms:{rec['file']}")
        if confirmed is None or confirmed > when:
            continue
        f = rec["fields"]
        if "start" in f and f["dated"] >= start_dated:
            start, start_dated = date.fromisoformat(f["start"]), f["dated"]
        if "end" in f and f["dated"] >= end_dated:
            end, end_dated = date.fromisoformat(f["end"]), f["dated"]
    return start, end


def share_of(note: str, award_number: str) -> tuple[int, int] | None:
    """This award's share in a note like "56 of the 96 samples ... for SYN-1".

    The share's denominator is the M of the first "N of M". This award's count
    is the last whole number below M written before its award number and after
    the award number mentioned before it.
    """
    body = ev.normalize(note)
    first = SHARE.search(body)
    if not first:
        return None
    whole = int(first.group(2))
    prev = 0
    for m in AWARD.finditer(body):
        if m.group(0) == award_number.casefold():
            tokens = [t.strip(",.;:") for t in body[prev : m.start()].split()]
            counts = [int(t) for t in tokens if t.isdigit() and 0 < int(t) < whole]
            return (counts[-1], whole) if counts else None
        prev = m.end()
    return None


def account_categories(account: str) -> frozenset[str] | None:
    """The NSF categories of a ledger account's group, or None outside every group."""
    code = account.split(" ")[0]
    for prefix, categories in ACCOUNT_CATEGORIES:
        if code.startswith(prefix):
            return categories
    return None


def categories_agree(account: frozenset[str], line: str) -> bool:
    """The two-way rule: the same category, or one contains the other.

    Other Direct Costs contains its six sub-lines, the only categories that sit
    inside another.
    """
    return any(
        c == line
        or (c == "other_direct_costs" and line in ODC_SUBLINES)
        or (line == "other_direct_costs" and c in ODC_SUBLINES)
        for c in account
    )


def check_invariants(
    key: dict,
    lines: dict,
    arrivals: dict[str, datetime],
    text: dict[str, str],
    problems: list[str],
) -> None:
    """The rules a key's buckets and links have to follow, whatever the generator says.

    - Nothing is Evidence complete while its cost date is outside the period in
      force, counting only confirmed terms, or with an answer of contradicts or
      unsure, or with nothing linked.
    - A link for part of a bill rests on a basis (decision 0021): an item on the
      bill with the same amount, a note linked to the same charge, or other
      charges on this grant that take the rest of the bill.
    - Where the note gives a share, "N of M", the link is the bill's total times
      N over M, to within one cent.
    - Nothing is Evidence complete when its ledger account's categories and its
      budget line's category disagree under the two-way rule.
    """
    kinds: dict[str, set[str]] = {}
    totals: dict[str, int] = {}
    items: dict[str, set[int]] = {}
    for rec in key["records"]:
        kinds.setdefault(rec["file"], set()).add(rec["kind"])
        if rec["kind"] == "bill":
            totals[rec["file"]] = int(rec["fields"]["total"])
            items[rec["file"]] = {
                int(v) for k, v in rec["fields"].items() if k.endswith("].amount")
            }
    links_by_line: dict[str, list[dict]] = {}
    used: dict[str, int] = {}
    for link in key["links"]:
        links_by_line.setdefault(link["line_id"], []).append(link)
        if "amount_cents" in link:
            used[link["file"]] = used.get(link["file"], 0) + link["amount_cents"]
    award = key["award_number"]

    unbased: set[str] = set()
    for lid, links in links_by_line.items():
        notes = [x["file"] for x in links if "note" in kinds.get(x["file"], set())]
        for link in links:
            name, amount = link["file"], link.get("amount_cents")
            if amount is None or name not in totals or abs(amount) >= abs(totals[name]):
                continue
            if amount in items[name] or used[name] == totals[name]:
                continue
            if not notes:
                unbased.add(lid)
                continue
            for note in notes:
                share = share_of(text.get(note, ""), award)
                if share is None:
                    continue
                want = totals[name] * share[0] / share[1]
                if abs(amount - want) > 1:
                    problems.append(
                        f"links {lid}: {amount} cents isn't {share[0]} of {share[1]} of "
                        f"{name}'s {totals[name]} cents ({want:.2f})"
                    )

    line_category = {
        rec["fields"]["name"]: rec["fields"]["category"]
        for rec in key["records"]
        if rec["kind"] == "budget_line"
    }
    assigned = {b["line_id"]: b["budget_line"] for b in key["budget_lines"]}
    doubtful = {a["line_id"] for a in key["answers"] if a["answer"] != "supports"}
    for item in key["buckets"]:
        if item["bucket"] != "evidence_complete":
            continue
        lid, when = item["line_id"], ev.parse_time(item["at"])
        where = f"buckets {lid} at {item['at']}"
        cost = date.fromisoformat(lines[lid]["transaction_date"])
        start, end = period_in_force(key, arrivals, when)
        if start is None or end is None or not start <= cost <= end:
            problems.append(f"{where}: complete, but {cost} is outside the period in force")
        if lid in doubtful:
            problems.append(f"{where}: complete, but an answer isn't supports")
        if not links_by_line.get(lid):
            problems.append(f"{where}: complete with nothing linked")
        if lid in unbased:
            problems.append(f"{where}: complete on part of a bill with no basis (0021)")
        account = account_categories(lines[lid]["account"])
        category = line_category.get(assigned.get(lid, ""))
        if account and category and not categories_agree(account, category):
            problems.append(
                f"{where}: complete, but account {lines[lid]['account']!r} and budget line "
                f"{assigned[lid]!r} disagree"
            )


def folder_inputs(key_dir: Path, files: Path, grant, ledger_upload, problems: list[str]):
    text = texts(files, grant)
    lines = check_ledger(files, problems)
    arrivals = check_arrivals(key_dir, files, lines, ledger_upload, problems)
    return lines, arrivals, text


def check_folder(key_dir: Path, files: Path, grant, ledger_upload: datetime | None) -> list[str]:
    problems: list[str] = []
    check_generated(key_dir, files, grant, problems)
    text = texts(files, grant)
    for d in grant.docs:
        if d.name.endswith(".pdf") and d.name in text and text[d.name] != d.text.rstrip("\n"):
            problems.append(f"{d.name}: its PDF text doesn't read back as written")
    lines = check_ledger(files, problems)
    arrivals = check_arrivals(key_dir, files, lines, ledger_upload, problems)
    check_key(key_dir, lines, arrivals, text, grant.award_number, problems)
    check_synthetic(files, text, problems)
    return [f"{key_dir.name}: {p}" for p in problems]


# ---------------------------------------------------------------- tests


def test_files_and_keys() -> None:
    g = gen()
    pack = json.loads((SCRATCH / "pack.json").read_text(encoding="utf-8"))
    problems = []
    for key_dir, files in folders():
        upload = ev.parse_time(pack["ledger_uploaded_at"]) if key_dir == SCRATCH else None
        problems += check_folder(key_dir, files, g[key_dir], upload)
    assert not problems, "\n".join(problems)


def test_invariants_catch_false_clears() -> None:
    """The edits a reviewer tried, each of which the byte check alone missed.

    The last one marks the reagents filed on participant support (L-7264-0039)
    complete, though their account and their budget line disagree.
    """
    g = gen()

    def run(folder: str, edit) -> list[str]:
        key_dir = DEMO / folder
        problems: list[str] = []
        lines, arrivals, text = folder_inputs(key_dir, key_dir, g[key_dir], None, problems)
        key = json.loads((key_dir / "answer_key.json").read_text(encoding="utf-8"))
        ref = {lid: row["reference"] for lid, row in lines.items()}
        edit(key, ref)
        check_invariants(key, lines, arrivals, text, problems)
        return problems

    def complete(reference: str, before: str | None = None):
        def edit(key, ref):
            for b in key["buckets"]:
                if ref[b["line_id"]] == reference and (before is None or b["at"] < before):
                    b["bucket"] = "evidence_complete"

        return edit

    def relink(key, ref):
        for link in key["links"]:
            if ref[link["line_id"]] == "EGS-20931" and "amount_cents" in link:
                link["amount_cents"] = 590000

    for folder in ("salt-marsh-carbon", "coastal-microbial-genomics", "river-delta-sediment"):
        assert not run(folder, lambda key, ref: None), folder
    assert run("salt-marsh-carbon", complete("ECX-7702")), "S3c marked complete"
    assert run("river-delta-sediment", complete("EMS-2609-14", "2026-11-23")), "S2 early"
    assert run("coastal-microbial-genomics", complete("REG-2026-0457")), "S1 marked complete"
    assert run("salt-marsh-carbon", relink), "S3a linked for $5,900"
    assert run("coastal-microbial-genomics", complete("ESS-29944")), "reagents marked complete"


def test_seed_story() -> None:
    """What decision 0024 asks of the demo seed."""
    g = gen()
    seed = json.loads((DEMO / "seed.json").read_text(encoding="utf-8"))
    opening = ev.parse_time(seed["opening_at"])
    assert opening == g["opening"]
    grants = [g[DEMO / s["folder"]] for s in seed["grants"]]
    assert len(grants) >= 2
    # One grant near the end of its period: inside its 90-day closeout window.
    assert any(
        timedelta(0)
        < datetime.combine(x.end, datetime.min.time(), opening.tzinfo) - opening
        <= timedelta(days=90)
        for x in grants
    )
    # More arrivals after the opening date, for the clock to release.
    for x in grants:
        assert any(d.at > opening for d in x.docs) or any(
            x.line_arrival(ln) > opening for ln in x.lines
        ), f"{x.slug} has nothing arriving after the opening date"
    # At least two grants share a cost: the same bill, on each grant's own copy.
    by_hash: dict[str, set[str]] = {}
    for x in grants:
        for d in x.docs:
            if d.name.startswith("invoice_"):
                by_hash.setdefault(hashlib.sha256(d.data).hexdigest(), set()).add(x.slug)
    assert any(len(v) >= 2 for v in by_hash.values()), "no cost is shared by two grants"
    # Ledger line IDs are unique in the workspace (contracts.md section 6).
    ids = [ln.line_id for x in grants for ln in x.lines]
    assert len(ids) == len(set(ids))
    # Every charge has an expected bucket, or is listed as left out.
    for s, x in zip(seed["grants"], grants, strict=True):
        key = json.loads((DEMO / s["folder"] / "answer_key.json").read_text(encoding="utf-8"))
        with_bucket = {b["line_id"] for b in key["buckets"]}
        left_out = set(s["lines_without_buckets"])
        for ln in x.lines:
            assert (ln.line_id in with_bucket) != (ln.line_id in left_out), ln.line_id


def test_from_scratch_pack() -> None:
    """Decision 0024: an award letter, a ledger, emails, invoices, a receipt photo."""
    g = gen()
    opening = g["opening"]
    names = [p.name for p in (SCRATCH / "pack").iterdir() if p.is_file()]
    assert sum(n.startswith("award_letter.") for n in names) == 1
    assert "ledger.csv" in names
    assert any(n.endswith(".eml") for n in names)
    assert any(n.startswith("invoice_") for n in names)
    assert any(Path(n).suffix in PHOTO_SUFFIXES for n in names)
    assert not META_FILES & set(names), "the pack holds only what the user drops in"
    with (SCRATCH / "pack" / "ledger.csv").open(encoding="utf-8") as fh:
        postings = [date.fromisoformat(r["posting_date"]) for r in csv.DictReader(fh)]
    assert any(p > opening.date() for p in postings), "no later ledger lines"


if __name__ == "__main__":
    failed = 0
    for test in (
        test_files_and_keys,
        test_invariants_catch_false_clears,
        test_seed_story,
        test_from_scratch_pack,
    ):
        try:
            test()
            print(f"ok    {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {test.__name__}\n{exc}")
    sys.exit(1 if failed else 0)
