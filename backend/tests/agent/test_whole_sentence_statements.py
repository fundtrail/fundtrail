"""A statement that wraps in the document is saved whole (#269).

QA found the small sample's "Governing conditions" term stopping mid-sentence: "This award is
subject to the NSF Grant General Conditions (GC-1) effective". The sentence wraps after
"effective" in award_letter.pdf. A label line holds one line, so the agent writes the wrap as a
space, and the write check wants the value's text inside its passage exactly: the whole sentence
was refused, and only its first line could be saved. Now the value's text is stored as the
passage writes it, line break included, and the passage keeps both lines.

The recorded input is the small sample's award letter (tests/agent/fixtures). No model is called.
"""

from dataclasses import replace
from pathlib import Path

from anthropic.types import CitationCharLocation, CitationPageLocation

from app.agent.citations import LabelLine, SentDocument, as_written, resolve_citation
from app.agent.context import RunContext
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool
from app.contracts.records import OtherTerm
from app.contracts.runs import Trigger, TriggerKind

from .fakes import sample_inputs
from .test_benefit_rates import ARRIVED, RATE_FILE

PDF = (Path(__file__).parent / "fixtures" / "nitrate_sensors_award_letter.pdf").read_bytes()
SENTENCE = (
    "This award is subject to the NSF Grant General Conditions (GC-1) effective\n"
    "October 1, 2024, and to the terms of this notice."
)
ONE_LINE = " ".join(SENTENCE.split())  # as the agent writes it on a label line


def page_cite(chunk: str) -> CitationPageLocation:
    return CitationPageLocation(
        type="page_location",
        cited_text=chunk,
        document_index=0,
        start_page_number=1,
        end_page_number=2,
    )


def award_context() -> RunContext:
    award = RATE_FILE.model_copy(
        update={
            "id": "file-award-letter-pdf",
            "name": "award_letter.pdf",
            "storage_path": "ws-sample/grant-sample/file-award-letter-pdf/award_letter.pdf",
        }
    )
    base = sample_inputs(
        now=ARRIVED, trigger=Trigger(kind=TriggerKind.FILE, id=award.id), records=[]
    )
    read = base.read_file
    inputs = replace(
        base,
        files=[*base.files, award],
        read_file=lambda f: PDF if f.id == award.id else read(f),
    )
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook())
    result, error = run_tool(ctx, "open_file", {"file_id": award.id})
    assert not error, result
    return ctx


def test_a_wrapped_statement_is_saved_as_the_whole_sentence():
    ctx = award_context()
    ctx.labels["statement"] = LabelLine("statement", ONE_LINE, [page_cite(SENTENCE)])
    ctx.labels["dated"] = LabelLine(
        "dated", "August 12, 2025", [page_cite("Amendment Date: August 12, 2025")]
    )
    result, error = run_tool(
        ctx,
        "write_term",
        {
            "kind": "other_term",
            "label": "Governing conditions",
            "values": [
                {"field": "dated", "label": "dated", "value": "2025-08-12"},
                {"field": "statement", "label": "statement"},
            ],
        },
    )
    assert not error, result
    term = ctx.staged[-1].record.data
    assert isinstance(term, OtherTerm)
    statement = term.statement
    assert statement.value == ONE_LINE  # the whole sentence, ending "of this notice."
    assert statement.text == SENTENCE  # as the document writes it, line break and all
    assert statement.citation is not None and statement.citation.passage == SENTENCE
    assert statement.citation.match == "exact"
    assert len(statement.citation.highlight or ()) == 2  # both lines of the sentence marked


def test_a_wrapped_value_in_a_longer_text_chunk_keeps_just_its_lines():
    text = (
        "TERMS AND CONDITIONS\n"
        "This award is subject to the NSF Grant General Conditions (GC-1) effective\n"
        "October 1, 2024, and to the terms of this notice.\n"
        "BUDGET\n"
    )
    doc = SentDocument("file-award-text", "text", text=text)
    raw = CitationCharLocation(
        type="char_location",
        cited_text=text,
        document_index=0,
        start_char_index=0,
        end_char_index=len(text),
    )
    c = resolve_citation(ONE_LINE, [raw], [doc])
    assert c["passage"] == SENTENCE and c["match"] == "exact"


def test_as_written_returns_the_passages_own_characters_only_when_its_one_place():
    assert as_written(ONE_LINE, SENTENCE) == SENTENCE
    assert as_written("GC-1", SENTENCE) == "GC-1"  # already there as written
    twice = "Total: $40,000\nTotal:  $40,000"
    assert as_written("Total: $40,000", twice) == "Total: $40,000"
    assert as_written("Total:\n$40,000", twice) == "Total:\n$40,000"  # two places: unchanged


def test_the_agent_is_told_to_copy_the_whole_sentence():
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "copy the whole sentence, not up to the line break" in flat
