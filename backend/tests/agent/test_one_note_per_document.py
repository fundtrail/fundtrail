"""Ruling 81's agent instructions: one document, one note; no flag for what a check reports.

The eval's first run found documents split into up to six notes ("postdoc monthly salary",
"cost-share split", ...), and a flag repeating the misfiled-account check. A second note on a
document is refused, as is a note citing more than one file; a correction of the note is how a
fact is added to it. The flag rule is the prompt's: whether a flag repeats a check is a matter
of meaning, so code can't refuse it, and the desk already shows each charge's failing reasons.
"""

from datetime import datetime

from anthropic.types import CitationCharLocation

from app.agent.citations import LabelLine
from app.agent.context import RunContext
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import Note
from app.contracts.runs import Trigger, TriggerKind

from .fakes import sample_inputs

SAMPLE = load_sample_grant()
INVOICE = SAMPLE.document("file-invoice-1001")
NOTICE = SAMPLE.document("file-extension-notice")
LINERS = "Sediment core liners, 50 count: $1,240.00"


def context() -> RunContext:
    inputs = sample_inputs(
        now=datetime.fromisoformat("2026-04-10T00:00:00+00:00"),
        trigger=Trigger(kind=TriggerKind.FILE, id="file-invoice-1001"),
        records=[],
    )
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook())
    for file_id in ("file-invoice-1001", "file-extension-notice"):  # documents 0 and 1
        result, error = run_tool(ctx, "open_file", {"file_id": file_id})
        assert not error, result
    return ctx


def label(ctx: RunContext, name: str, value: str, document: int, chunk: str) -> None:
    text = INVOICE if document == 0 else NOTICE
    start = text.index(chunk)
    cite = CitationCharLocation(
        type="char_location",
        cited_text=chunk,
        document_index=document,
        start_char_index=start,
        end_char_index=start + len(chunk),
    )
    ctx.labels[name] = LabelLine(name, value, [cite])


def note(ctx: RunContext, name: str, values: list[dict[str, str]], replaces: str | None = None):
    args: dict[str, object] = {"kind": "note", "label": name, "values": values}
    if replaces:
        args["replaces_id"] = replaces
    return run_tool(ctx, "write_fact", args)


def test_a_second_note_on_a_document_is_refused_and_a_correction_is_the_way_to_add_to_it():
    ctx = context()
    label(ctx, "what", "Sediment core liners, 50 count: $1,240.00", 0, LINERS)
    result, error = note(ctx, "Liners invoice", [{"field": "statement", "label": "what"}])
    assert not error, result
    first = ctx.staged[-1].record.id

    label(ctx, "award", "Award: SYN-2300117", 0, "Award: SYN-2300117")
    result, error = note(ctx, "Award on the invoice", [{"field": "statement", "label": "award"}])
    assert error and "already has its note" in result and first in result
    assert "One document is one note" in result and "replaces_id" in result
    assert len([s for s in ctx.staged if isinstance(s.record.data, Note)]) == 1

    result, error = note(
        ctx, "Liners invoice", [{"field": "statement", "label": "award"}], replaces=first
    )
    assert not error, result  # the correction of that note


def test_a_note_citing_two_documents_is_refused():
    ctx = context()
    label(ctx, "what", "Sediment core liners, 50 count: $1,240.00", 0, LINERS)
    label(ctx, "start", "January 15, 2026", 1, "Amendment Date: January 15, 2026")
    label(ctx, "end", "January 31, 2027", 1, "January 31, 2027")
    values = [
        {"field": "statement", "label": "what"},
        {"field": "period.start", "label": "start", "value": "2026-01-15"},
        {"field": "period.end", "label": "end", "value": "2027-01-31"},
    ]
    result, error = note(ctx, "Mixed", values)
    assert error and "A note is about one document" in result
    assert not ctx.staged


def test_two_documents_get_a_note_each():
    ctx = context()
    label(ctx, "a", "Sediment core liners, 50 count: $1,240.00", 0, LINERS)
    label(ctx, "b", "Amendment Type: No Cost Extensions", 1, "Amendment Type: No Cost Extensions")
    for name, lab in (("Liners invoice", "a"), ("Extension", "b")):
        result, error = note(ctx, name, [{"field": "statement", "label": lab}])
        assert not error, result
    assert len(ctx.staged) == 2


def test_the_prompt_says_one_note_per_document_and_no_flag_for_a_check():
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "One document is one note" in flat
    assert "Don't split a document into several notes" in flat
    assert "An award letter or an amendment gives terms, not a note" in flat
    assert "Don't flag what code's checks already report" in flat
    assert "budget line that disagrees with the ledger account" in flat


def test_a_second_fix_while_the_first_waits_is_accepted_and_a_new_note_is_still_refused():
    """Every correction the agent writes waits, so a note can have a waiting fix. Fixing that
    fix, or the note again, is the same note's chain, not a second note (PR 325's review)."""
    ctx = context()
    label(ctx, "what", LINERS, 0, LINERS)
    label(ctx, "award", "Award: SYN-2300117", 0, "Award: SYN-2300117")
    what = [{"field": "statement", "label": "what"}]
    award = [{"field": "statement", "label": "award"}]
    result, error = note(ctx, "Liners invoice", what)
    assert not error, result
    first = ctx.staged[-1].record.id

    result, error = note(ctx, "Liners invoice", award, first)
    assert not error, result
    fix = ctx.staged[-1]
    assert fix.waits  # a correction of the agent's own fact waits

    # Fixing the waiting fix is the contract's to refuse (a replaced record has to be current),
    # never this check's: it's the same note's chain.
    result, error = note(ctx, "Liners invoice", what, fix.record.id)
    assert error and "isn't current" in result and "already has its note" not in result
    result, error = note(ctx, "Liners invoice", award, first)
    assert not error, result  # fixing the note again, while the first fix waits

    result, error = note(ctx, "Another note", award)
    assert error and f"already has its note ({first}," in result  # the version that counts now
