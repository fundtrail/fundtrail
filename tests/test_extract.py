import json
from pathlib import Path

import pytest

from fundtrail.extract import CacheMiss, build_request, cache_path, fetch_response, parse_response
from fundtrail.fields import AWARD_FIELDS, FieldSpec
from fundtrail.ingest import load_text_document

ROOT = Path(__file__).resolve().parent.parent
AWARD = ROOT / "data" / "demo" / "award_letter.txt"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

PERIOD_END = FieldSpec("period_end", "date", "the last day of the period of performance")
AWARD_NUMBER = FieldSpec("award_number", "text", "the award number")
PSC_BUDGET = FieldSpec("psc_budget", "money", "the PSC budget")

PERIOD_PARAGRAPH = (
    "Period of Performance. The period of performance for this award is September 1, 2022 "
    "through August 31, 2025. Costs must be incurred within the period of performance to be charged to this award."
)


def cite(text, start, end=None):
    return {
        "type": "content_block_location",
        "cited_text": text,
        "document_index": 0,
        "start_block_index": start,
        "end_block_index": end if end is not None else start + 1,
    }


def response(*blocks):
    return {"content": list(blocks)}


def test_award_letter_splits_into_paragraph_blocks():
    doc = load_text_document(AWARD)
    assert len(doc.blocks) == 8
    assert "August 31, 2025" in doc.blocks[3]


def test_real_step1_response_verifies_period_end():
    """The live response from step 1: text split in two, citation only on the date."""
    data = json.loads((FIXTURES / "step1_period_end_response.json").read_text())
    [record] = parse_response(data, "award_letter", [PERIOD_END])
    assert record.status == "verified"
    assert record.value == "August 31, 2025"
    assert record.value_normalized == "2025-08-31"
    assert (record.block, record.block_end) == (3, 4)


def test_citations_bind_to_their_own_line():
    data = response(
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text": "award_number: "},
        {"type": "text", "text": "SYN-2400042", "citations": [cite("Award Number: SYN-2400042", 1)]},
        {"type": "text", "text": "\nperiod_end: "},
        {"type": "text", "text": "August 31, 2025", "citations": [cite(PERIOD_PARAGRAPH, 3)]},
    )
    records = {r.field: r for r in parse_response(data, "award_letter", [AWARD_NUMBER, PERIOD_END])}
    assert records["award_number"].status == "verified"
    assert records["award_number"].block == 1
    assert records["period_end"].status == "verified"
    assert records["period_end"].block == 3


def test_value_without_citation_is_flagged():
    data = response({"type": "text", "text": "period_end: August 31, 2025"})
    [record] = parse_response(data, "award_letter", [PERIOD_END])
    assert record.status == "no_citation"
    assert record.value_normalized == "2025-08-31"


def test_citation_that_does_not_state_the_value_is_flagged():
    data = response(
        {"type": "text", "text": "psc_budget: "},
        {"type": "text", "text": "$300,000", "citations": [cite("participant support costs ($30,000) may not", 5)]},
    )
    [record] = parse_response(data, "award_letter", [PSC_BUDGET])
    assert record.status == "value_not_in_citation"
    assert record.cited_text == "participant support costs ($30,000) may not"


def test_second_citation_is_used_when_first_does_not_support_value():
    data = response(
        {"type": "text", "text": "psc_budget: "},
        {"type": "text", "text": "$30,000", "citations": [cite("The total is $300,000.", 4), cite("budgeted ($30,000)", 5)]},
    )
    [record] = parse_response(data, "award_letter", [PSC_BUDGET])
    assert record.status == "verified"
    assert record.block == 5


def test_not_found_and_missing_lines():
    data = response({"type": "text", "text": "award_number: NOT FOUND"})
    records = {r.field: r for r in parse_response(data, "award_letter", [AWARD_NUMBER, PERIOD_END])}
    assert records["award_number"].status == "not_found"
    assert records["award_number"].value is None
    assert records["period_end"].status == "missing"


def test_request_sends_every_block_with_citations_on():
    doc = load_text_document(AWARD)
    request = build_request(doc, AWARD_FIELDS)
    document = request["messages"][0]["content"][0]
    assert document["citations"] == {"enabled": True}
    assert len(document["source"]["content"]) == len(doc.blocks)
    prompt = request["messages"][0]["content"][1]["text"]
    assert all(f"{f.name}:" in prompt for f in AWARD_FIELDS)


def test_replay_without_cache_never_calls_the_api(tmp_path):
    doc = load_text_document(AWARD)
    with pytest.raises(CacheMiss):
        fetch_response(doc, AWARD_FIELDS, replay=True, cache_dir=tmp_path)


def test_cached_response_is_used_without_a_client(tmp_path):
    doc = load_text_document(AWARD)
    path = cache_path(doc, [PERIOD_END], tmp_path)
    path.write_text((FIXTURES / "step1_period_end_response.json").read_text())
    data = fetch_response(doc, [PERIOD_END], replay=True, cache_dir=tmp_path)
    assert data["content"][1]["text"] == "August 31, 2025"


def test_cache_key_changes_when_prompt_changes(tmp_path):
    doc = load_text_document(AWARD)
    assert cache_path(doc, [PERIOD_END], tmp_path) != cache_path(doc, [PERIOD_END, AWARD_NUMBER], tmp_path)
