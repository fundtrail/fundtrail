"""Checks the two sample grants and the two unused seed grants.

- The files on disk are exactly what data/generator/build.py makes (photos
  aside, which depend on the machine's fonts), so nobody edits one by hand.
- Each ledger follows docs/contracts.md section 13 and each answer key section
  14. Each timeline holds scheduled events only, and each line arrives by
  decision 0023's rule. The user actions are the script the key assumes.
- Every value a key expects is written in its file. PDFs are read back from
  their text, and photos from the words the generator drew on them.
- The synthetic-data rule (CLAUDE.md): award numbers start with SYN-, email
  addresses are at .example, and nothing has an em dash or an en dash.
- The larger sample's timeline runs from its start into its closeout window,
  and the small sample starts with its award letter and its ledger.

Uses only the standard library, and borrows the eval cases' checks from
eval/test_cases.py. Run it with `python3 data/test_seed.py`, or with pytest.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import importlib.util
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parent
SAMPLES = DATA / "samples"
DEMO = DATA / "demo"
GENERATOR = DATA / "generator"
LARGER = SAMPLES / "salt-marsh-carbon"
SMALL = SAMPLES / "nitrate-sensors"

_spec = importlib.util.spec_from_file_location(
    "eval_case_checks", DATA.parent / "eval" / "test_cases.py"
)
assert _spec and _spec.loader
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

META_FILES = {
    "answer_key.json",
    "timeline.json",
    "user_actions.json",
    "sample.json",
    "README.md",
}
TIMELINE_KINDS = {"file", "ledger", "ledger_line"}
# The accountant script (ruling 47): each action's required and optional fields,
# besides `at`, `action` and an optional `note`. References are stable (a ledger
# line ID, a file name, a record kind) and never record IDs.
ACTION_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    "confirm_terms": ({"file"}, set()),
    "deliver_file": ({"file"}, set()),
    # suggestion: the record kind suggested, such as checklist_removal, dispute,
    # duplicate or link. decision: accept or reject.
    "decide_suggestion": ({"suggestion", "decision"}, {"line_id", "file"}),
    # The accountant's answer to the agent's flag on a charge.
    "answer_flag": ({"line_id", "answer"}, set()),
    # A share and its basis typed for part of a bill (decision 0021).
    "enter_share": ({"line_id", "file", "share", "out_of", "basis"}, set()),
}
USER_ACTIONS = set(ACTION_FIELDS)
DECISIONS = {"accept", "reject"}
# SampleChoice, as issue 165 settles it. When the contract code has the enum,
# test_sample_choices_match_the_contract reads it and compares.
SAMPLE_CHOICES = ("small_live", "larger_live", "larger_prerun")
WORKSPACES_SOURCE = DATA.parent / "backend" / "app" / "contracts" / "workspaces.py"
SAMPLE_JSON_FIELDS = {
    "sample",
    "award_number",
    "starts_at",
    "last_event_at",
    "ledger_lines",
    "files",
    "options",
}
OPTION_FIELDS = {"choice", "name", "description", "placeholder"}
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png"}
CATEGORIES = ev.CATEGORIES
ODC_SUBLINES = ev.ODC_SUBLINE_CATEGORIES
MAX_FILE_BYTES = 200_000
# Each account group's NSF categories, by account code prefix, longest prefix
# first, and None for an account in no group. A copy of the table in
# backend/app/checks/account_groups.py, which imports the contract code and so
# the backend's dependencies. test_account_categories_match_the_table reads that
# file's source and fails if this copy drifts from it.
ACCOUNT_GROUPS_SOURCE = DATA.parent / "backend" / "app" / "checks" / "account_groups.py"
ACCOUNT_CATEGORIES: tuple[tuple[str, frozenset[str] | None], ...] = tuple(
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
            ("56710", None),
            ("59000", None),
        ],
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)
# Section 1's fields, plus `scope` on an approval rule (ApprovalScope, added in
# PR 61): `every_charge`, or `moved_out` for a rule about moving money out of
# its category. It's cited to the clause's words, such as "may not be
# diverted", but its value is the enum's, which the letter never writes, so
# the key's value isn't looked for in the file.
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
    "samples/nitrate-sensors/hardware_receipt.jpg": (
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


def generated() -> dict:
    """Runs the generator in memory: each folder's Grant, by the folder it writes."""
    sys.path.insert(0, str(GENERATOR))
    try:
        import build
    finally:
        sys.path.pop(0)
    samples, unused = build.built()
    out: dict = {SAMPLES / name: g for name, g in samples.items()}
    out.update({DEMO / g.slug: g for g in unused})
    out["sample_json"] = build.sample_json
    return out


_GENERATED: dict | None = None


def gen() -> dict:
    global _GENERATED
    if _GENERATED is None:
        _GENERATED = generated()
    return _GENERATED


def folders() -> list[Path]:
    """Each sample's folder, then each unused grant's."""
    return [p for root in (SAMPLES, DEMO) for p in sorted(root.iterdir()) if p.is_dir()]


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
    made_files = [
        ("answer_key.json", grant.key_json()),
        ("timeline.json", grant.timeline_json()),
        ("user_actions.json", grant.user_actions_json()),
    ]
    if key_dir.parent == SAMPLES:
        made_files.append(("sample.json", gen()["sample_json"](grant)))
    for fname, made in made_files:
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


def check_timeline(
    key_dir: Path, files: Path, lines: dict, problems: list[str]
) -> dict[str, datetime]:
    """Reads the timeline and the user actions. Returns when each line and file
    arrives in the play the key assumes, and when each user action happens."""
    timeline = json.loads((key_dir / "timeline.json").read_text(encoding="utf-8"))
    actions = json.loads((key_dir / "user_actions.json").read_text(encoding="utf-8"))
    out: dict[str, datetime] = {}
    if set(timeline) != {"sample", "starts_at", "events"}:
        problems.append("timeline.json: must have exactly sample, starts_at and events")
        return out
    if set(actions) != {"sample", "actions"}:
        problems.append("user_actions.json: must have exactly sample and actions")
        return out
    documents = {p.name for p in files.iterdir() if p.is_file() and p.name not in META_FILES}
    documents.discard("ledger.csv")
    seen_files: dict[str, int] = {}
    seen_lines: dict[str, int] = {}
    ledger_at: datetime | None = None
    last = None
    for i, e in enumerate(timeline["events"]):
        where = f"timeline.json events[{i}]"
        if not ev.ISO_TIME.match(str(e.get("at"))):
            problems.append(f"{where}: bad at")
            continue
        t = ev.parse_time(e["at"])
        if last and t < last:
            problems.append(f"{where}: events must be in time order")
        last = t
        kind = e.get("kind")
        if kind == "file":
            allowed = {"at", "kind", "file", "source", "sender", "deliver", "note"}
            name = e.get("file")
            if name not in documents:
                problems.append(f"{where}: {name!r} isn't a document")
            seen_files[name] = seen_files.get(name, 0) + 1
            # A file marked for the user arrives only when the user delivers it
            # (ruling 44); the clock never does.
            if e.get("deliver") != "user":
                out[f"file:{name}"] = t
            if e.get("source") not in ev.SOURCES:
                problems.append(f"{where}: bad source")
            if e.get("source") == "gmail":
                if not str(e.get("sender", "")).endswith(".example"):
                    problems.append(f"{where}: a gmail arrival needs a .example sender")
            elif "sender" in e:
                problems.append(f"{where}: only a gmail arrival has a sender")
            if e.get("deliver", "user") != "user":
                problems.append(f"{where}: deliver can only be user")
        elif kind == "ledger":
            allowed = {"at", "kind", "file", "note"}
            if e.get("file") != "ledger.csv" or ledger_at is not None:
                problems.append(f"{where}: one ledger event, for ledger.csv")
            ledger_at = t
        elif kind == "ledger_line":
            allowed = {"at", "kind", "line_id", "note"}
            lid = e.get("line_id")
            seen_lines[lid] = seen_lines.get(lid, 0) + 1
            out[f"line:{lid}"] = t
            if lid not in lines:
                problems.append(f"{where}: {lid!r} isn't in ledger.csv")
            elif t != ev.parse_time(f"{lines[lid]['posting_date']}T00:00:00Z"):
                problems.append(f"{where}: a seeded line arrives at 00:00 UTC on its posting date")
        else:
            problems.append(f"{where}: bad kind {kind!r}")
            continue
        if extra := set(e) - allowed:
            problems.append(f"{where}: unknown fields {sorted(extra)}")
    if ledger_at is not None:
        if seen_lines:
            problems.append("timeline.json: a ledger event and ledger_line events together")
        # Decision 0023: a line arrives at the later of the ledger's arrival and
        # 00:00 UTC on its posting date.
        for lid, row in lines.items():
            posting = ev.parse_time(f"{row['posting_date']}T00:00:00Z")
            out[f"line:{lid}"] = max(ledger_at, posting)
            seen_lines[lid] = 1
    for name in sorted(documents):
        if seen_files.get(name) != 1:
            problems.append(f"timeline.json: {name} must arrive exactly once")
    for lid in sorted(lines):
        if seen_lines.get(lid) != 1:
            problems.append(f"timeline.json: {lid} must arrive exactly once")

    for i, a in enumerate(actions["actions"]):
        where = f"user_actions.json actions[{i}]"
        if a.get("action") not in USER_ACTIONS or not ev.ISO_TIME.match(str(a.get("at"))):
            problems.append(f"{where}: needs at and an action in {sorted(USER_ACTIONS)}")
            continue
        required, optional = ACTION_FIELDS[a["action"]]
        given = set(a) - {"at", "action", "note"}
        if not required <= given or given - required - optional:
            problems.append(
                f"{where}: {a['action']} takes {sorted(required)}, and may take {sorted(optional)}"
            )
            continue
        if a["action"] == "decide_suggestion" and (
            a["decision"] not in DECISIONS or not ({"line_id", "file"} & given)
        ):
            problems.append(f"{where}: a decision is accept or reject, about a line or a file")
        if a["action"] == "answer_flag" and a["answer"] not in ev.ANSWERS:
            problems.append(f"{where}: answer must be one of {sorted(ev.ANSWERS)}")
        t = ev.parse_time(a["at"])
        out[f"{a['action']}:{a.get('line_id') or a.get('file')}"] = t
        if a["action"] == "answer_flag":
            out[f"answer_flag_value:{a['line_id']}"] = a["answer"]  # type: ignore[assignment]
        if a["action"] == "enter_share":
            out[f"enter_share_value:{a['line_id']}"] = (  # type: ignore[assignment]
                a["file"],
                int(a["share"]),
                int(a["out_of"]),
            )
        if a["action"] == "deliver_file":
            # A file marked for the user arrives when the user brings it in.
            out[f"file:{a['file']}"] = t
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


def table_from_source(path: Path) -> dict[str, frozenset[str] | None]:
    """The account table in account_groups.py, read from its source with ast.

    Each AccountGroup call gives its `accounts` and `nsf_categories`, and its
    `categories_by_account` overrides. NOT_IN_ANY_GROUP gives the accounts in no
    group. A BudgetCategory member's value is its name in lower case.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))

    def strings(node: ast.AST) -> list[str]:
        return [
            n.value
            for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]

    def categories(node: ast.AST) -> frozenset[str]:
        return frozenset(
            n.attr.lower()
            for n in ast.walk(node)
            if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id == "BudgetCategory"
        )

    table: dict[str, frozenset[str] | None] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "AccountGroup":
            kw = {k.arg: k.value for k in node.keywords}
            for prefix in strings(kw["accounts"]):
                table[prefix] = categories(kw["nsf_categories"])
            by_account = kw.get("categories_by_account")
            if by_account is not None:
                mapping = next(n for n in ast.walk(by_account) if isinstance(n, ast.Dict))
                for k, v in zip(mapping.keys, mapping.values, strict=True):
                    assert isinstance(k, ast.Constant)
                    table[k.value] = categories(v)
        if (
            isinstance(node, ast.AnnAssign)
            and getattr(node.target, "id", None) == "NOT_IN_ANY_GROUP"
        ):
            assert node.value is not None
            for code in strings(node.value):
                table[code] = None
    return table


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
            typed = arrivals.get(f"enter_share_value:{lid}")
            if typed and typed[0] == name:  # type: ignore[index]
                _, share, out_of = typed  # type: ignore[misc]
                want = totals[name] * share / out_of
                if abs(amount - want) > 1:
                    problems.append(
                        f"links {lid}: {amount} cents isn't the scripted share {share} of "
                        f"{out_of} of {name}'s {totals[name]} cents ({want:.2f})"
                    )
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
    flagged_only = {
        lid
        for lid in doubtful
        if all(
            a["question"] == "flag"
            for a in key["answers"]
            if a["line_id"] == lid and a["answer"] != "supports"
        )
    }
    for item in key["buckets"]:
        if item["bucket"] != "evidence_complete":
            continue
        lid, when = item["line_id"], ev.parse_time(item["at"])
        where = f"buckets {lid} at {item['at']}"
        cost = date.fromisoformat(lines[lid]["transaction_date"])
        start, end = period_in_force(key, arrivals, when)
        if start is None or end is None or not start <= cost <= end:
            problems.append(f"{where}: complete, but {cost} is outside the period in force")
        answered = arrivals.get(f"answer_flag:{lid}")
        cleared = (
            lid in flagged_only
            and answered is not None
            and answered < when
            and arrivals.get(f"answer_flag_value:{lid}") == "supports"
        )
        if lid in doubtful and not cleared:
            problems.append(f"{where}: complete, but an answer isn't supports")
        if not links_by_line.get(lid):
            problems.append(f"{where}: complete with nothing linked")
        shared = arrivals.get(f"enter_share:{lid}")
        if lid in unbased and (shared is None or shared >= when):
            problems.append(f"{where}: complete on part of a bill with no basis (0021)")
        account = account_categories(lines[lid]["account"])
        category = line_category.get(assigned.get(lid, ""))
        if account and category and not categories_agree(account, category):
            problems.append(
                f"{where}: complete, but account {lines[lid]['account']!r} and budget line "
                f"{assigned[lid]!r} disagree"
            )


def folder_inputs(key_dir: Path, grant, problems: list[str]):
    text = texts(key_dir, grant)
    lines = check_ledger(key_dir, problems)
    arrivals = check_timeline(key_dir, key_dir, lines, problems)
    return lines, arrivals, text


def check_folder(key_dir: Path, grant) -> list[str]:
    files = key_dir
    problems: list[str] = []
    check_generated(key_dir, files, grant, problems)
    text = texts(files, grant)
    for d in grant.docs:
        if d.name.endswith(".pdf") and d.name in text and text[d.name] != d.text.rstrip("\n"):
            problems.append(f"{d.name}: its PDF text doesn't read back as written")
    lines = check_ledger(files, problems)
    arrivals = check_timeline(key_dir, files, lines, problems)
    check_key(key_dir, lines, arrivals, text, grant.award_number, problems)
    check_synthetic(files, text, problems)
    return [f"{key_dir.name}: {p}" for p in problems]


# ---------------------------------------------------------------- tests


def test_files_and_keys() -> None:
    g = gen()
    problems = []
    for folder in folders():
        problems += check_folder(folder, g[folder])
    assert not problems, "\n".join(problems)


def test_invariants_catch_false_clears() -> None:
    """The edits a reviewer tried, each of which the byte check alone missed.

    The last one marks the reagents filed on participant support (L-7264-0039)
    complete, though their account and their budget line disagree.
    """
    g = gen()

    def run(folder: str, edit) -> list[str]:
        key_dir = SAMPLES / folder if (SAMPLES / folder).is_dir() else DEMO / folder
        problems: list[str] = []
        lines, arrivals, text = folder_inputs(key_dir, g[key_dir], problems)
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


def test_account_categories_match_the_table() -> None:
    """The test's copy of the account groups' categories is the backend's table."""
    assert dict(ACCOUNT_CATEGORIES) == table_from_source(ACCOUNT_GROUPS_SOURCE)


# ---------------------------------------------------------------- samples


def load(folder: Path, name: str) -> dict:
    return json.loads((folder / name).read_text(encoding="utf-8"))


def check_no_user_decision(folder: Path, problems: list[str]) -> None:
    """A timeline holds scheduled events only. Confirming terms, accepting a
    suggestion or delivering a file is the user's, never a scheduled event."""
    for i, e in enumerate(load(folder, "timeline.json")["events"]):
        if e.get("kind") not in TIMELINE_KINDS or "action" in e:
            problems.append(f"{folder.name}: timeline event {i} is a user decision, not a schedule")


def check_user_actions(folder: Path, problems: list[str]) -> None:
    """Each user action is possible at its time.

    - confirm_terms: the file has arrived on the timeline, or the user brought
      it in, before the action.
    - deliver_file: the file is marked for the user, and the user brings it in
      on or after its date (ruling 44: the clock never delivers it).
    - Any action about a ledger line comes after the line arrives, and any
      action about a file after the file arrives.
    - answer_flag answers a flag the key expects on that line; enter_share is
      for a part of a bill the key links to that line.
    """
    events = load(folder, "timeline.json")["events"]
    scheduled = {e["file"]: e for e in events if e.get("kind") == "file"}
    actions = load(folder, "user_actions.json")["actions"]
    key = load(folder, "answer_key.json")
    delivered = {
        a["file"]: ev.parse_time(a["at"]) for a in actions if a["action"] == "deliver_file"
    }
    ledger_at = next((ev.parse_time(e["at"]) for e in events if e["kind"] == "ledger"), None)
    line_at = {}
    with (folder / "ledger.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            posting = ev.parse_time(f"{row['posting_date']}T00:00:00Z")
            line_at[row["line_id"]] = max(posting, ledger_at) if ledger_at else posting
    for a in actions:
        where = f"{folder.name}: user action {a['action']} {a.get('line_id') or a.get('file')}"
        at = ev.parse_time(a["at"])
        lid = a.get("line_id")
        if lid is not None and (lid not in line_at or at <= line_at[lid]):
            problems.append(f"{where}: comes before its ledger line arrives")
        if a["action"] == "answer_flag" and not any(
            x["line_id"] == lid and x["question"] == "flag" for x in key["answers"]
        ):
            problems.append(f"{where}: the key expects no flag on this line to answer")
        if a["action"] == "enter_share" and not any(
            x["line_id"] == lid and x["file"] == a["file"] and "amount_cents" in x
            for x in key["links"]
        ):
            problems.append(f"{where}: the key links no part of this bill to the line")
        if "file" not in a:
            continue
        event = scheduled.get(a["file"])
        if event is None:
            problems.append(f"{where}: its file isn't on the timeline")
            continue
        clock_at = ev.parse_time(event["at"])
        if a["action"] == "deliver_file":
            if event.get("deliver") != "user":
                problems.append(f"{where}: the file isn't marked for the user to deliver")
            if at < clock_at:
                problems.append(f"{where}: comes before the file's date")
        else:
            marked = event.get("deliver") == "user"
            arrived = delivered.get(a["file"]) if marked else clock_at
            if arrived is None or at <= arrived:
                problems.append(f"{where}: comes before its file arrives")


def check_sample_json(folder: Path, problems: list[str]) -> list[str]:
    """sample.json agrees with the timeline and the key, and its options are
    SampleChoice values with a name and a description. Returns its choices."""
    meta = load(folder, "sample.json")
    timeline = load(folder, "timeline.json")
    key = load(folder, "answer_key.json")
    where = f"{folder.name}: sample.json"
    if set(meta) != SAMPLE_JSON_FIELDS:
        problems.append(f"{where}: fields must be exactly {sorted(SAMPLE_JSON_FIELDS)}")
        return []
    if meta["sample"] != folder.name or timeline["sample"] != folder.name:
        problems.append(
            f"{where}: sample must be the folder's name, in sample.json and the timeline"
        )
    if meta["award_number"] != key["award_number"]:
        problems.append(f"{where}: award_number differs from the answer key's")
    if meta["starts_at"] != timeline["starts_at"]:
        problems.append(f"{where}: starts_at differs from the timeline's")
    events = timeline["events"]
    if events and meta["starts_at"] != events[0]["at"]:
        problems.append(f"{where}: starts_at isn't the first scheduled event")
    if (
        events
        and meta["last_event_at"] != events[-1]["at"]
        and not any(e["kind"] == "ledger" for e in events)
    ):
        problems.append(f"{where}: last_event_at isn't the last scheduled event")
    choices = []
    for i, option in enumerate(meta["options"]):
        if set(option) != OPTION_FIELDS:
            problems.append(f"{where}: option {i} must have exactly {sorted(OPTION_FIELDS)}")
            continue
        if option["choice"] not in SAMPLE_CHOICES:
            problems.append(f"{where}: option {i} choice {option['choice']!r} isn't a SampleChoice")
        for field in ("name", "description"):
            if not (isinstance(option[field], str) and option[field].strip()):
                problems.append(f"{where}: option {i} needs a {field}")
        if not isinstance(option["placeholder"], bool):
            problems.append(f"{where}: option {i} placeholder must be true or false")
        choices.append(option["choice"])
    return choices


def choices_in_contract(path: Path) -> tuple[str, ...] | None:
    """SampleChoice's values in the contract code, in order, or None before it exists."""
    if not path.is_file():
        return None
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ClassDef) and node.name == "SampleChoice":
            return tuple(
                stmt.value.value
                for stmt in node.body
                if isinstance(stmt, ast.Assign)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            )
    return None


def test_samples_follow_the_rule() -> None:
    """No user decision in a timeline, every user action possible at its time,
    and each sample.json consistent. Every SampleChoice is served by exactly one
    sample: the small one serves small_live, the larger one the other two."""
    problems: list[str] = []
    served: dict[str, list[str]] = {}
    for folder in folders():
        check_no_user_decision(folder, problems)
        check_user_actions(folder, problems)
        if folder.parent == SAMPLES:
            for choice in check_sample_json(folder, problems):
                served.setdefault(choice, []).append(folder.name)
    assert not problems, "\n".join(problems)
    assert served == {
        "small_live": [SMALL.name],
        "larger_live": [LARGER.name],
        "larger_prerun": [LARGER.name],
    }, served


def test_sample_choices_match_the_contract() -> None:
    """Once the contract code has SampleChoice, its values are this test's."""
    found = choices_in_contract(WORKSPACES_SOURCE)
    assert found is None or found == SAMPLE_CHOICES, found


def test_a_user_decision_in_a_timeline_fails() -> None:
    """A confirmation put back into a timeline, or a delivery of an unmarked
    file, is caught."""
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / SMALL.name
        shutil.copytree(SMALL, copy)
        timeline = load(copy, "timeline.json")
        timeline["events"].insert(
            1,
            {
                "at": timeline["events"][0]["at"],
                "kind": "accountant",
                "action": "confirm_terms",
                "file": timeline["events"][0]["file"],
            },
        )
        (copy / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
        actions = load(copy, "user_actions.json")
        actions["actions"].append(
            {
                "at": actions["actions"][0]["at"],
                "action": "deliver_file",
                "file": "invoice_EES-5531.pdf",
            }
        )
        # A marked file delivered before its date (ruling 44).
        for a in actions["actions"]:
            if a["action"] == "deliver_file" and a["file"] == "hardware_receipt.jpg":
                a["at"] = actions["actions"][0]["at"]
        (copy / "user_actions.json").write_text(json.dumps(actions), encoding="utf-8")
        problems: list[str] = []
        check_no_user_decision(copy, problems)
        check_user_actions(copy, problems)
    assert any("user decision" in p for p in problems), problems
    assert any("isn't marked for the user" in p for p in problems), problems
    assert any("comes before the file's date" in p for p in problems), problems


def test_a_bucket_that_rests_on_a_decision_needs_its_scripted_action() -> None:
    """S3c (no basis on file) marked complete fails without the accountant's typed
    share in the script, passes with a share that works out to the link, and
    fails with one that doesn't. A scripted action must also be possible at its
    time."""
    import shutil
    import tempfile

    folder = LARGER
    g = gen()[folder]
    problems: list[str] = []
    lines, arrivals, text = folder_inputs(folder, g, problems)
    assert not problems, problems
    key = load(folder, "answer_key.json")
    s3c = next(lid for lid, row in lines.items() if row["reference"] == "ECX-7702")
    for b in key["buckets"]:
        if b["line_id"] == s3c:
            b["bucket"] = "evidence_complete"
            b["at"] = "2026-03-20T12:00:00Z"

    def run(share: tuple[str, int, int] | None) -> list[str]:
        scripted = dict(arrivals)
        if share:
            scripted[f"enter_share:{s3c}"] = ev.parse_time("2026-03-12T17:00:00Z")
            scripted[f"enter_share_value:{s3c}"] = share  # type: ignore[assignment]
        out: list[str] = []
        check_invariants(key, lines, scripted, text, out)
        return out

    assert any("no basis" in p for p in run(None))
    assert not run(("invoice_ECX-7702.txt", 3, 5)), run(("invoice_ECX-7702.txt", 3, 5))
    assert any("scripted share" in p for p in run(("invoice_ECX-7702.txt", 1, 2)))

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / folder.name
        shutil.copytree(folder, copy)
        actions = load(copy, "user_actions.json")
        actions["actions"] += [
            {
                "at": "2026-03-09T12:00:00Z",
                "action": "enter_share",
                "line_id": s3c,
                "file": "invoice_ECX-7702.txt",
                "share": "3",
                "out_of": "5",
                "basis": "Three fifths of the shared dewar's nitrogen",
            },
            {
                "at": "2026-03-12T12:00:00Z",
                "action": "answer_flag",
                "line_id": s3c,
                "answer": "supports",
            },
        ]
        (copy / "user_actions.json").write_text(json.dumps(actions), encoding="utf-8")
        found: list[str] = []
        check_user_actions(copy, found)
    assert any("before its ledger line arrives" in p for p in found), found
    assert any("no flag on this line" in p for p in found), found


def test_larger_sample() -> None:
    """The larger sample reaches closeout: its timeline starts with its award
    letter and runs past the start of its 90-day closeout window."""
    g = gen()[LARGER]
    end = datetime.combine(g.end, datetime.min.time(), g.first_event_at().tzinfo)
    assert g.docs[0].name.startswith("award_letter.") and g.docs[0].at == g.first_event_at()
    assert g.last_event_at() > end - timedelta(days=90), "never reaches its closeout window"


def test_small_sample() -> None:
    """The small sample starts with its award letter, then its ledger, and has
    emails, invoices, a photo, later lines and files marked for the user."""
    g = gen()[SMALL]
    events = json.loads((SMALL / "timeline.json").read_text(encoding="utf-8"))["events"]
    assert events[0]["kind"] == "file" and events[0]["file"].startswith("award_letter.")
    assert events[1]["kind"] == "ledger"
    names = [d.name for d in g.docs]
    assert any(n.endswith(".eml") for n in names)
    assert any(n.startswith("invoice_") for n in names)
    assert any(Path(n).suffix in PHOTO_SUFFIXES for n in names)
    assert any(d.deliver == "user" for d in g.docs), "no file marked for the user"
    assert any(g.line_arrival(ln) > g.ledger_at for ln in g.lines), "no later ledger lines"


def test_line_ids_are_unique() -> None:
    """Ledger line IDs are unique across every grant (contracts.md section 6)."""
    g = gen()
    ids = [ln.line_id for folder in folders() for ln in g[folder].lines]
    assert len(ids) == len(set(ids))


if __name__ == "__main__":
    failed = 0
    for test in (
        test_files_and_keys,
        test_invariants_catch_false_clears,
        test_account_categories_match_the_table,
        test_samples_follow_the_rule,
        test_sample_choices_match_the_contract,
        test_a_user_decision_in_a_timeline_fails,
        test_a_bucket_that_rests_on_a_decision_needs_its_scripted_action,
        test_larger_sample,
        test_small_sample,
        test_line_ids_are_unique,
    ):
        try:
            test()
            print(f"ok    {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {test.__name__}\n{exc}")
    sys.exit(1 if failed else 0)
