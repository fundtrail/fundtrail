"""Issue 336: a bill read from a photo or a scanned PDF can be linked, and quoted in an
answer or a flag.

A photo's or a scan's citation is a box with no passage (`passage` None). The link tool built
the link's part by dumping the bill's citation with None fields left out, which dropped the
required `passage`, so the link failed validation. These go through the agent's own tool path
(`link`, with its default part and with a `quote` of the bill's total), not faked records.
"""

from dataclasses import replace
from datetime import datetime

import pytest

from app.agent.context import RunContext
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import Citation, ImageBox, Match, Record
from app.contracts.runs import Trigger

from .fakes import sample_inputs

SAMPLE = load_sample_grant()


def _box_file(name: str, media_type: str):
    """A photo or a scanned PDF on the sample grant, as the bill's file."""
    invoice = next(f for f in SAMPLE.files if f.id == "file-invoice-1001")
    return invoice.model_copy(
        update={
            "id": "file-box",
            "name": name,
            "media_type": media_type,
            "storage_path": f"{SAMPLE.workspace.id}/{SAMPLE.grant.id}/file-box/{name}",
            "sha256": "box",
        }
    )


def _context(name: str, media_type: str, page: int, until: str = "rec-link-l-1001") -> RunContext:
    """The sample run up to `until` (by default, before L-1001 is linked), with its bill's
    total read from a box on a photo (page 1) or on a page of a scanned PDF, and no passage."""
    box = Citation(
        file_id="file-box",
        passage=None,
        location=ImageBox(page=page, left=0.1, top=0.2, width=0.3, height=0.05),
        match=Match.EXACT,
    )
    records: list[Record] = []
    for r in SAMPLE.records:
        if r.id == until:
            break
        if r.id == "rec-bill-inv-1001":
            total = r.data.total.model_copy(update={"citation": box})  # pyright: ignore[reportAttributeAccessIssue]
            r = r.model_copy(update={"data": r.data.model_copy(update={"total": total})})
        records.append(r)
    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-14T00:00:00+00:00"),
        trigger=Trigger(kind="charge", id="chg-l-1001"),  # pyright: ignore[reportArgumentType]
        records=records,
        charge_ids=["chg-l-1001"],
    )
    inputs = replace(inputs, files=[*inputs.files, _box_file(name, media_type)])
    return RunContext(inputs=inputs, rulebook=load_rulebook())


def _assert_box(citation: Citation | None, page: int) -> None:
    """The saved citation is the box on the photo or the scan, with no passage."""
    assert citation is not None
    assert citation.file_id == "file-box" and citation.passage is None
    assert isinstance(citation.location, ImageBox) and citation.location.page == page


CASES = [
    pytest.param("receipt_photo.jpg", "image/jpeg", 1, id="photo"),
    pytest.param("scanned_invoice.pdf", "application/pdf", 2, id="scanned-pdf-page"),
]


@pytest.mark.parametrize(("name", "media_type", "page"), CASES)
def test_a_bill_read_from_a_box_links_with_its_default_part(
    name: str, media_type: str, page: int
) -> None:
    ctx = _context(name, media_type, page)
    args = {
        "record_id": "rec-bill-inv-1001",
        "charge_id": "chg-l-1001",
        "amount_cents": 124000,
        "default_item": "bill",
    }
    result, error = run_tool(ctx, "link", args)
    assert not error, result
    _assert_box(ctx.staged[-1].record.data.part, page)  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize(("name", "media_type", "page"), CASES)
def test_a_bill_read_from_a_box_links_with_a_quoted_part(
    name: str, media_type: str, page: int
) -> None:
    ctx = _context(name, media_type, page)
    args = {
        "record_id": "rec-bill-inv-1001",
        "charge_id": "chg-l-1001",
        "amount_cents": 124000,
        "default_item": "bill",
        "part": {"record_id": "rec-bill-inv-1001", "field": "total"},
    }
    result, error = run_tool(ctx, "link", args)
    assert not error, result
    _assert_box(ctx.staged[-1].record.data.part, page)  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize(("name", "media_type", "page"), CASES)
def test_an_answer_can_quote_a_bill_read_from_a_box(name: str, media_type: str, page: int) -> None:
    ctx = _context(name, media_type, page, until="rec-budget-l-1001")
    args = {
        "charge_id": "chg-l-1001",
        "question": "allowable",
        "answer": "supports",
        "reasoning": "Lab supplies for the project.",
        "quotes": [{"record_id": "rec-bill-inv-1001", "field": "total"}],
    }
    result, error = run_tool(ctx, "answer", args)
    assert not error, result
    [quoted] = ctx.staged[-1].record.data.quotes  # pyright: ignore[reportAttributeAccessIssue]
    _assert_box(quoted, page)


@pytest.mark.parametrize(("name", "media_type", "page"), CASES)
def test_a_flag_can_quote_a_bill_read_from_a_box(name: str, media_type: str, page: int) -> None:
    ctx = _context(name, media_type, page)
    args = {
        "charge_id": "chg-l-1001",
        "question": "Is this total the whole invoice?",
        "reasoning": "The photo is cut off at the bottom.",
        "quotes": [{"record_id": "rec-bill-inv-1001", "field": "total"}],
    }
    result, error = run_tool(ctx, "flag", args)
    assert not error, result
    [quoted] = ctx.staged[-1].record.data.quotes  # pyright: ignore[reportAttributeAccessIssue]
    _assert_box(quoted, page)
