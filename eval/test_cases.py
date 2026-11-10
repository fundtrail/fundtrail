"""Checks every eval case in eval/cases/ against docs/contracts.md.

Validates each answer key against the format in section 14, each ledger file
against section 13, and each case's arrival schedule (arrivals.json). Checks
that every file a key names exists, and that every expected text value in a
key appears in its file. Uses only the standard library, needs no API key and
never runs the agent.

Run it with `python eval/test_cases.py`, or with pytest.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

CASES_DIR = Path(__file__).resolve().parent / "cases"

# Files a case has that aren't evidence documents. A case's README holds
# notes on the key that section 14 has no field for.
CASE_META_FILES = {"answer_key.json", "arrivals.json", "ledger.csv", "README.md"}

# Section 14: the answer key's top-level fields.
KEY_FIELDS = {"case", "award_number", "records", "links", "budget_lines", "answers", "buckets"}

# Section 1: the record kinds the agent reads from documents, and the field
# paths each one can carry. `dated` is on every term. `notice` (an award
# notice's amendment and amounts) and `budget_line.category` follow the shapes
# agreed for the contract code (issue 14). The rate term's fields aren't
# settled, so a key can't name it yet.
TERM_KINDS = {"period_of_performance", "budget_line", "person", "approval_rule", "other_term", "notice"}
RECORD_FIELDS = {
    "period_of_performance": {"start", "end", "dated"},
    "notice": {"amendment_number", "amendment_type", "obligated_by_amendment", "obligated_to_date", "dated"},
    "budget_line": {"name", "category", "amount", "dated"},
    "person": {"name", "email", "role", "dated"},
    "approval_rule": {"applies_to", "approver", "channel", "dated"},
    "other_term": {"label", "statement", "dated"},
    "bill": {"total", "vendor", "dated", "description", "items[].description", "items[].amount"},
    "approval": {"approver_email", "covers", "approver_name", "approved_on", "channel"},
    "note": {"label", "statement"},
}
DATE_FIELDS = {"start", "end", "dated", "approved_on"}
MONEY_FIELDS = {"amount", "total", "items[].amount", "obligated_by_amendment", "obligated_to_date"}
# A label is the agent's own short name, not a value read from the file.
UNCITED_FIELDS = {"label"}
# NSF's standard categories and Other Direct Costs' six sub-lines, spelled as
# the contract code's BudgetCategory spells them. The sixth sub-line is
# other_direct_costs_other, so it can't be read as participant support's Other.
CATEGORIES = {
    "senior_personnel", "other_personnel", "fringe_benefits", "equipment", "travel",
    "participant_support", "other_direct_costs", "materials_and_supplies", "publication",
    "consultant_services", "computer_services", "subawards", "other_direct_costs_other",
}
ODC_SUBLINE_CATEGORIES = {
    "materials_and_supplies", "publication", "consultant_services",
    "computer_services", "subawards", "other_direct_costs_other",
}

QUESTIONS = {"allowable", "covers", "unusual_term", "flag"}
QUESTIONS_WITH_FILE = {"covers", "unusual_term"}
ANSWERS = {"supports", "contradicts", "unsure"}
BUCKETS = {"evidence_complete", "possible_conflict", "missing_evidence", "needs_human"}

# Section 13: ledger file columns.
LEDGER_REQUIRED = {"line_id", "transaction_date", "posting_date", "amount", "description", "account"}
LEDGER_OPTIONAL = {"vendor", "reference", "original_line_id"}

# domain.md, "Default checklists by account group": the starting table of
# Berkeley account ranges. A ledger account must start with one of these.
ACCOUNT_GROUP_PREFIXES = (
    "50", "51", "53", "538", "5742", "5721", "5722", "550", "553",
    "542", "5671", "5781", "5672", "564", "590",
)

# The arrival schedule: what can arrive, and what the accountant can do.
SOURCES = {"gmail", "drive", "upload"}
ACCOUNTANT_ACTIONS = {"confirm_terms"}

# domain.md, "What an NSF award notice contains": the sections, in order.
AWARD_LETTER_SECTIONS = [
    "RECIPIENT INFORMATION",
    "AMENDMENT INFORMATION",
    "AWARD INFORMATION",
    "FUNDING INFORMATION",
    "PROJECT PERSONNEL",
    "NSF CONTACT INFORMATION",
    "TERMS AND CONDITIONS",
    "BUDGET",
]

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
CENTS = re.compile(r"^-?\d+$")
DOLLARS = re.compile(r"^-?\d+(\.\d{1,2})?$")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]+")
ITEM_PATH = re.compile(r"^items\[(\d+)\]\.(description|amount)$")


def normalize(text: str) -> str:
    """Section 14 compares strings ignoring case and extra whitespace."""
    return " ".join(text.split()).casefold()


def parse_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def date_renderings(value: date) -> list[str]:
    return [
        value.isoformat(),
        f"{value:%B} {value.day}, {value.year}",
        f"{value:%m/%d/%Y}",
        f"{value.day} {value:%b} {value.year}",
    ]


MINUS = "\N{MINUS SIGN}"
HYPHEN_OR_EN_DASH = "-\N{EN DASH}"


def sign_marked(text: str, start: int, end: int) -> str:
    """How the text marks the sign of the amount at text[start:end], the digits
    right after a dollar sign. Follows the main coordinator's provisional sign
    ruling (call 31):

    - "negative": a hyphen or en dash attached to the amount, after a space, a
      bracket or the start ("-$450.00", "$-450.00"); a true minus, attached or
      spaced; a trailing minus or CR ("$450.00-", "$450.00 CR"). A dash between
      two amounts is a range, not a trailing minus ("$400-$500").
    - "either": a hyphen or en dash with a space before the amount ("- $450.00",
      "Year 2 - $50,000", "$400 - $500"), or brackets ("($450.00)"), which this
      check can't tell apart from brackets in a sentence.
    - "positive": no mark, an em dash, or a dash right after a digit or a letter
      ("$400-$500", "Year 2-$50,000").
    """
    after = text[end:]
    trailing_minus = after.startswith("-") and not (after[1:2] == "$" or after[1:2].isdigit())
    if trailing_minus or after.startswith(" cr") and not after[3:4].isalpha():
        return "negative"
    i = start - 1
    if i >= 0 and text[i] in HYPHEN_OR_EN_DASH + MINUS:  # "$-450.00"
        i -= 1
        return "negative" if i >= 0 and text[i] == "$" else "positive"
    if i < 0 or text[i] != "$":
        return "positive"
    i -= 1
    mark = text[i] if i >= 0 else ""
    before = text[i - 1] if i >= 1 else ""
    if mark == MINUS or (mark == " " and before == MINUS):
        return "negative"
    if mark and mark in HYPHEN_OR_EN_DASH:
        return "positive" if before.isalnum() else "negative"
    if mark == " " and before and before in HYPHEN_OR_EN_DASH:
        return "either"
    if mark == "(" and after.startswith(")"):
        return "either"
    return "positive"


def money_written(cents: int, text: str) -> bool:
    """True when the amount is written in text as a whole amount after a dollar
    sign, so $150 doesn't match inside $150,000 or $150.50, and its sign mark
    allows the amount's sign: a negative amount needs a mark that's negative or
    either, and a positive one a mark that's positive or either."""
    dollars, rest = divmod(abs(cents), 100)
    forms = [f"{dollars:,}.{rest:02d}"] + ([f"{dollars:,}"] if rest == 0 else [])
    want = "negative" if cents < 0 else "positive"
    for form in forms:
        for m in re.finditer(r"(?<![\d,.])" + re.escape(form) + r"(?![\d,]|\.\d)", text):
            j = m.start() - 1
            if j >= 0 and text[j] in HYPHEN_OR_EN_DASH + MINUS:
                j -= 1
            if j < 0 or text[j] != "$":
                continue
            if sign_marked(text, m.start(), m.end()) in (want, "either"):
                return True
    return False


def budget_parents(letter_text: str) -> dict[str, str]:
    """Maps each sub-line the award letter's budget prints to its line.

    A line starts with its letter ("G. Other Direct Costs"). A sub-line is
    indented under it. Amounts are dropped from the names.
    """
    parents: dict[str, str] = {}
    _, _, budget = letter_text.partition("\nBUDGET\n")
    current = None
    for raw in budget.splitlines():
        name = re.sub(r"\s+\$[\d,.]+\s*$", "", raw).strip()
        if not name or "$" not in raw:
            continue
        line = re.match(r"^[A-M]\.\s+(.+)$", name)
        if line and not raw[:1].isspace():
            current = line.group(1)
        elif raw[:1].isspace() and current is not None:
            parents[name] = current
    return parents


def field_type(path: str) -> str:
    """Collapse items[3].amount to items[].amount for the field tables."""
    match = ITEM_PATH.match(path)
    return f"items[].{match.group(2)}" if match else path


def case_dirs() -> list[Path]:
    return sorted(p for p in CASES_DIR.iterdir() if p.is_dir())


def load_json(path: Path, problems: list[str]) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"{path.name}: can't be read as JSON ({exc})")
        return None
    if not isinstance(data, dict):
        problems.append(f"{path.name}: must be a JSON object")
        return None
    return data


def check_ledger(case: Path, problems: list[str]) -> dict[str, dict[str, str]]:
    path = case / "ledger.csv"
    if not path.is_file():
        problems.append("ledger.csv is missing")
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = set(reader.fieldnames or [])
        rows = list(reader)
    if missing := LEDGER_REQUIRED - header:
        problems.append(f"ledger.csv: missing columns {sorted(missing)}")
    if unknown := header - LEDGER_REQUIRED - LEDGER_OPTIONAL:
        problems.append(f"ledger.csv: unknown columns {sorted(unknown)}")
    lines: dict[str, dict[str, str]] = {}
    for n, row in enumerate(rows, start=2):
        where = f"ledger.csv row {n}"
        line_id = (row.get("line_id") or "").strip()
        if not line_id:
            problems.append(f"{where}: empty line_id")
            continue
        if line_id in lines:
            problems.append(f"{where}: line_id {line_id} appears twice")
        for col in LEDGER_REQUIRED:
            if not (row.get(col) or "").strip():
                problems.append(f"{where}: {col} is empty")
        dates = {}
        for col in ("transaction_date", "posting_date"):
            value = row.get(col) or ""
            if not ISO_DATE.match(value):
                problems.append(f"{where}: {col} {value!r} isn't YYYY-MM-DD")
                continue
            try:
                dates[col] = date.fromisoformat(value)
            except ValueError:
                problems.append(f"{where}: {col} {value!r} isn't a real date")
        if len(dates) == 2 and dates["posting_date"] < dates["transaction_date"]:
            problems.append(f"{where}: posted before its transaction date")
        if not DOLLARS.match(row.get("amount") or ""):
            problems.append(f"{where}: amount {row.get('amount')!r} isn't dollars with up to two decimals")
        code = (row.get("account") or "").split(" ")[0]
        if not (re.fullmatch(r"5\d{4}", code) and code.startswith(ACCOUNT_GROUP_PREFIXES)):
            problems.append(f"{where}: account {row.get('account')!r} isn't in a group from domain.md's starting table")
        lines[line_id] = row
    return lines


def cents_of(row: dict[str, str]) -> int:
    return round(float(row["amount"]) * 100)


def check_record(rec: object, i: int, case: Path, problems: list[str]) -> None:
    where = f"answer_key.json records[{i}]"
    if not isinstance(rec, dict) or set(rec) != {"kind", "file", "fields"}:
        problems.append(f"{where}: must have exactly kind, file and fields")
        return
    kind, name, fields = rec["kind"], rec["file"], rec["fields"]
    if kind not in RECORD_FIELDS:
        problems.append(f"{where}: kind {kind!r} isn't a record kind the agent reads from a document")
        return
    path = case / name if isinstance(name, str) else None
    if path is None or name in CASE_META_FILES or not path.is_file():
        problems.append(f"{where}: file {name!r} isn't an evidence file in the case")
        return
    if not isinstance(fields, dict):
        problems.append(f"{where}: fields must be an object")
        return
    text = normalize(path.read_text(encoding="utf-8"))
    for field, value in fields.items():
        ftype = field_type(field)
        if ftype not in RECORD_FIELDS[kind]:
            problems.append(f"{where}: {kind} has no field {field!r}")
            continue
        if not isinstance(value, str):
            problems.append(f"{where}: {field} must be a string")
            continue
        if ftype == "category":
            if value not in CATEGORIES:
                problems.append(f"{where}: category {value!r} isn't one of {sorted(CATEGORIES)}")
        elif ftype in DATE_FIELDS:
            try:
                parsed = date.fromisoformat(value) if ISO_DATE.match(value) else None
            except ValueError:
                parsed = None
            if parsed is None:
                problems.append(f"{where}: {field} {value!r} isn't a YYYY-MM-DD date")
            elif not any(normalize(r) in text for r in date_renderings(parsed)):
                problems.append(f"{where}: {field} {value} isn't written in {name}")
        elif ftype in MONEY_FIELDS:
            if not CENTS.match(value):
                problems.append(f"{where}: {field} {value!r} isn't a whole number of cents")
            elif not money_written(int(value), text):
                problems.append(f"{where}: {field} {value} cents isn't written in {name}")
        elif ftype not in UNCITED_FIELDS and normalize(value) not in text:
            problems.append(f"{where}: {field} {value!r} doesn't appear in {name}")
    if kind in TERM_KINDS and "dated" not in fields:
        problems.append(f"{where}: a term should give its dated")


def check_key(case: Path, lines: dict[str, dict[str, str]], arrivals: dict[str, datetime],
              problems: list[str], key: dict | None = None) -> None:
    if key is None:
        key = load_json(case / "answer_key.json", problems)
    if key is None:
        return
    if set(key) != KEY_FIELDS:
        problems.append(f"answer_key.json: fields must be exactly {sorted(KEY_FIELDS)}")
        return
    if key["case"] != case.name:
        problems.append(f"answer_key.json: case {key['case']!r} doesn't match its folder")
    award = key["award_number"]
    if not (isinstance(award, str) and award.startswith("SYN-")):
        problems.append("answer_key.json: award_number must start with SYN-")
    letters = list(case.glob("award_letter.*"))
    if len(letters) != 1:
        problems.append("the case needs exactly one award_letter file")
    elif isinstance(award, str) and award not in letters[0].read_text(encoding="utf-8"):
        problems.append(f"{letters[0].name} doesn't carry the award number {award}")
    for part in ("records", "links", "budget_lines", "answers", "buckets"):
        if not isinstance(key[part], list):
            problems.append(f"answer_key.json: {part} must be a list")
            return

    kinds_by_file: dict[str, set[str]] = {}
    bill_totals: dict[str, int] = {}
    budget_names: set[str] = set()
    for i, rec in enumerate(key["records"]):
        check_record(rec, i, case, problems)
        if isinstance(rec, dict) and isinstance(rec.get("fields"), dict):
            kinds_by_file.setdefault(rec.get("file"), set()).add(rec.get("kind"))
            fields = rec["fields"]
            if rec.get("kind") == "bill" and CENTS.match(fields.get("total", "")):
                bill_totals[rec["file"]] = int(fields["total"])
            if rec.get("kind") == "budget_line" and "name" in fields:
                budget_names.add(fields["name"])

    # A sub-line's category is its line's category, except inside Other
    # Direct Costs, whose six sub-lines are categories of their own.
    categories = {
        r["fields"]["name"]: r["fields"].get("category")
        for r in key["records"]
        if isinstance(r, dict) and r.get("kind") == "budget_line"
        and isinstance(r.get("fields"), dict) and "name" in r["fields"]
    }
    if len(letters) == 1:
        parents = budget_parents(letters[0].read_text(encoding="utf-8"))
        for name, category in categories.items():
            parent = parents.get(name)
            if parent is None:
                continue
            parent_category = categories.get(parent)
            if parent_category is None:
                problems.append(f"answer_key.json: sub-line {name!r} has no budget_line for its line {parent!r}")
            elif parent_category == "other_direct_costs":
                if category not in ODC_SUBLINE_CATEGORIES:
                    problems.append(
                        f"answer_key.json: sub-line {name!r} of Other Direct Costs needs one of "
                        f"{sorted(ODC_SUBLINE_CATEGORIES)}, not {category!r}")
            elif category != parent_category:
                problems.append(
                    f"answer_key.json: sub-line {name!r} has category {category!r}, "
                    f"but its line {parent!r} is {parent_category!r}")

    linked_lines: set[str] = set()
    files_by_line: dict[str, set[str]] = {}
    seen_links: set[tuple[str, str]] = set()
    used_by_bill: dict[str, int] = {}
    for i, link in enumerate(key["links"]):
        where = f"answer_key.json links[{i}]"
        if not isinstance(link, dict) or not {"file", "line_id"} <= set(link) <= {"file", "line_id", "amount_cents"}:
            problems.append(f"{where}: must have file and line_id, and may have amount_cents")
            continue
        name, line_id = link["file"], link["line_id"]
        if name not in kinds_by_file:
            problems.append(f"{where}: no expected record is read from {name!r}")
        if line_id not in lines:
            problems.append(f"{where}: line_id {line_id!r} isn't in ledger.csv")
        if (name, line_id) in seen_links:
            problems.append(f"{where}: the same link appears twice")
        seen_links.add((name, line_id))
        linked_lines.add(line_id)
        files_by_line.setdefault(line_id, set()).add(name)
        is_bill = "bill" in kinds_by_file.get(name, set())
        amount = link.get("amount_cents")
        if is_bill and not (isinstance(amount, int) and not isinstance(amount, bool)):
            problems.append(f"{where}: a link to a bill needs an integer amount_cents")
        elif not is_bill and "amount_cents" in link:
            problems.append(f"{where}: only a link to a bill carries amount_cents")
        elif is_bill:
            # Call 38, A1: a link's amount has the same sign as its bill's total.
            total = bill_totals.get(name)
            if total is not None and amount * total < 0:
                problems.append(f"{where}: links {amount} cents of {name}, whose total is {total}")
            used_by_bill[name] = used_by_bill.get(name, 0) + amount
            if line_id in lines and abs(amount) > abs(cents_of(lines[line_id])):
                problems.append(f"{where}: links more than the charge's amount")
    for name, used in used_by_bill.items():
        # Added with their signs, a bill's links reach no further than its total.
        total = bill_totals.get(name)
        if total is not None and (abs(used) > abs(total) or used * total < 0):
            problems.append(f"answer_key.json: links to {name} add up to more than its total")

    assigned: set[str] = set()
    for i, item in enumerate(key["budget_lines"]):
        where = f"answer_key.json budget_lines[{i}]"
        if not isinstance(item, dict) or set(item) != {"line_id", "budget_line"}:
            problems.append(f"{where}: must have exactly line_id and budget_line")
            continue
        if item["line_id"] not in lines:
            problems.append(f"{where}: line_id {item['line_id']!r} isn't in ledger.csv")
        if item["line_id"] in assigned:
            problems.append(f"{where}: a charge has at most one budget line")
        assigned.add(item["line_id"])
        if item["budget_line"] not in budget_names:
            problems.append(f"{where}: {item['budget_line']!r} isn't a budget_line record in the key")

    for i, ans in enumerate(key["answers"]):
        where = f"answer_key.json answers[{i}]"
        if not isinstance(ans, dict) or not {"line_id", "question", "answer"} <= set(ans) <= {
            "line_id", "question", "answer", "about_file"}:
            problems.append(f"{where}: must have line_id, question and answer, and may have about_file")
            continue
        if ans["line_id"] not in lines:
            problems.append(f"{where}: line_id {ans['line_id']!r} isn't in ledger.csv")
        if ans["question"] not in QUESTIONS:
            problems.append(f"{where}: question {ans['question']!r} isn't one of {sorted(QUESTIONS)}")
        if ans["answer"] not in ANSWERS:
            problems.append(f"{where}: answer {ans['answer']!r} isn't one of {sorted(ANSWERS)}")
        if ans["question"] in QUESTIONS_WITH_FILE:
            if not (case / str(ans.get("about_file"))).is_file():
                problems.append(f"{where}: {ans['question']} needs an about_file that exists")
        elif "about_file" in ans:
            problems.append(f"{where}: only covers and unusual_term take about_file")
        # contracts.md section 4: Allowable is asked when evidence is linked.
        if ans["question"] == "allowable" and ans["line_id"] not in linked_lines:
            problems.append(f"{where}: Allowable is only asked for a charge with evidence linked")

    confirmed = [t for k, t in arrivals.items() if k.startswith("confirm_terms:")]
    for i, item in enumerate(key["buckets"]):
        where = f"answer_key.json buckets[{i}]"
        if not isinstance(item, dict) or set(item) != {"line_id", "at", "bucket"}:
            problems.append(f"{where}: must have exactly line_id, at and bucket")
            continue
        if item["bucket"] not in BUCKETS:
            problems.append(f"{where}: bucket {item['bucket']!r} isn't one of {sorted(BUCKETS)}")
        if not ISO_TIME.match(str(item["at"])):
            problems.append(f"{where}: at {item['at']!r} isn't a UTC time like 2026-01-31T12:00:00Z")
            continue
        at = parse_time(item["at"])
        arrived = arrivals.get(f"line:{item['line_id']}")
        if arrived is None:
            problems.append(f"{where}: line_id {item['line_id']!r} never arrives")
        elif at <= arrived:
            problems.append(f"{where}: at must come after the line arrives")
        if not confirmed or at <= min(confirmed):
            problems.append(f"{where}: at must come after the accountant confirms the terms")
        # A charge can't be complete before the evidence linked to it is on file.
        # A credit linked later, with the opposite sign from the charge, only
        # takes evidence away, so the charge can be complete before it arrives.
        if item["bucket"] == "evidence_complete":
            charge = cents_of(lines[item["line_id"]]) if item["line_id"] in lines else 0
            credits = {
                link["file"] for link in key["links"]
                if link["line_id"] == item["line_id"]
                and isinstance(link.get("amount_cents"), int) and link["amount_cents"] * charge < 0
            }
            for name in sorted(files_by_line.get(item["line_id"], set()) - credits):
                file_at = arrivals.get(f"file:{name}")
                if file_at is None or at <= file_at:
                    problems.append(f"{where}: evidence_complete must come after {name} arrives")
            # The bills on file then, added with their signs, can't come to more
            # than the charge. Once a credit is on file they must come to exactly
            # the charge: a credit leaves the charge short unless something else
            # makes up the difference. Without a credit they may come to less,
            # because an item from a rate, such as a trip's per diem, carries an
            # amount the key can't express.
            arrived = [
                link for link in key["links"]
                if link["line_id"] == item["line_id"] and isinstance(link.get("amount_cents"), int)
                and arrivals.get(f"file:{link['file']}", at) < at
            ]
            if arrived:
                signed = sum(link["amount_cents"] for link in arrived)
                credit_on_file = any(link["file"] in credits for link in arrived)
                if abs(signed) > abs(charge) or signed * charge < 0 or (
                        credit_on_file and signed != charge):
                    problems.append(f"{where}: evidence_complete, but the bills on file add up "
                                    f"to {signed} cents against the charge's {charge}")


def check_arrivals(case: Path, lines: dict[str, dict[str, str]], problems: list[str]) -> dict[str, datetime]:
    """Returns when each line and file arrives, and when terms are confirmed."""
    out: dict[str, datetime] = {}
    sched = load_json(case / "arrivals.json", problems)
    if sched is None:
        return out
    if set(sched) != {"case", "events"} or not isinstance(sched["events"], list):
        problems.append("arrivals.json: must have exactly case and an events list")
        return out
    if sched["case"] != case.name:
        problems.append(f"arrivals.json: case {sched['case']!r} doesn't match its folder")
    documents = {p.name for p in case.iterdir() if p.is_file() and p.name not in CASE_META_FILES}
    file_count: dict[str, int] = {}
    line_count: dict[str, int] = {}
    last: datetime | None = None
    for i, ev in enumerate(sched["events"]):
        where = f"arrivals.json events[{i}]"
        if not isinstance(ev, dict) or not ISO_TIME.match(str(ev.get("at"))):
            problems.append(f"{where}: needs an at like 2026-01-31T12:00:00Z")
            continue
        at = parse_time(ev["at"])
        if last is not None and at < last:
            problems.append(f"{where}: events must be in time order")
        last = at
        kind = ev.get("kind")
        if kind == "file":
            allowed = {"at", "kind", "file", "source", "sender", "note"}
            name = ev.get("file")
            if name not in documents:
                problems.append(f"{where}: file {name!r} isn't a document in the case")
            file_count[name] = file_count.get(name, 0) + 1
            out[f"file:{name}"] = at
            if ev.get("source") not in SOURCES:
                problems.append(f"{where}: source must be one of {sorted(SOURCES)}")
            if ev.get("source") == "gmail":
                if not str(ev.get("sender", "")).endswith(".example"):
                    problems.append(f"{where}: a gmail arrival needs a sender at a .example address")
            elif "sender" in ev:
                problems.append(f"{where}: only a gmail arrival has a sender")
        elif kind == "ledger_line":
            allowed = {"at", "kind", "line_id", "note"}
            line_id = ev.get("line_id")
            line_count[line_id] = line_count.get(line_id, 0) + 1
            out[f"line:{line_id}"] = at
            if line_id not in lines:
                problems.append(f"{where}: line_id {line_id!r} isn't in ledger.csv")
            elif at < parse_time(f"{lines[line_id]['posting_date']}T00:00:00Z"):
                problems.append(f"{where}: a ledger line can't arrive before its posting date")
        elif kind == "accountant":
            allowed = {"at", "kind", "action", "file", "note"}
            if ev.get("action") not in ACCOUNTANT_ACTIONS:
                problems.append(f"{where}: action must be one of {sorted(ACCOUNTANT_ACTIONS)}")
            arrived = out.get(f"file:{ev.get('file')}")
            if arrived is None or arrived >= at:
                problems.append(f"{where}: the accountant acts on a file that has already arrived")
            out[f"{ev.get('action')}:{ev.get('file')}"] = at
        else:
            problems.append(f"{where}: kind must be file, ledger_line or accountant")
            continue
        if unknown := set(ev) - allowed:
            problems.append(f"{where}: unknown fields {sorted(unknown)}")
    for name in sorted(documents):
        if file_count.get(name) != 1:
            problems.append(f"arrivals.json: {name} must arrive exactly once")
    for line_id in sorted(lines):
        if line_count.get(line_id) != 1:
            problems.append(f"arrivals.json: {line_id} must arrive exactly once")
    check_line_arrivals(lines, out, problems)
    return out


def check_line_arrivals(lines: dict[str, dict[str, str]], out: dict[str, datetime],
                        problems: list[str]) -> None:
    """Decision 0023: a ledger line arrives at the later of 00:00 UTC on its
    posting date and the workspace's "now" when the ledger is uploaded (the
    contract's LedgerRow.arrival(now)). A seeded line arrives on its posting
    date. A line that arrives later than that came with the upload, so every
    such line shares the upload's time, and no line posting before it can
    arrive on its own posting date."""
    posted = {
        line_id: parse_time(f"{row['posting_date']}T00:00:00Z")
        for line_id, row in lines.items()
        if ISO_DATE.match(row.get("posting_date") or "")
    }
    arrived = {line_id: out[f"line:{line_id}"] for line_id in posted if f"line:{line_id}" in out}
    uploads = {at for line_id, at in arrived.items() if at > posted[line_id]}
    if len(uploads) > 1:
        problems.append("arrivals.json: lines arriving after their posting date must share "
                        "the ledger's one upload time")
        return
    upload = next(iter(uploads), None)
    for line_id, at in sorted(arrived.items()):
        want = max(posted[line_id], upload) if upload else posted[line_id]
        if at != want:
            problems.append(f"arrivals.json: {line_id} arrives at the later of its posting "
                            "date and the ledger's upload (decision 0023)")


def check_documents(case: Path, problems: list[str]) -> None:
    for path in sorted(case.iterdir()):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for address in EMAIL.findall(text):
            if not address.lower().endswith(".example"):
                problems.append(f"{path.name}: email address {address} isn't at a .example domain")
        for dash, dash_name in (("\N{EM DASH}", "an em dash"), ("\N{EN DASH}", "an en dash")):
            if dash in text:
                problems.append(f"{path.name}: has {dash_name}")
    for letter in case.glob("award_letter.*"):
        text = letter.read_text(encoding="utf-8")
        positions = [text.find(s) for s in AWARD_LETTER_SECTIONS]
        if -1 in positions or positions != sorted(positions):
            problems.append(f"{letter.name}: needs the award notice's sections, in order: {AWARD_LETTER_SECTIONS}")


def check_case(case: Path) -> list[str]:
    problems: list[str] = []
    lines = check_ledger(case, problems)
    arrivals = check_arrivals(case, lines, problems)
    check_key(case, lines, arrivals, problems)
    check_documents(case, problems)
    return [f"{case.name}: {p}" for p in problems]


def test_there_are_cases() -> None:
    assert case_dirs(), f"no cases in {CASES_DIR}"


def test_every_case_is_valid() -> None:
    problems = [p for case in case_dirs() for p in check_case(case)]
    assert not problems, "\n".join(problems)


def test_sign_marks() -> None:
    """The sign ruling's examples, read as the check reads them."""
    cases = [
        ("Credit - $450.00", 45000, True), ("Credit - $450.00", -45000, True),
        ("Airfare \N{EN DASH} $450.00", 45000, True),
        ("Year 2 - $50,000", 5000000, True), ("$400-$500", 50000, True),
        ("$400-$500", -50000, False), ("Year 2-$50,000", 5000000, True),
        ("Refund -$450.00", -45000, True), ("Refund -$450.00", 45000, False),
        ("$-450.00", -45000, True), ("$-450.00", 45000, False),
        ("\N{MINUS SIGN}$450.00", -45000, True), ("\N{MINUS SIGN} $450.00", 45000, False),
        ("$450.00-", -45000, True), ("$450.00-", 45000, False),
        ("$400-$500", 40000, True), ("$400-$500", -40000, False),
        ("$450.00-$500.00", 45000, True), ("$450.00-$500.00", -45000, False),
        ("$450.00 cr", -45000, True), ("$450.00 cr", 45000, False),
        ("fee ($450.00) paid", -45000, True), ("fee ($450.00) paid", 45000, True),
        ("total $450.00", 45000, True), ("total $450.00", -45000, False),
        ("total \N{EM DASH} $450.00", -45000, False), ("$1,450.00", 45000, False),
    ]
    wrong = [(t, c) for t, c, ok in cases if money_written(c, normalize(t)) != ok]
    assert not wrong, wrong


def credit_memo_case() -> tuple[Path, dict, dict, dict]:
    case = CASES_DIR / "credit-memo-spaced-dash"
    problems: list[str] = []
    lines = check_ledger(case, problems)
    arrivals = check_arrivals(case, lines, problems)
    key = json.loads((case / "answer_key.json").read_text(encoding="utf-8"))
    return case, lines, arrivals, key


def test_credit_memo_case_reads_the_memo_as_negative() -> None:
    """The memo's spaced dash reads as either sign, so its text can't hold the key
    to the call 38 ruling. A key that encoded the whole trap, reading the memo as
    +45000 and linking it to L-8102, would otherwise pass."""
    _, _, _, key = credit_memo_case()
    memo = [r for r in key["records"] if r["file"] == "credit_memo_20417.eml"]
    assert [r["fields"]["total"] for r in memo] == ["-45000"], memo
    links = [lk for lk in key["links"] if lk["file"] == "credit_memo_20417.eml"]
    assert links == [{"file": "credit_memo_20417.eml", "line_id": "L-8101", "amount_cents": -45000}]


def test_credit_on_file_keeps_its_charge_from_complete() -> None:
    """L-8101 marked Evidence complete after the memo arrives fails: its bills
    then come to $750.00 of $1,200.00."""
    case, lines, arrivals, key = credit_memo_case()
    for b in key["buckets"]:
        if b["line_id"] == "L-8101" and b["at"] == "2026-03-24T12:00:00Z":
            b["bucket"] = "evidence_complete"
    problems: list[str] = []
    check_key(case, lines, arrivals, problems, key)
    assert any("bills on file add up to 75000" in p for p in problems), problems


def test_link_sign_must_match_its_bill() -> None:
    """Linking the credit memo to L-8102 for +45000, the false clear the case
    exists for, fails the check."""
    case, lines, arrivals, key = credit_memo_case()
    problems: list[str] = []
    key["links"].append({"file": "credit_memo_20417.eml", "line_id": "L-8102", "amount_cents": 45000})
    check_key(case, lines, arrivals, problems, key)
    assert any("credit_memo_20417.eml" in p for p in problems), problems


if __name__ == "__main__":
    cases = case_dirs()
    all_problems = [p for case in cases for p in check_case(case)]
    for p in all_problems:
        print(p)
    print(f"{len(cases)} cases checked, {len(all_problems)} problems")
    sys.exit(1 if all_problems else 0)
