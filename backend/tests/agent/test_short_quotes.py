"""A value's citation is the shortest passage that holds it: its line, not the API's chunk.

The API cites a PDF a sentence at a time, and an award notice has no full stop until its
amendment description, so the smallest chunk that holds the amendment number is the first
eleven lines of the page. The UI audit of the live small sample found those eleven lines stored
as the quote for single values, filling Terms and Evidence with long blocks.

The recorded input is the small sample's award letter (data/samples/nitrate-sensors, copied to
tests/agent/fixtures). The chunks below are the sentences of its text as pdfium reads it, the
way the API cites them. No model is called.
"""

from dataclasses import replace
from pathlib import Path

from anthropic.types import CitationPageLocation

from app.agent.citations import LabelLine, SentDocument, resolve_citation
from app.agent.context import RunContext
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool
from app.contracts.records import Notice
from app.contracts.runs import Trigger, TriggerKind

from .fakes import sample_inputs
from .test_benefit_rates import ARRIVED, RATE_FILE

PDF = (Path(__file__).parent / "fixtures" / "nitrate_sensors_award_letter.pdf").read_bytes()
DOC = SentDocument("file-award-letter-pdf", "pdf", pdf=PDF)

# The first sentence of the page: eleven lines, up to the first full stop.
OPENING = """NATIONAL SCIENCE FOUNDATION
AWARD NOTICE
RECIPIENT INFORMATION
Recipient: University of Example
Address: 100 Example Hall, Example City, CA 94000
AMENDMENT INFORMATION
Amendment Type: New Project
Amendment Number: 000
Amendment Date: August 12, 2025
Amendment Description: This amendment funds a new project for the period
of performance shown below."""

FUNDING = """FUNDING INFORMATION
Amount Obligated by this Amendment: $40,000
Total Intended Award Amount: $40,000
Cost Share: $0
Total Amount Obligated to Date: $40,000
Expenditure Limitation: Not applicable"""


def page_cite(chunk: str) -> CitationPageLocation:
    return CitationPageLocation(
        type="page_location",
        cited_text=chunk,
        document_index=0,
        start_page_number=1,
        end_page_number=2,
    )


def test_the_eleven_line_chunk_is_stored_as_the_line_that_holds_the_value():
    assert len(OPENING.splitlines()) == 11
    for value, line in [
        ("000", "Amendment Number: 000"),
        ("August 12, 2025", "Amendment Date: August 12, 2025"),
        ("New Project", "Amendment Type: New Project"),
    ]:
        c = resolve_citation(value, [page_cite(OPENING)], [DOC])
        assert c["passage"] == line and c["match"] == "exact", value
        boxes = c["highlight"]
        assert len(boxes) == 1 and boxes[0]["page"] == 1  # one line marked, not a section
        assert boxes[0]["height"] < 0.05, value


def test_a_value_on_several_lines_keeps_only_those_lines():
    c = resolve_citation("$40,000", [page_cite(FUNDING)], [DOC])
    passage = c["passage"]
    assert passage.startswith("Amount Obligated by this Amendment: $40,000")
    assert passage.endswith("Total Amount Obligated to Date: $40,000")
    assert "FUNDING INFORMATION" not in passage and "Expenditure Limitation" not in passage


def test_a_chunk_the_finder_cant_place_stays_as_the_api_gave_it():
    bogus = "Amendment Number: 000\nAmendment Date: March 3, 2031"
    c = resolve_citation("000", [page_cite(bogus)], [DOC])
    assert c["match"] == "not_found" and c["passage"] == bogus


def test_a_notice_written_from_the_long_chunks_saves_one_line_quotes():
    """The Terms screen shows these passages: each is the line with its value."""
    award = RATE_FILE.model_copy(
        update={
            "id": DOC.file_id,
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
    for name, value, chunk in [
        ("number", "000", OPENING),
        ("type", "New Project", OPENING),
        ("dated", "August 12, 2025", OPENING),
        ("added", "$40,000", FUNDING),
    ]:
        ctx.labels[name] = LabelLine(name, value, [page_cite(chunk)])
    values = [
        {"field": "dated", "label": "dated", "value": "2025-08-12"},
        {"field": "amendment_number", "label": "number"},
        {"field": "amendment_type", "label": "type"},
        {"field": "obligated_by_amendment", "label": "added", "value": 4000000},
    ]
    result, error = run_tool(ctx, "write_term", {"kind": "notice", "values": values})
    assert not error, result
    notice = ctx.staged[-1].record.data
    assert isinstance(notice, Notice)
    assert notice.amendment_number.citation is not None
    assert notice.amendment_number.citation.passage == "Amendment Number: 000"
    assert notice.dated.citation is not None
    assert notice.dated.citation.passage == "Amendment Date: August 12, 2025"
    assert notice.amendment_type.citation is not None
    assert notice.amendment_type.citation.passage == "Amendment Type: New Project"


def test_the_agent_is_told_to_cite_the_line_that_holds_a_value():
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "Cite each value from the passage that holds it" in flat
    assert "code keeps only the line" in flat
