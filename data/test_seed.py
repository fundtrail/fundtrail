"""Checks the two sample grants and the two unused seed grants.

- The files on disk are exactly what data/generator/build.py makes (images
  aside, which depend on the machine's fonts), so nobody edits one by hand.
- Each ledger follows docs/contracts.md section 13 and each answer key section
  14. Each timeline holds scheduled events only, and each line arrives by
  decision 0023's rule. The user actions are the script the key assumes.
- Every value a key expects is written in its file. A sample's typeset PDF is
  read back with pdfium: every row of its text has to be on the page, in order.
  An image is read from the strings the generator drew on it. A scan or a photo
  made from a typeset page is read from that page's text: a scanned PDF has no
  text layer, so its words' boxes are checked in place of a read-back.
- Every passage the stand-in agent's records cite into a PDF is found there by
  the app's own quote finder, with its value, as often as the text has it.
- The synthetic-data rule (CLAUDE.md): award numbers start with SYN-, email
  addresses are at .example, and nothing has an em dash or an en dash.
- The larger sample's timeline runs from its start into its closeout window,
  and the small sample starts with its award letter and its ledger.

It runs the generator, so it needs reportlab and pypdfium2, and the quote finder
is the backend's. Run it from backend/:

    cd backend && uv run python ../data/test_seed.py
    cd backend && uv run pytest ../data/test_seed.py

It borrows the eval cases' checks from eval/test_cases.py.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import importlib.util
import json
import math
import re
import sys
from datetime import date, datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent
sys.path.insert(0, str(DATA.parent / "backend"))  # for the app's quote finder
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
    "agent_records.json",
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
    # Ruling 59. A held Gmail file let in; a reason accepted with the accountant's
    # note, about a line, a file, or neither (the grant); the sign-off with its
    # note. For these two, `note` is the accountant's note and is required.
    "let_in_mail": ({"file"}, set()),
    "accept_reason": ({"check"}, {"problem", "line_id", "file"}),
    "sign_off": (set(), set()),
}
# Steps the answer key can't measure (it doesn't express suggestions, grant
# problems, held mail or the sign-off), so "no more than the key assumes" can't
# be checked for them.
UNMEASURED = {"decide_suggestion", "let_in_mail", "accept_reason", "sign_off"}
NOTE_REQUIRED = {"accept_reason", "sign_off"}
USER_ACTIONS = set(ACTION_FIELDS)
DECISIONS = {"accept", "reject"}
RECORDS_SOURCE = DATA.parent / "backend" / "app" / "contracts" / "records.py"
# The record kinds an agent's suggestion can be, the ones that wait for the
# accountant (contracts.md section 1, "What counts"): a fix to a link, a new
# answer, a checklist removal, a dispute, a duplicate mark, a correction, a
# remainder, or a retraction of its own flag. Each must be a RecordKind.
SUGGESTION_KINDS = {
    "link",
    "judgment",
    "checklist_removal",
    "dispute",
    "duplicate",
    "correction",
    "remainder",
    "retraction",
}
# The record kinds that are a grant's terms, which confirm_terms confirms.
TERM_RECORD_KINDS = {
    "period_of_performance",
    "budget_line",
    "person",
    "approval_rule",
    "rate",
    "notice",
    "other_term",
}
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
MAX_FILE_BYTES = 500_000  # a phone photo of a receipt is the largest
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
    # Ruling 61: a benefit rate term, one row of the rate agreement. Its rate is a
    # fraction and its group the contract's BenefitGroup, so neither is written as
    # such in the file; its name and dates are.
    "rate": {"name", "rate", "applies_to", "effective_from", "effective_to", "dated"},
    "approval_rule": ev.RECORD_FIELDS["approval_rule"] | {"scope"},
}
UNCITED_FIELDS = ev.UNCITED_FIELDS | {"scope", "rate", "applies_to"}
DATE_FIELDS = ev.DATE_FIELDS | {"effective_from", "effective_to"}
# The composite benefit rate accounts (ruling 61): code fills a benefit charge's
# "Benefit rate" item from the confirmed rate and its salary lines, with no link.
BENEFIT_ACCOUNTS = {"53060", "53070", "53080", "53085", "53086"}
APPROVAL_SCOPES = {"every_charge", "moved_out"}
# The pictures (photos and scans, the scanned PDFs among them) depend on the machine's
# fonts, so the generator's bytes can't be compared. Their hashes catch a picture
# swapped or edited by hand. After redrawing them on purpose (build.py --photos),
# update these.
PHOTO_SHA256 = {
    "demo/coastal-microbial-genomics/taxi_receipt_ocean_sciences_2026.jpg": (
        "3210e49710071f2bfb82d3bf6a528c731ecc62a6f55baf2d6fac80c98217f310"
    ),
    "samples/nitrate-sensors/hardware_receipt.jpg": (
        "32c3a51ac7b4459f410a40f94fc0333c306b8bb743927a5bb34fbe5709e244b1"
    ),
    "samples/salt-marsh-carbon/taxi_receipt_egu_2024.jpg": (
        "50533f521a574c6bdcbefd7ee2151d7caf1cc309e30c76a644ff32c4b20279d5"
    ),
    "samples/salt-marsh-carbon/hotel_folio_egu-2024.jpg": (
        "dfd928d0e643872e23b3eea2413b45df356034683804e2a62586831ea85528a8"
    ),
    "samples/salt-marsh-carbon/invoice_INV-12655.pdf": (
        "19679ce302a56812bae9c864c4b873799a7339d119aa30e4d70cbcea75b965a9"
    ),
    "samples/salt-marsh-carbon/invoice_EFG-56443.pdf": (
        "8f82981119360df0720583ce9418361cc8d7de11b4d2fcfb5f6bff51cf254d5e"
    ),
    "samples/salt-marsh-carbon/appointment_letter_castellano.pdf": (
        "e33a01e3ca8ce759b6658283fb9eb37b76bcff1a89deaa3356ccd90cef1ea5cb"
    ),
    "samples/salt-marsh-carbon/scan_invoice_ESS-55120.jpg": (
        "1ef97f648cde2b6ec0dbec4b4596bb72ff2217d7ce7dd52cc125a4be4f2fff47"
    ),
}
# The highlights each sample marks in its timeline (the sample content brief).
LARGER_HIGHLIGHTS = {
    "Terms tied to their passages",  # 1
    "Invoice before its line",  # 2
    "Receipt photo you deliver",  # 3
    "Shared invoice, 56 of 96",  # 4
    "Own fee, own approval",  # 5
    "Extension found in Drive",  # 6
    "Held vendor email",  # 7
    "Moved off the grant",  # 7
    "Over budget",  # 8
    "More money, a higher limit",  # 8
    "Closeout",  # 9
    "Same invoice twice",  # 10
    "One report, six salary lines",  # 11
    "Bill under its charge",  # 12
}
# The three highlights that sit on a ledger line's event, where the charge posts, so the
# charge is on screen when the clock lands there (ruling 77).
HIGHLIGHT_ON_LINE = {
    "Invoice before its line": "L-1835-0013",
    "Shared invoice, 56 of 96": "L-1835-0014",
    "Held vendor email": "L-1835-0030",
}
SMALL_HIGHLIGHTS = {
    "Terms tied to their passages",
    "Invoice before its line",
    "Receipt photo you deliver",
}
# The scripted steps that are a highlight's own, the user's part of it, with the label
# they carry (ruling 77). Every other step carries none: the rate agreement's
# confirmation belongs to no highlight.
HIGHLIGHT_STEPS = {
    LARGER: {
        (("confirm_terms", "award_letter.pdf"), "Terms tied to their passages"),
        (("deliver_file", "taxi_receipt_egu_2024.jpg"), "Receipt photo you deliver"),
        (("decide_suggestion", "scan_invoice_ESS-55120.jpg"), "Same invoice twice"),
        (("let_in_mail", "email_invoice_EFG-30418.eml"), "Held vendor email"),
        (("accept_reason", None), "Over budget"),
        (("confirm_terms", "notice_001_increment.pdf"), "More money, a higher limit"),
        (("confirm_terms", "extension_notice_002.pdf"), "Extension found in Drive"),
        (("sign_off", None), "Closeout"),
    },
    SMALL: {
        (("confirm_terms", "award_letter.pdf"), "Terms tied to their passages"),
        (("deliver_file", "hardware_receipt.jpg"), "Receipt photo you deliver"),
    },
}
TJ = re.compile(rb"\(((?:\\.|[^\\)])*)\)\s*Tj")


# ---------------------------------------------------------------- reading files


def pdf_text(data: bytes) -> str:
    """The text of a typewriter PDF the generator wrote for an unused seed grant: one
    Tj string per line."""
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
    out["agent_records_json"] = build.agent_records_json
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


def is_picture(doc) -> bool:
    """Whether a file is a picture of paper: a photo or a scan, a scanned PDF included."""
    return Path(doc.name).suffix in PHOTO_SUFFIXES or doc.boxes is not None or doc.words is not None


def texts(files: Path, grant) -> dict[str, str]:
    """What a reader sees in each evidence file, read back from disk.

    A typeset PDF and an image give the generator's text for them: check_folder
    holds the PDF to having every row of it, and an image is its drawn strings."""
    docs = {d.name: d for d in grant.docs}
    out = {}
    for p in sorted(files.iterdir()):
        if not p.is_file() or p.name in META_FILES:
            continue
        data = p.read_bytes()
        doc = docs.get(p.name)
        if doc is not None and (doc.pages is not None or doc.words is not None):
            out[p.name] = doc.text
        elif p.suffix == ".pdf":
            out[p.name] = pdf_text(data)
        elif p.suffix in PHOTO_SUFFIXES:
            out[p.name] = doc.text if doc is not None else ""
        else:
            out[p.name] = data.decode("utf-8")
    return out


def typeset_module():
    sys.path.insert(0, str(GENERATOR))
    try:
        import typeset
    finally:
        sys.path.pop(0)
    return typeset


# ---------------------------------------------------------------- checks


def check_generated(key_dir: Path, files: Path, grant, problems: list[str]) -> None:
    expected = {d.name: d.data for d in grant.docs}
    expected["ledger.csv"] = grant.ledger_csv().encode()
    on_disk = {p.name for p in files.iterdir() if p.is_file() and p.name not in META_FILES}
    for name in sorted(on_disk - set(expected)):
        problems.append(f"{name}: on disk but the generator doesn't make it")
    pictures = {d.name for d in grant.docs if is_picture(d)}
    for name, data in expected.items():
        path = files / name
        if not path.is_file():
            problems.append(f"{name}: the generator makes it but it isn't on disk")
        elif name in pictures:
            rel = path.relative_to(DATA).as_posix()
            if hashlib.sha256(path.read_bytes()).hexdigest() != PHOTO_SHA256.get(rel):
                problems.append(f"{rel}: isn't the picture the test knows (PHOTO_SHA256)")
        elif path.read_bytes() != data:
            problems.append(f"{name}: differs from the generator's output; run build.py")
    made_files = [
        ("answer_key.json", grant.key_json()),
        ("timeline.json", grant.timeline_json()),
        ("user_actions.json", grant.user_actions_json()),
    ]
    if key_dir.parent == SAMPLES:
        made_files.append(("sample.json", gen()["sample_json"](grant)))
        made_files.append(("agent_records.json", gen()["agent_records_json"](grant)))
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
            allowed = {"at", "kind", "file", "source", "sender", "deliver", "highlight", "note"}
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
            allowed = {"at", "kind", "file", "highlight", "note"}
            if e.get("file") != "ledger.csv" or ledger_at is not None:
                problems.append(f"{where}: one ledger event, for ledger.csv")
            ledger_at = t
        elif kind == "ledger_line":
            allowed = {"at", "kind", "line_id", "highlight", "note"}
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
        if "highlight" in e and not (isinstance(e["highlight"], str) and e["highlight"].strip()):
            problems.append(f"{where}: a highlight label can't be blank")
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

    # A step that is a highlight's own carries a label a timeline event carries (ruling 77).
    labels = {e["highlight"] for e in timeline["events"] if "highlight" in e}
    for i, a in enumerate(actions["actions"]):
        where = f"user_actions.json actions[{i}]"
        if a.get("action") not in USER_ACTIONS or not ev.ISO_TIME.match(str(a.get("at"))):
            problems.append(f"{where}: needs at and an action in {sorted(USER_ACTIONS)}")
            continue
        required, optional = ACTION_FIELDS[a["action"]]
        given = set(a) - {"at", "action", "note", "highlight"}
        if "highlight" in a and a["highlight"] not in labels:
            problems.append(f"{where}: no timeline event is the highlight {a['highlight']!r}")
        if a["action"] in NOTE_REQUIRED and not str(a.get("note", "")).strip():
            problems.append(f"{where}: {a['action']} needs the accountant's note")
        if not required <= given or given - required - optional:
            problems.append(
                f"{where}: {a['action']} takes {sorted(required)}, and may take {sorted(optional)}"
            )
            continue
        if a["action"] == "decide_suggestion":
            if a["decision"] not in DECISIONS or not ({"line_id", "file"} & given):
                problems.append(f"{where}: a decision is accept or reject, about a line or a file")
            if a["suggestion"] not in SUGGESTION_KINDS:
                problems.append(
                    f"{where}: suggestion {a['suggestion']!r} isn't one of "
                    f"{sorted(SUGGESTION_KINDS)}"
                )
        if a["action"] == "answer_flag" and a["answer"] not in ev.ANSWERS:
            problems.append(f"{where}: answer must be one of {sorted(ev.ANSWERS)}")
        share = None
        if a["action"] == "enter_share":
            share = typed_share(a)
            if share is None:
                problems.append(
                    f"{where}: share and out_of must be numbers, with out_of above 0 and "
                    f"the share from 0 to out_of"
                )
                continue
        t = ev.parse_time(a["at"])
        out[f"{a['action']}:{a.get('line_id') or a.get('file')}"] = t
        if a["action"] == "answer_flag":
            out[f"answer_flag_value:{a['line_id']}"] = a["answer"]  # type: ignore[assignment]
        if share is not None:
            out[f"enter_share_value:{a['line_id']}"] = (a["file"], *share)  # type: ignore[assignment]
        if a["action"] in ("deliver_file", "let_in_mail"):
            # A file marked for the user arrives when the user brings it in, and a
            # held email when the accountant lets it in.
            out[f"file:{a['file']}"] = t
    return out


def typed_share(action: dict) -> tuple[float, float] | None:
    """A scripted share and its whole, or None when they aren't a usable share."""
    try:
        share, whole = float(str(action["share"])), float(str(action["out_of"]))
    except ValueError:
        return None
    if not (math.isfinite(share) and math.isfinite(whole) and whole > 0 and 0 <= share <= whole):
        return None
    return share, whole


def kinds_in_contract(path: Path) -> set[str] | None:
    """RecordKind's values in the contract code, or None if it isn't there."""
    if not path.is_file():
        return None
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ClassDef) and node.name == "RecordKind":
            return {
                stmt.value.value
                for stmt in node.body
                if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
            }
    return None


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
        elif ftype in DATE_FIELDS:
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
    if kind in ev.TERM_KINDS | {"rate"} and "dated" not in fields:
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
        complete = any(
            b["line_id"] == lid and b["bucket"] == "evidence_complete" for b in key["buckets"]
        )
        if complete and bills and bills != ev.cents_of(lines[lid]):
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
        if p.is_file() and p.name not in META_FILES and p.stat().st_size > MAX_FILE_BYTES:
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
        benefit = lines[lid]["account"].split(" ")[0] in BENEFIT_ACCOUNTS
        if not links_by_line.get(lid) and not benefit:
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
    drawn: dict[str, str] = {}
    for d in grant.docs:
        if not d.name.endswith(".pdf") or d.name not in text:
            continue
        if d.words is not None:
            continue  # a scan: no text layer to read back (check_pictures)
        if d.pages is None:
            if text[d.name] != d.text.rstrip("\n"):
                problems.append(f"{d.name}: its PDF text doesn't read back as written")
            continue
        # A typeset PDF: every row of its text is on the page, in order, on the pages
        # the records cite. What else the page says (its furniture) is checked too.
        typeset = typeset_module()
        data = (files / d.name).read_bytes()
        try:
            if typeset.locate(data, d.text) != d.pages:
                problems.append(f"{d.name}: its rows aren't on the pages the generator found")
        except ValueError as error:
            problems.append(f"{d.name}: {error}")
        drawn[f"{d.name} (as drawn)"] = "\n".join(typeset.page_texts(data))
    lines = check_ledger(files, problems)
    arrivals = check_timeline(key_dir, files, lines, problems)
    check_key(key_dir, lines, arrivals, text, grant.award_number, problems)
    check_synthetic(files, {**text, **drawn}, problems)
    if key_dir.parent == SAMPLES:
        check_sample_names(text | drawn, problems)
        check_marked(grant, drawn, problems)
        check_pictures(files, grant, problems)
    return [f"{key_dir.name}: {p}" for p in problems]


def check_pictures(files: Path, grant, problems: list[str]) -> None:
    """A scan or a photo made from a typeset page.

    - A scanned PDF is one page with no text layer, so the app sends it as an image.
    - It has the words of every row of the document's text, each with a box that lies
      inside the picture and isn't empty.
    """
    typeset = typeset_module()
    for d in grant.docs:
        if d.words is None:
            continue
        if d.name.endswith(".pdf"):
            pages = typeset.page_texts((files / d.name).read_bytes())
            if len(pages) != 1 or pages[0].strip():
                problems.append(f"{d.name}: a scan is one page with no text layer")
        rows = d.text.split("\n")
        if len(rows) != len(d.words):
            problems.append(f"{d.name}: its word boxes don't line up with its text's rows")
            continue
        for n, (row, words) in enumerate(zip(rows, d.words, strict=True)):
            if [w for w, _ in words or []] != row.split():
                problems.append(f"{d.name}: row {n}'s words aren't the text's: {row.strip()!r}")
            for word, (left, top, width, height) in words or []:
                inside = 0 <= left and 0 <= top and left + width <= 1 and top + height <= 1
                if not inside or width <= 0 or height <= 0:
                    problems.append(f"{d.name}: the box of {word!r} isn't on the picture")


def check_sample_names(text: dict[str, str], problems: list[str]) -> None:
    """A sample's names are invented, realistic ones: no placeholder "Example" is left
    in any file, apart from the .example domain of an email address."""
    for name, body in text.items():
        if re.search(r"(?<![.\w])example", body, re.IGNORECASE):
            problems.append(f"{name}: still says Example")


# The documents laid out like an agency's or a university's own notice, by the start
# of their file names. Each says on every page that it's a synthetic sample.
MARKED = ("award_letter", "notice_0", "extension_notice", "rate_agreement", "notice_of_exp")
SYNTHETIC_MARK = "Synthetic sample document for a software demonstration. Not issued by"


def check_marked(grant, drawn: dict[str, str], problems: list[str]) -> None:
    typeset = typeset_module()
    for d in grant.docs:
        if d.name.startswith("closeout_certification") and SYNTHETIC_MARK not in d.text:
            problems.append(f"{d.name}: doesn't say it's a synthetic sample")
        if d.name.startswith(MARKED) and d.pages is not None:
            for n, page in enumerate(typeset.page_texts(d.data), start=1):
                if SYNTHETIC_MARK not in " ".join(page.split()):
                    problems.append(f"{d.name}: page {n} doesn't say it's a synthetic sample")


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
    assert run("river-delta-sediment", complete("ECX-7702")), "S3c marked complete"
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
    let_in = {a["file"]: ev.parse_time(a["at"]) for a in actions if a["action"] == "let_in_mail"}
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
        if lid is not None and lid not in line_at:
            problems.append(f"{where}: line_id {lid!r} isn't in the ledger")
            continue
        if lid is not None and at <= line_at[lid]:
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
        check_needed(a, key, actions, problems, where)
        if "file" not in a:
            continue
        event = scheduled.get(a["file"])
        if event is None:
            problems.append(f"{where}: its file isn't on the timeline")
            continue
        clock_at = ev.parse_time(event["at"])
        if a["action"] == "let_in_mail":
            known = {
                r["fields"].get("email", "").casefold()
                for r in key["records"]
                if r["kind"] == "person"
            }
            if event.get("source") != "gmail" or str(event.get("sender", "")).casefold() in known:
                problems.append(f"{where}: only a Gmail file from an unknown sender is held")
            if at < clock_at:
                problems.append(f"{where}: comes before the email arrives")
            continue
        if a["action"] == "deliver_file":
            if event.get("deliver") != "user":
                problems.append(f"{where}: the file isn't marked for the user to deliver")
            if at < clock_at:
                problems.append(f"{where}: comes before the file's date")
        else:
            marked = event.get("deliver") == "user"
            arrived = delivered.get(a["file"]) if marked else let_in.get(a["file"], clock_at)
            if arrived is None or at <= arrived:
                problems.append(f"{where}: comes before its file arrives")


# The buckets a scripted decision clears a line to. A flag answered supports
# takes away the flag's Needs a human, leaving Evidence complete or Missing
# evidence. Answered contradicts, it's Possible conflict. Answered unsure, it
# clears nothing. A typed share gives part of a bill its basis, so the line can
# be complete, or still missing other evidence.
CLEARS_TO: dict[tuple[str, str | None], set[str]] = {
    ("answer_flag", "supports"): {"evidence_complete", "missing_evidence"},
    ("answer_flag", "contradicts"): {"possible_conflict"},
    ("answer_flag", "unsure"): set(),
    ("enter_share", None): {"evidence_complete", "missing_evidence"},
}


def needs_typed_share(key: dict, line_id: str, bill: str) -> bool:
    """Whether the key's link of part of this bill to this line has no basis on
    file (decision 0021): no note linked to the line, no item of the bill with the
    link's amount, and no other link on the grant taking the rest of the bill."""
    total = next(
        (
            int(r["fields"]["total"])
            for r in key["records"]
            if r["file"] == bill and r["kind"] == "bill"
        ),
        None,
    )
    link = next(
        (
            x
            for x in key["links"]
            if x["line_id"] == line_id and x["file"] == bill and "amount_cents" in x
        ),
        None,
    )
    if total is None or link is None or abs(link["amount_cents"]) >= abs(total):
        return False
    items = {
        int(v)
        for r in key["records"]
        if r["file"] == bill and r["kind"] == "bill"
        for k, v in r["fields"].items()
        if k.endswith("].amount")
    }
    used = sum(x["amount_cents"] for x in key["links"] if x["file"] == bill and "amount_cents" in x)
    notes = any(x["line_id"] == line_id and "amount_cents" not in x for x in key["links"])
    return not (notes or link["amount_cents"] in items or used == total)


def check_needed(a: dict, key: dict, actions: list[dict], problems: list[str], where: str) -> None:
    """No more than the key assumes (ruling 47).

    - confirm_terms confirms a file the key reads terms from, once.
    - deliver_file delivers a marked file once.
    - answer_flag and enter_share are followed by the bucket the decision clears
      the line to: the first bucket the key gives the line after the step must be
      the one the decision leads to (CLEARS_TO). enter_share is only for part of
      a bill with no basis on file.
    A decide_suggestion can't be checked this way yet: the key doesn't express
    suggestions (contracts.md section 14).
    """
    same = [
        b
        for b in actions
        if b["action"] == a["action"]
        and b.get("file") == a.get("file")
        and b.get("line_id") == a.get("line_id")
    ]
    if len(same) > 1 and a["action"] in (
        "confirm_terms",
        "deliver_file",
        "enter_share",
        "answer_flag",
        "let_in_mail",
        "sign_off",
    ):
        problems.append(f"{where}: scripted more than once")
    if a["action"] == "confirm_terms" and not any(
        r["file"] == a["file"] and r["kind"] in TERM_RECORD_KINDS for r in key["records"]
    ):
        problems.append(f"{where}: the key reads no terms from this file to confirm")
    if a["action"] in ("answer_flag", "enter_share"):
        after = sorted(
            (b for b in key["buckets"] if b["line_id"] == a["line_id"] and b["at"] > a["at"]),
            key=lambda b: b["at"],
        )
        cleared = CLEARS_TO.get((a["action"], a.get("answer")), set())
        if not after or after[0]["bucket"] not in cleared:
            problems.append(
                f"{where}: the key's next bucket on this line isn't one it clears to "
                f"({', '.join(sorted(cleared)) or 'none'})"
            )
    if a["action"] == "enter_share" and not needs_typed_share(key, a["line_id"], a["file"]):
        problems.append(f"{where}: the key's link already has a basis on file")


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

    folder = DEMO / "river-delta-sediment"
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
    assert not run(("invoice_ECX-7702.txt", 2, 5)), run(("invoice_ECX-7702.txt", 2, 5))
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


def test_suggestion_kinds_are_record_kinds() -> None:
    """Every suggestion kind the script allows is one of the contract's record kinds."""
    kinds = kinds_in_contract(RECORDS_SOURCE)
    assert kinds is None or SUGGESTION_KINDS <= kinds, SUGGESTION_KINDS - (kinds or set())
    assert kinds is None or TERM_RECORD_KINDS <= kinds, TERM_RECORD_KINDS - (kinds or set())


def test_a_script_with_more_than_the_key_assumes_fails() -> None:
    """Steps the key doesn't assume, or that can't be read, are reported as
    problems, not tracebacks: a share typed where a basis is on file (S3a), a
    confirmation of an invoice, a suggestion that isn't a record kind, a share
    that isn't a number or is out of 0, and a line that isn't in the ledger."""
    # A share the loader would refuse: not a number, infinite, or out of nothing.
    for share, whole in (
        ("many", "96"),
        ("Infinity", "Infinity"),
        ("56", "inf"),
        ("1", "0"),
        ("NaN", "96"),
        ("97", "96"),
    ):
        assert typed_share({"share": share, "out_of": whole}) is None, (share, whole)
    assert typed_share({"share": "56", "out_of": "96"}) == (56.0, 96.0)

    import shutil
    import tempfile

    g = gen()[LARGER]
    s3a = next(ln.line_id for ln in g.lines if ln.reference == "EGS-20931")
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / LARGER.name
        shutil.copytree(LARGER, copy)
        actions = load(copy, "user_actions.json")
        later = "2026-06-01T12:00:00Z"
        actions["actions"] += [
            {
                "at": later,
                "action": "enter_share",
                "line_id": s3a,
                "file": "invoice_EGS-20931.pdf",
                "share": "56",
                "out_of": "96",
                "basis": "x",
            },
            {"at": later, "action": "confirm_terms", "file": "invoice_EGS-20931.pdf"},
            {
                "at": later,
                "action": "decide_suggestion",
                "suggestion": "snooze",
                "decision": "accept",
                "line_id": s3a,
            },
            {
                "at": later,
                "action": "enter_share",
                "line_id": s3a,
                "file": "invoice_EGS-20931.pdf",
                "share": "many",
                "out_of": "0",
                "basis": "x",
            },
            {"at": later, "action": "answer_flag", "line_id": "L-0000-0000", "answer": "supports"},
            # An answer that isn't supports, contradicts or unsure.
            {"at": later, "action": "answer_flag", "line_id": s3a, "answer": "maybe"},
        ]
        (copy / "user_actions.json").write_text(json.dumps(actions), encoding="utf-8")
        problems: list[str] = []
        lines = check_ledger(copy, problems)
        check_timeline(copy, copy, lines, problems)
        check_user_actions(copy, problems)
    text = "\n".join(problems)
    for expected in (
        "already has a basis on file",
        "reads no terms from this file",
        "isn't one of",
        "must be numbers",
        "isn't in the ledger",
        "answer must be one of",
    ):
        assert expected in text, (expected, problems)

    # S3c's key stays Needs a human, so a typed share clears it to nothing.
    c = DEMO / "river-delta-sediment"
    s3c = next(ln.line_id for ln in gen()[c].lines if ln.reference == "ECX-7702")
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / c.name
        shutil.copytree(c, copy)
        actions = load(copy, "user_actions.json")
        actions["actions"].append(
            {
                "at": "2026-06-01T12:00:00Z",
                "action": "enter_share",
                "line_id": s3c,
                "file": "invoice_ECX-7702.txt",
                "share": "2",
                "out_of": "5",
                "basis": "Two fifths of the shared dewar's nitrogen",
            }
        )
        (copy / "user_actions.json").write_text(json.dumps(actions), encoding="utf-8")
        found: list[str] = []
        check_user_actions(copy, found)
    assert any("isn't one it clears to" in p for p in found), found


def citations(obj) -> list[dict]:
    """Every citation inside a record's data."""
    found = []
    if isinstance(obj, dict):
        if "file_id" in obj and "location" in obj:
            found.append(obj)
        for v in obj.values():
            found += citations(v)
    elif isinstance(obj, list):
        for v in obj:
            found += citations(v)
    return found


def check_agent_records(folder: Path, grant, problems: list[str]) -> None:
    """agent_records.json, the agent's expected records for the checks-only play.

    - Every link, budget line and answer the key expects is there, on the same
      charge, with the same amount or answer.
    - Every citation points at a file of the sample and its passage is really
      there: at its characters in a text file, on its page in a PDF. A photo's box
      lies inside the photo.
    - Nothing is written before its file or its charge arrives.
    """
    body = load(folder, "agent_records.json")
    key = load(folder, "answer_key.json")
    where = f"{folder.name}: agent_records.json"
    records = body["records"]
    by_id = {r["id"]: r for r in records}
    file_of: dict[str, str] = {}
    for r in records:
        if r["data"]["kind"] in ("bill", "note", "approval"):
            cites = citations(r["data"])
            file_of[r["id"]] = cites[0]["file_id"].removeprefix("file-") if cites else ""
    links = {
        (
            file_of.get(r["data"]["record_id"]),
            r["data"]["charge_id"].removeprefix("chg-"),
            r["data"].get("amount_cents"),
        )
        for r in records
        if r["data"]["kind"] == "link"
    }
    for lk in key["links"]:
        if (lk["file"], lk["line_id"], lk.get("amount_cents")) not in links:
            problems.append(f"{where}: no link of {lk['file']} to {lk['line_id']}")
    names = {
        r["id"]: r["data"]["name"]["value"] for r in records if r["data"]["kind"] == "budget_line"
    }
    budgets = {
        (r["data"]["charge_id"].removeprefix("chg-"), names.get(r["data"]["record_id"]))
        for r in records
        if r["data"]["kind"] == "budget_assignment"
    }
    for b in key["budget_lines"]:
        if (b["line_id"], b["budget_line"]) not in budgets:
            problems.append(f"{where}: no budget line {b['budget_line']!r} for {b['line_id']}")
    last_answer: dict[tuple[str, str], str] = {}
    for r in records:
        d = r["data"]
        if d["kind"] == "judgment":
            last_answer[(d["charge_id"].removeprefix("chg-"), d["question"])] = d["answer"]
    for a in key["answers"]:
        if last_answer.get((a["line_id"], a["question"])) != a["answer"]:
            problems.append(f"{where}: no {a['question']} answer {a['answer']} on {a['line_id']}")

    docs = {d.name: d for d in grant.docs}
    arrived = {d.name: grant.file_arrival(d.name) for d in grant.docs}
    # File order: a record comes after every record it points to, as a run writes
    # them (a note before the link to it).
    seen: set[str] = set()
    for r in records:
        d = r["data"]
        refs = {d.get("record_id"), r.get("replaces_id"), *d.get("rests_on", [])} - {None}
        if missing := refs - seen:
            problems.append(f"{where}: {r['id']} comes before {sorted(missing)} it points to")
        seen.add(r["id"])
    line_at = {f"chg-{ln.line_id}": grant.line_arrival(ln) for ln in grant.lines}
    for r in records:
        rid = r["id"]
        written = ev.parse_time(r["written_at"])
        charge = r["data"].get("charge_id")
        if charge is not None and (charge not in line_at or written < line_at[charge]):
            problems.append(f"{where}: {rid} is written before its charge arrives")
        for target in ("record_id", "replaces_id"):
            ref = r["data"].get(target) if target == "record_id" else r.get(target)
            if ref is not None and (ref not in by_id or by_id[ref]["written_at"] > r["written_at"]):
                problems.append(f"{where}: {rid} points to {ref}, not written before it")
        for c in citations(r["data"]):
            name = c["file_id"].removeprefix("file-")
            if name not in docs:
                problems.append(f"{where}: {rid} cites {name}, which isn't a file of the sample")
                continue
            if written < arrived[name]:
                problems.append(f"{where}: {rid} cites {name} before it arrives")
            loc, rows = c["location"], docs[name].text.split("\n")
            if loc["type"] == "char_location":
                got = docs[name].text[loc["start_char_index"] : loc["end_char_index"]]
                if got != c["passage"]:
                    problems.append(f"{where}: {rid}'s passage isn't at its characters in {name}")
            elif loc["type"] == "page_location":
                # The passage is a row of the file's text, cited on the pages the
                # typeset PDF puts that row on. test_pdf_citations_are_found then
                # finds it in the PDF itself.
                pages = (loc["start_page_number"], loc["end_page_number"] - 1)
                spaced = [" ".join(r.split()) for r in rows]
                at = [docs[name].pages[i] for i, r in enumerate(spaced) if r == c["passage"]]
                if pages not in at:
                    problems.append(f"{where}: {rid}'s passage isn't a row of {name} there")
            elif loc["type"] == "image_box":
                box = (loc["left"], loc["top"], loc["width"], loc["height"])
                if not (
                    0 <= loc["left"]
                    and loc["left"] + loc["width"] <= 1
                    and 0 <= loc["top"]
                    and loc["top"] + loc["height"] <= 1
                ):
                    problems.append(f"{where}: {rid}'s box isn't inside {name}")
                elif docs[name].words is not None:
                    # A picture of a typeset page: the box is around words of one row.
                    left, top = loc["left"], loc["top"]
                    right, bottom = left + loc["width"], top + loc["height"]
                    held = [
                        [
                            w
                            for w, b in row
                            if b[0] >= left - 1e-6
                            and b[1] >= top - 1e-6
                            and b[0] + b[2] <= right + 1e-3
                            and b[1] + b[3] <= bottom + 1e-3
                        ]
                        for row in docs[name].words
                        if row
                    ]
                    words = max(held, key=len)
                    if loc["page"] != 1 or not words:
                        problems.append(f"{where}: {rid}'s box holds no word of {name}")
                elif box not in (docs[name].boxes or []):
                    problems.append(f"{where}: {rid}'s box isn't a string drawn on {name}")
            else:
                problems.append(f"{where}: {rid} has a {loc['type']} citation")


def test_agent_records_match_the_key() -> None:
    """Each sample's agent_records.json gives the key's links, budget lines and
    answers, with citations that point at their files."""
    g = gen()
    problems: list[str] = []
    for folder in (LARGER, SMALL):
        check_agent_records(folder, g[folder], problems)
    assert not problems, "\n".join(problems[:30])


def check_pdf_citations(folder: Path, grant, problems: list[str]) -> None:
    """Every passage agent_records.json cites into a PDF is found in the file on disk
    by the app's own quote finder, on the pages cited, with its value.

    It's found as often as the file's text has it and no more: a page's furniture
    mustn't repeat a cited passage, or a value would be found twice."""
    from app.quotes.pdf import find_pdf_quote

    docs = {d.name: d for d in grant.docs}
    seen: set[tuple] = set()
    for r in load(folder, "agent_records.json")["records"]:
        for value in cited_values(r["data"]):
            c = value["citation"]
            loc = c["location"]
            name = c["file_id"].removeprefix("file-")
            key = (name, c["passage"], value.get("text"), loc.get("start_page_number"))
            if loc["type"] != "page_location" or key in seen or name not in docs:
                continue
            seen.add(key)
            where = f"{folder.name}: {r['id']}: {c['passage']!r} in {name}"
            found = find_pdf_quote(
                (folder / name).read_bytes(),
                c["passage"],
                start_page_number=loc["start_page_number"],
                end_page_number=loc["end_page_number"],
                value_text=value.get("text"),
            )
            if found.match not in ("exact", "close"):
                problems.append(f"{where}: the finder says {found.match}")
                continue
            if value.get("text") and not found.value_found:
                problems.append(f"{where}: the value {value['text']!r} isn't found in it")
            if found.match != c["match"]:
                problems.append(f"{where}: found as {found.match}, cited as {c['match']}")
            spaced = " ".join(docs[name].text.split())
            in_text = spaced.count(c["passage"])
            if len(found.occurrences) > in_text:
                problems.append(
                    f"{where}: on the page {len(found.occurrences)} times, in its text {in_text}"
                )


def cited_values(obj) -> list[dict]:
    """Every cited value inside a record's data: a dict with its citation, and its
    text where it has one. A bare citation (a link's part, an answer's quote) counts."""
    found = []
    if isinstance(obj, dict):
        if isinstance(obj.get("citation"), dict):
            found.append(obj)
        elif "file_id" in obj and "location" in obj:
            found.append({"citation": obj})
        for v in obj.values():
            found += cited_values(v)
    elif isinstance(obj, list):
        for v in obj:
            found += cited_values(v)
    return found


def test_pdf_citations_are_found() -> None:
    """The app's quote finder finds every passage the agent records cite into a PDF."""
    g = gen()
    problems: list[str] = []
    for folder in (LARGER, SMALL):
        check_pdf_citations(folder, g[folder], problems)
    assert not problems, "\n".join(problems[:30])


def test_larger_sample() -> None:
    """The larger sample reaches closeout: its timeline starts with its award
    letter and runs past the start of its 90-day closeout window."""
    g = gen()[LARGER]
    final_end = max([g.end, *(new_end for _, new_end in g.extensions)])
    end = datetime.combine(final_end, datetime.min.time(), g.first_event_at().tzinfo)
    assert g.docs[0].name.startswith("award_letter.") and g.docs[0].at == g.first_event_at()
    assert g.last_event_at() > end, "never reaches closeout, past its end date"
    actions = load(LARGER, "user_actions.json")["actions"]
    assert any(a["action"] == "sign_off" for a in actions), "never signed off"


def test_highlights() -> None:
    """Each sample marks its highlights, each where its charge is on screen, and each
    scripted step that is a highlight's own carries its label. A blank label is refused."""
    import shutil
    import tempfile

    for folder, want in ((LARGER, LARGER_HIGHLIGHTS), (SMALL, SMALL_HIGHLIGHTS)):
        events = load(folder, "timeline.json")["events"]
        labels = {e["highlight"] for e in events if "highlight" in e}
        assert labels == want, (folder.name, labels ^ want)
        at = {e["highlight"]: e.get("file") or e["line_id"] for e in events if "highlight" in e}
        steps = {
            (a["action"], a.get("file")): a.get("highlight")
            for a in load(folder, "user_actions.json")["actions"]
        }
        assert {(k, v) for k, v in steps.items() if v} == HIGHLIGHT_STEPS[folder], folder.name
        for label, where in HIGHLIGHT_ON_LINE.items():
            if folder == LARGER:
                assert at[label] == where, (label, at[label])
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / SMALL.name
        shutil.copytree(SMALL, copy)
        timeline = load(copy, "timeline.json")
        timeline["events"][1]["highlight"] = "   "
        (copy / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
        problems: list[str] = []
        check_timeline(copy, copy, check_ledger(copy, problems), problems)
    assert any("highlight label can't be blank" in p for p in problems), problems


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
        test_suggestion_kinds_are_record_kinds,
        test_a_script_with_more_than_the_key_assumes_fails,
        test_agent_records_match_the_key,
        test_pdf_citations_are_found,
        test_larger_sample,
        test_highlights,
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
