"""The sample grant (docs/contracts.md section 15) fits the contracts.

What the tests check: that the sample grant fits the contracts, that every
passage is copied exactly from its document, that every record passes the
write check when replayed in order, that the sums balance, that the ledger file
matches the charges, and that the answer key scores all right against the
sample grant's own agent records.
"""

import csv
import hashlib
import re
from datetime import datetime
from decimal import Decimal

from app.contracts.fixtures import (
    ANSWER_KEY_FILE,
    DOCUMENTS_DIR,
    GOLDEN_DIR,
    LEDGER_FILE,
    SAMPLE_GRANT_FILE,
    build_sample,
    load_sample_answer_key,
    load_sample_grant,
)
from app.contracts.records import (
    TERM_KINDS,
    Bill,
    BudgetAssignment,
    BudgetLine,
    CharLocation,
    CitedDate,
    CitedMoney,
    Judgment,
    Link,
    Notice,
    Record,
    RecordKind,
    citations,
    cited_values,
)
from app.contracts.rules import RecordState, check_new_record

SAMPLE = load_sample_grant()
KEY = load_sample_answer_key()
NAMES = {f.id: f.name for f in SAMPLE.files}
LINES = {c.id: c.ledger_line_id for c in SAMPLE.charges}


def test_the_json_is_what_the_builder_writes():
    assert SAMPLE_GRANT_FILE.read_text(encoding="utf-8") == build_sample.dumps(
        build_sample.sample_grant()
    )
    assert ANSWER_KEY_FILE.read_text(encoding="utf-8") == build_sample.dumps(
        build_sample.answer_key()
    )


def test_everything_is_synthetic():
    assert SAMPLE.grant.award_number == KEY.award_number == "SYN-2300117"
    text = "\n".join(p.read_text(encoding="utf-8") for p in GOLDEN_DIR.rglob("*") if p.is_file())
    domains = re.findall(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)", text)
    assert domains and all(d.endswith(".example") for d in domains)
    for f in SAMPLE.files:
        assert "SYNTHETIC DEMO DOCUMENT" in SAMPLE.document(f.id)


def test_the_award_letter_is_laid_out_like_an_nsf_award_notice():
    letter = (DOCUMENTS_DIR / "award_letter.txt").read_text(encoding="utf-8")
    sections = [
        "RECIPIENT INFORMATION",
        "AMENDMENT INFORMATION",
        "AWARD INFORMATION",
        "FUNDING INFORMATION",
        "PROJECT PERSONNEL",
        "NSF CONTACT INFORMATION",
        "GENERAL TERMS AND CONDITIONS",
        "BUDGET",
    ]
    positions = [letter.index(f"\n{s}\n") for s in sections]
    assert positions == sorted(positions)


def test_files_match_their_documents():
    assert sorted(NAMES.values()) == sorted(p.name for p in DOCUMENTS_DIR.iterdir())
    for f in SAMPLE.files:
        assert hashlib.sha256((DOCUMENTS_DIR / f.name).read_bytes()).hexdigest() == f.sha256
        assert (f.workspace_id, f.grant_id) == (SAMPLE.workspace.id, SAMPLE.grant.id)


def test_every_passage_is_copied_exactly_from_its_document():
    count = 0
    for r in SAMPLE.records:
        for c in citations(r.data):
            assert isinstance(c.location, CharLocation)
            text = SAMPLE.document(c.file_id)
            assert text[c.location.start_char_index : c.location.end_char_index] == c.passage
            count += 1
        for path, v in cited_values(r.data):
            assert v.citation and v.text and v.text in (v.citation.passage or ""), (r.id, path)
            if isinstance(v, CitedDate):
                assert datetime.strptime(v.text, "%B %d, %Y").date() == v.value
            elif isinstance(v, CitedMoney):
                assert int(Decimal(v.text.lstrip("$").replace(",", "")) * 100) == v.value
            else:
                assert v.text == v.value
    assert count > 40


def test_every_record_passes_the_write_check_replayed_in_order():
    written: list[Record] = []
    for r in SAMPLE.records:
        assert (r.workspace_id, r.grant_id) == (SAMPLE.workspace.id, SAMPLE.grant.id)
        charges = [c for c in SAMPLE.charges if c.arrived_at <= r.written_at]
        files = [f for f in SAMPLE.files if f.arrived_at <= r.written_at]
        assert (
            check_new_record(r, written, charges, files, default_items=SAMPLE.sample_default_items)
            == []
        ), r.id
        written.append(r)


def test_the_award_letter_gives_ten_terms_and_the_accountant_confirms_them():
    letter = next(f.id for f in SAMPLE.files if f.name == "award_letter.txt")
    terms = [
        r
        for r in SAMPLE.records
        if r.kind in TERM_KINDS and letter in {c.file_id for c in citations(r.data)}
    ]
    assert len(terms) == 10
    kinds = sorted(t.kind for t in terms)
    assert kinds.count(RecordKind.BUDGET_LINE) == 4 and kinds.count(RecordKind.PERSON) == 3
    state = RecordState(SAMPLE.records, SAMPLE.files)
    assert all(state.is_current(t.id) for t in terms)
    assert state.waiting() == []


def test_the_extension_waits_until_the_accountant_confirms_it():
    extension = next(r for r in SAMPLE.records if r.id == "rec-period-extension")
    before = [r for r in SAMPLE.records if r.written_at <= extension.written_at]
    state = RecordState(before, SAMPLE.files)
    assert [r.id for r in state.waiting()] == [extension.id]
    assert state.is_current("rec-period")  # the old end date stays in force
    after = RecordState(SAMPLE.records, SAMPLE.files)
    assert after.is_current(extension.id) and after.is_current(
        "rec-period"
    )  # an amendment isn't a correction


def test_the_sums_balance():
    state = RecordState(SAMPLE.records, SAMPLE.files)
    current = state.current()
    links = [r.data for r in current if isinstance(r.data, Link)]
    bills = {r.id: r.data for r in current if isinstance(r.data, Bill)}
    for bill_id, b in bills.items():  # per bill: its links add up to at most its total
        assert (
            sum(link.amount_cents or 0 for link in links if link.record_id == bill_id)
            <= b.total.value
        )
    for charge in SAMPLE.charges:
        items = SAMPLE.sample_default_items(charge, current)
        assert len(items) == 1
        for item in items:  # per item that carries an amount: its bills add up to it
            filled = [
                link
                for link in links
                if link.charge_id == charge.id and link.default_item == item.key
            ]
            assert sum(link.amount_cents or 0 for link in filled) == item.amount_cents
        # per charge: the amounts on its checklist add up to the charge
        assert sum(item.amount_cents or 0 for item in items) == charge.amount_cents


def test_spending_is_under_the_awards_limit():
    notice = next(r.data for r in SAMPLE.records if isinstance(r.data, Notice))
    assert notice.obligated_to_date is not None
    assert sum(c.amount_cents for c in SAMPLE.charges) == 342000 < notice.obligated_to_date.value


def test_the_ledger_file_matches_the_charges():
    from app.contracts.charges import LedgerRow

    with LEDGER_FILE.open(newline="", encoding="utf-8") as f:
        rows = [
            LedgerRow.model_validate({k: v or None for k, v in row.items()})
            for row in csv.DictReader(f)
        ]
    assert len(rows) == len(SAMPLE.charges)
    for row, charge in zip(rows, SAMPLE.charges, strict=True):
        assert (
            row.to_charge(id=charge.id, workspace_id=charge.workspace_id, grant_id=charge.grant_id)
            == charge
        )


def norm(value: object) -> str:
    return " ".join(str(value).split()).casefold()


def flat_values(r: Record) -> dict[str, str]:
    return {path: str(v.value) for path, v in cited_values(r.data)}


def test_the_answer_key_scores_all_right():
    """Scored with the match rules in contracts.md section 14: all right, none wrong or missing."""
    state = RecordState(SAMPLE.records, SAMPLE.files)
    agent = [r for r in state.current() if r.author == "agent"]
    by_id = state.by_id

    def file_of(r: Record) -> str:
        return NAMES[next(c.file_id for c in citations(r.data))]

    facts = [
        r
        for r in agent
        if r.kind in TERM_KINDS or r.kind in (RecordKind.BILL, RecordKind.APPROVAL, RecordKind.NOTE)
    ]
    for expected in KEY.records:
        match = next(
            r
            for r in facts
            if r.kind == expected.kind
            and file_of(r) == expected.file
            and all(norm(flat_values(r).get(k)) == norm(v) for k, v in expected.fields.items())
        )
        facts.remove(match)
    assert facts == []  # no wrong records

    links = [
        (file_of(by_id[r.data.record_id]), LINES[r.data.charge_id], r.data.amount_cents)
        for r in agent
        if isinstance(r.data, Link)
    ]
    assert sorted(links) == sorted((e.file, e.line_id, e.amount_cents) for e in KEY.links)

    budget_lines: list[tuple[str, str]] = []
    for r in agent:
        if isinstance(r.data, BudgetAssignment):
            line = by_id[r.data.record_id].data
            assert isinstance(line, BudgetLine)
            budget_lines.append((LINES[r.data.charge_id], line.name.value))
    assert sorted(budget_lines) == sorted((e.line_id, e.budget_line) for e in KEY.budget_lines)

    answers = [
        (LINES[r.data.charge_id or ""], r.data.question, r.data.answer)
        for r in agent
        if isinstance(r.data, Judgment)
    ]
    assert sorted(answers) == sorted((e.line_id, e.question, e.answer) for e in KEY.answers)


def test_expected_buckets_follow_arrivals():
    arrived = {c.ledger_line_id: c.arrived_at for c in SAMPLE.charges}
    assert SAMPLE.workspace.clock_now is not None
    for b in KEY.buckets:
        assert arrived[b.line_id] <= b.at <= SAMPLE.workspace.clock_now
