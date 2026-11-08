"""The golden fixture validates against the contracts and agrees with its own documents.

Run from backend/: python -m pytest app/contracts
"""

import csv
import hashlib
import re
from datetime import UTC, datetime, time
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from app.contracts import (
    TERM_KINDS,
    Author,
    Bucket,
    ChargeStatus,
    ChecksInput,
    Citation,
    Cited,
    CitedDate,
    CitedMoney,
    ContentBlockLocation,
    LedgerRow,
    Link,
    Reason,
    Record,
    api,
    confirmed_term_ids,
    current_records,
    run_checks,
)
from app.contracts.fixtures import GOLDEN_DIR, GOLDEN_DOCUMENTS, GOLDEN_LEDGER, load_golden, load_golden_answer_key

FIXTURE = load_golden()
KEY = load_golden_answer_key()
NOW = datetime(2026, 4, 10, 17, tzinfo=UTC)


def blocks(name: str) -> list[str]:
    """One block per paragraph, the way the agent sends text to Claude."""
    return [p.strip() for p in (GOLDEN_DOCUMENTS / name).read_text().split("\n\n") if p.strip()]


def cited_values(record: Record) -> list[tuple[str, Cited, Citation, str]]:
    """(field name, cited value, its citation, its text) for every cited value on a record."""
    return [(n, v, v.citation, v.text) for n, v in record.data if isinstance(v, Cited) and v.citation and v.text]


def parse(cited: Cited, text: str):
    if isinstance(cited, CitedDate):
        return datetime.strptime(text, "%B %d, %Y").date()
    if isinstance(cited, CitedMoney):
        return int(Decimal(text.lstrip("$").replace(",", "")) * 100)
    return text


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
    names = {f.id: f.name for f in FIXTURE.evidence}
    for r in FIXTURE.records:
        for _, v, citation, text in cited_values(r):
            loc = citation.location
            assert isinstance(loc, ContentBlockLocation) and citation.passage
            doc = blocks(names[citation.file_id])
            assert citation.passage == "\n\n".join(doc[loc.start_block_index : loc.end_block_index])
            assert text in citation.passage
            assert parse(v, text) == v.value


def test_references_resolve():
    record_ids = {r.id for r in FIXTURE.records}
    file_ids = {f.id for f in FIXTURE.evidence}
    charge_ids = {c.id for c in FIXTURE.charges}
    for r in FIXTURE.records:
        assert (r.workspace_id, r.grant_id) == (FIXTURE.workspace.id, FIXTURE.grant.id)
        assert r.replaces_id is None or r.replaces_id in record_ids
        assert all(citation.file_id in file_ids for _, _, citation, _ in cited_values(r))
        if isinstance(r.data, Link):
            assert r.data.file_id in file_ids and r.data.charge_id in charge_ids


def test_every_term_is_confirmed():
    terms = {r.id for r in FIXTURE.records if r.data.kind in TERM_KINDS}
    assert confirmed_term_ids(FIXTURE.records) == terms


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


def test_answer_key_matches_agent_records():
    """Scored with the match rule in docs/contracts.md: all right, none wrong, none missing."""
    names = {f.id: f.name for f in FIXTURE.evidence}
    lines = {c.id: c.ledger_line_id for c in FIXTURE.charges}

    def norm(value) -> str:
        return " ".join(str(value).split()).casefold()

    def actual(r: Record):
        if isinstance(r.data, Link):
            return r.data.kind, names[r.data.file_id], {"charge": lines[r.data.charge_id]}
        values = cited_values(r)
        file = names[values[0][2].file_id]
        return r.data.kind, file, {n: v.value for n, v, _, _ in values}

    unmatched = [actual(r) for r in current_records(FIXTURE.records) if r.author == Author.AGENT]
    for e in KEY.records:
        match = next(
            a
            for a in unmatched
            if a[:2] == (e.kind, e.file) and all(k in a[2] and norm(a[2][k]) == norm(v) for k, v in e.fields.items())
        )
        unmatched.remove(match)
    assert unmatched == []


def test_expected_buckets_follow_arrivals():
    arrived = {c.ledger_line_id: c.arrived_at for c in FIXTURE.charges}
    clock_now = FIXTURE.workspace.clock_now
    assert clock_now is not None
    for b in KEY.buckets:
        assert arrived[b.line_id] <= b.at <= clock_now


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


def test_record_rules():
    uncited = {"kind": "period_of_performance", "end": {"value": "2026-01-31"}}
    _record(data=uncited)  # a person may enter a value with no citation
    for bad in (
        dict(author_user_id=None),  # a person's record names the person
        dict(author="agent", author_user_id=None),  # only a person signs off
        dict(author="agent", author_user_id=None, data=uncited),  # the agent always cites
        dict(data={"kind": "retraction"}),  # a retraction replaces something
    ):
        with pytest.raises(ValidationError):
            _record(**bad)


def test_citation_rules():
    box = {"type": "image_box", "left": 0.1, "top": 0.2, "width": 0.3, "height": 0.1}
    pages = {"type": "page_location", "start_page_number": 1, "end_page_number": 2}
    Citation.model_validate({"file_id": "f", "passage": None, "location": box})
    with pytest.raises(ValidationError):
        Citation.model_validate({"file_id": "f", "passage": "typed by the model", "location": box})
    with pytest.raises(ValidationError):
        Citation.model_validate({"file_id": "f", "passage": None, "location": pages})


def test_replacement_and_retraction():
    records = [
        _record(id="a"),
        _record(id="b", replaces_id="a", data={"kind": "sign_off", "note": "corrected"}),
        _record(id="c"),
        _record(id="d", replaces_id="c", data={"kind": "retraction"}),
    ]
    assert [r.id for r in current_records(records)] == ["b"]


def test_bucket_is_the_most_serious_reason():
    reasons = [
        Reason(check="x", bucket=Bucket.MISSING_EVIDENCE, text="x"),
        Reason(check="y", bucket=Bucket.POSSIBLE_CONFLICT, text="y"),
    ]
    ChargeStatus(charge_id="c", bucket=Bucket.POSSIBLE_CONFLICT, reasons=reasons)
    with pytest.raises(ValidationError):
        ChargeStatus(charge_id="c", bucket=Bucket.MISSING_EVIDENCE, reasons=reasons)


def test_run_checks_is_a_stub():
    checks_input = ChecksInput(now=NOW, charges=FIXTURE.charges, evidence=FIXTURE.evidence, records=FIXTURE.records)
    with pytest.raises(NotImplementedError):
        run_checks(checks_input)


def test_api_models_have_json_schemas():
    models = [m for m in vars(api).values() if isinstance(m, type) and issubclass(m, BaseModel)]
    assert len(models) > 10
    for m in models:
        m.model_json_schema()
