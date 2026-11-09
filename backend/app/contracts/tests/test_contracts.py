"""The golden fixture validates against the contracts, and the record rules hold.

Run from backend/: python -m pytest app/contracts
"""

import csv
import hashlib
import re
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from app.contracts import (
    TERM_KINDS,
    Author,
    Bucket,
    Charge,
    ChargeStatus,
    ChecksInput,
    Citation,
    Cited,
    CitedDate,
    CitedMoney,
    ContentBlockLocation,
    Judgment,
    LedgerRow,
    Link,
    Reason,
    Record,
    api,
    check_new_record,
    cited_values,
    current_records,
    effective_records,
    run_checks,
    waiting_records,
)
from app.contracts.fixtures import GOLDEN_DIR, GOLDEN_DOCUMENTS, GOLDEN_LEDGER, load_golden, load_golden_answer_key

FIXTURE = load_golden()
KEY = load_golden_answer_key()
NOW = datetime(2026, 4, 10, 17, tzinfo=UTC)
NAMES = {f.id: f.name for f in FIXTURE.evidence}
LINES = {c.id: c.ledger_line_id for c in FIXTURE.charges}


def blocks(name: str) -> list[str]:
    """One block per paragraph, the way the agent sends text to the model."""
    return [p.strip() for p in (GOLDEN_DOCUMENTS / name).read_text().split("\n\n") if p.strip()]


def all_citations(record: Record) -> list[Citation]:
    found = [v.citation for _, v in cited_values(record.data) if v.citation]
    if isinstance(record.data, Link) and record.data.part:
        found.append(record.data.part)
    if isinstance(record.data, Judgment):
        found += record.data.quotes
    return found


def parse(cited: Cited, text: str):
    if isinstance(cited, CitedDate):
        return datetime.strptime(text, "%B %d, %Y").date()
    if isinstance(cited, CitedMoney):
        return int(Decimal(text.lstrip("$").replace(",", "")) * 100)
    return text


# The golden fixture


def test_fixture_is_synthetic():
    assert (FIXTURE.grant.award_number or "").startswith("SYN-")
    text = "\n".join(p.read_text() for p in GOLDEN_DIR.rglob("*") if p.is_file())
    domains = re.findall(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)", text)
    assert domains and all(d.endswith(".example") for d in domains)


def test_files_match_documents():
    for f in FIXTURE.evidence:
        assert hashlib.sha256((GOLDEN_DOCUMENTS / f.name).read_bytes()).hexdigest() == f.sha256
        assert f.storage_path == f"{f.workspace_id}/{f.grant_id}/{f.id}/{f.name}"


def test_citations_quote_their_documents():
    for r in FIXTURE.records:
        for c in all_citations(r):
            loc = c.location
            assert isinstance(loc, ContentBlockLocation) and c.passage
            doc = blocks(NAMES[c.file_id])
            assert c.passage == "\n\n".join(doc[loc.start_block_index : loc.end_block_index])
        for _, v in cited_values(r.data):
            assert v.citation and v.text and v.text in (v.citation.passage or "")
            assert parse(v, v.text) == v.value


def test_every_write_passes_the_write_check():
    """Replayed in order, each record is one the backend would accept."""
    written: list[Record] = []
    for r in FIXTURE.records:
        assert (r.workspace_id, r.grant_id) == (FIXTURE.workspace.id, FIXTURE.grant.id)
        assert check_new_record(r, written, FIXTURE.charges) == [], r.id
        written.append(r)


def test_every_term_is_confirmed_and_nothing_waits():
    terms = [r for r in FIXTURE.records if r.data.kind in TERM_KINDS]
    assert terms and all(r in effective_records(FIXTURE.records) for r in terms)
    assert waiting_records(FIXTURE.records) == []


def test_link_sums_balance():
    links = [r.data for r in current_records(FIXTURE.records) if isinstance(r.data, Link)]
    for c in FIXTURE.charges:
        assert sum(link.amount_cents or 0 for link in links if link.charge_id == c.id) == c.amount_cents


def test_ledger_file_matches_charges():
    with GOLDEN_LEDGER.open(newline="") as f:
        rows = [LedgerRow.model_validate({k: v or None for k, v in row.items()}) for row in csv.DictReader(f)]
    for row, c in zip(rows, FIXTURE.charges, strict=True):
        assert (row.line_id, row.transaction_date, row.posting_date, row.amount_cents) == (
            c.ledger_line_id,
            c.transaction_date,
            c.posting_date,
            c.amount_cents,
        )
        assert (row.description, row.account, row.vendor, row.reference, row.original_line_id) == (
            c.description,
            c.account,
            c.vendor,
            c.reference,
            c.original_line_id,
        )
        assert c.arrived_at == datetime.combine(row.posting_date, time(), tzinfo=UTC)


def norm(value) -> str:
    return " ".join(str(value).split()).casefold()


def test_answer_key_scores_all_right():
    """Scored with the match rules in docs/contracts.md: all right, none wrong, none missing."""
    current = current_records(FIXTURE.records)
    by_id = {r.id: r for r in FIXTURE.records}
    agent = [r for r in current if r.author == Author.AGENT]

    def file_of(record: Record) -> str:
        return NAMES[next(v.citation.file_id for _, v in cited_values(record.data) if v.citation)]

    facts = [
        (r.data.kind, file_of(r), {p: v.value for p, v in cited_values(r.data)})
        for r in agent
        if not isinstance(r.data, Link | Judgment)
    ]
    for e in KEY.records:
        match = next(
            a
            for a in facts
            if a[:2] == (e.kind, e.file) and all(k in a[2] and norm(a[2][k]) == norm(v) for k, v in e.fields.items())
        )
        facts.remove(match)
    assert facts == []

    links = [
        (file_of(by_id[r.data.record_id]), LINES[r.data.charge_id], r.data.amount_cents)
        for r in agent
        if isinstance(r.data, Link)
    ]
    assert sorted(links) == sorted((e.file, e.line_id, e.amount_cents) for e in KEY.links)

    answers = [(LINES[r.data.charge_id], r.data.question, r.data.answer) for r in agent if isinstance(r.data, Judgment)]
    assert sorted(answers) == sorted((e.line_id, e.question, e.answer) for e in KEY.answers)


def test_expected_buckets_follow_arrivals():
    arrived = {c.ledger_line_id: c.arrived_at for c in FIXTURE.charges}
    clock_now = FIXTURE.workspace.clock_now
    assert clock_now is not None
    for b in KEY.buckets:
        assert arrived[b.line_id] <= b.at <= clock_now


# Record rules


def _record(**changes) -> Record:
    fields = dict(
        id="r1",
        workspace_id="w",
        grant_id="g",
        author="user",
        author_user_id="u",
        written_at=NOW,
        data={"kind": "sign_off"},
    )
    return Record.model_validate(fields | changes)


def _agent(**changes) -> Record:
    return _record(author="agent", author_user_id=None, **changes)


BOX = {"type": "image_box", "left": 0.1, "top": 0.2, "width": 0.3, "height": 0.1}
CHARS = {"type": "char_location", "start_char_index": 0, "end_char_index": 17}
PART = {"file_id": "f1", "passage": "Total Due: $12.00", "location": CHARS}
RECEIPT = {"kind": "receipt", "total": {"value": 1200, "text": "$12.00", "citation": PART}}
APPROVAL = {
    "kind": "approval",
    "approver_email": {"value": "a@b.example", "text": "a@b.example", "citation": PART | {"passage": "a@b.example"}},
    "covers": {"value": "x", "text": "x", "citation": PART | {"passage": "x"}},
}
CHARGES = [
    Charge(
        id="c1",
        workspace_id="w",
        grant_id="g",
        ledger_line_id="L-1",
        transaction_date=NOW.date(),
        posting_date=NOW.date(),
        arrived_at=NOW,
        amount_cents=1200,
        description="d",
        account="a",
    )
]


def _link(**changes) -> dict:
    return {"kind": "link", "record_id": "rcpt", "charge_id": "c1", "amount_cents": 1200, "part": PART} | changes


def test_record_rules():
    uncited = {"kind": "period_of_performance", "end": {"value": "2026-01-31"}}
    _record(data=uncited)  # the accountant may enter a value with no citation
    for bad in (
        dict(author_user_id=None),  # the accountant's record names them
        dict(author="agent", author_user_id=None),  # only the accountant signs off
        dict(author="agent", author_user_id=None, data=uncited),  # the agent always cites
        dict(author="agent", author_user_id=None, data=_link(part=None)),  # the agent's link has a part
        dict(data={"kind": "retraction"}),  # a retraction replaces something
        dict(  # the agent's flag can only be unsure
            author="agent",
            author_user_id=None,
            data={
                "kind": "judgment",
                "charge_id": "c1",
                "question": "flag",
                "text": "?",
                "answer": "supports",
                "reasoning": "r",
            },
        ),
        dict(  # a covers question names its approval
            data={
                "kind": "judgment",
                "charge_id": "c1",
                "question": "covers",
                "text": "?",
                "answer": "unsure",
                "reasoning": "r",
            }
        ),
    ):
        with pytest.raises(ValidationError):
            _record(**bad)


def test_citation_rules():
    pages = {"type": "page_location", "start_page_number": 1, "end_page_number": 2}
    Citation.model_validate({"file_id": "f", "passage": None, "location": BOX})
    with pytest.raises(ValidationError):
        Citation.model_validate({"file_id": "f", "passage": "typed by the model", "location": BOX})
    with pytest.raises(ValidationError):
        Citation.model_validate({"file_id": "f", "passage": None, "location": pages})


def test_nested_values_need_citations():
    item = {"description": {"value": "x"}, "amount": {"value": 100}}
    with pytest.raises(ValidationError):
        _agent(data=RECEIPT | {"items": [item]})


def test_write_check_on_links():
    receipt = _agent(id="rcpt", data=RECEIPT)
    approval = _agent(id="appr", data=APPROVAL)
    written = [receipt, approval]

    def problems(data: dict, **changes) -> list[str]:
        return check_new_record(_agent(id="new", data=data, **changes), written, CHARGES)

    assert problems(_link()) == []
    assert problems(_link(amount_cents=None))  # a receipt link needs an amount
    assert problems(_link(record_id="appr"))  # an approval link has no amount
    assert problems(_link(record_id="appr", amount_cents=None, part=PART | {"passage": "x"})) == []
    assert problems(_link(part=PART | {"file_id": "f2"}))  # the part is in the record's own file
    assert problems(_link(charge_id="nope"))
    assert problems(RECEIPT | {"total": RECEIPT["total"] | {"text": "$13.00"}})  # trust rule 2 at write time


def test_agent_fixes_wait_for_the_accountant():
    receipt = _agent(id="rcpt", data=RECEIPT)
    link = _agent(id="l1", data=_link())
    fix = _agent(id="l2", data=_link(amount_cents=600), replaces_id="l1")
    written = [receipt, link, fix]
    assert waiting_records(written) == [fix]
    assert [r.id for r in current_records(written)] == ["rcpt", "l1"]  # the old link stays in force

    approve = _record(id="ok", data={"kind": "confirmation", "record_ids": ["l2"]}, written_at=NOW + timedelta(1))
    assert [r.id for r in current_records([*written, approve])] == ["rcpt", "l2", "ok"]

    reject = approve.model_copy(update={"data": approve.data.model_copy(update={"decision": "rejected"})})
    assert [r.id for r in current_records([*written, reject])] == ["rcpt", "l1", "ok"]
    assert waiting_records([*written, reject]) == []


def test_agent_only_suggests_fixes_to_the_accountants_links():
    receipt = _agent(id="rcpt", data=RECEIPT)
    their_link = _record(id="l1", data=_link())
    their_answer = _record(
        id="j1",
        data={
            "kind": "judgment",
            "charge_id": "c1",
            "question": "allowable",
            "text": "?",
            "answer": "supports",
            "reasoning": "r",
        },
    )
    written = [receipt, their_link, their_answer]

    fix = _agent(id="l2", data=_link(amount_cents=600), replaces_id="l1")
    assert check_new_record(fix, written, CHARGES) == []
    assert waiting_records([*written, fix]) == [fix]  # it waits for the accountant

    overrule = _agent(id="j2", data=their_answer.data.model_dump() | {"answer": "contradicts"}, replaces_id="j1")
    assert check_new_record(overrule, written, CHARGES)  # their answers stay theirs


def test_accountant_answers_a_flag():
    flag = {"kind": "judgment", "charge_id": "c1", "question": "flag", "text": "Which invoices?", "reasoning": "r"}
    _agent(data=flag | {"answer": "unsure"})
    _record(data=flag | {"answer": "supports"})  # the accountant can settle it


def test_agent_answers_again_without_waiting():
    answer = {"kind": "judgment", "charge_id": "c1", "question": "allowable", "text": "?", "reasoning": "r"}
    first = _agent(id="j1", data=answer | {"answer": "unsure"})
    again = _agent(id="j2", data=answer | {"answer": "supports"}, replaces_id="j1")
    assert [r.id for r in current_records([first, again])] == ["j2"]


def test_retraction():
    records = [_record(id="a"), _record(id="b", replaces_id="a", data={"kind": "retraction"})]
    assert current_records(records) == []


def test_bucket_is_the_most_serious_reason():
    reasons = [
        Reason(check="x", bucket=Bucket.MISSING_EVIDENCE, text="x"),
        Reason(check="y", bucket=Bucket.POSSIBLE_CONFLICT, text="y"),
    ]
    ChargeStatus(charge_id="c", bucket=Bucket.POSSIBLE_CONFLICT, reasons=reasons, flagged=True)
    with pytest.raises(ValidationError):
        ChargeStatus(charge_id="c", bucket=Bucket.MISSING_EVIDENCE, reasons=reasons, flagged=True)
    with pytest.raises(ValidationError):  # a conflict is always on the problem list
        ChargeStatus(charge_id="c", bucket=Bucket.POSSIBLE_CONFLICT, reasons=reasons, flagged=False)


def test_run_checks_is_a_stub():
    checks_input = ChecksInput(now=NOW, charges=FIXTURE.charges, evidence=FIXTURE.evidence, records=FIXTURE.records)
    with pytest.raises(NotImplementedError):
        run_checks(checks_input)


def test_api_models_have_json_schemas():
    models = [m for m in vars(api).values() if isinstance(m, type) and issubclass(m, BaseModel)]
    assert len(models) > 10
    for m in models:
        m.model_json_schema()
