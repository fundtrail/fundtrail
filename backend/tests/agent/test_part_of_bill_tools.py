"""A link for part of a bill carries its cited basis, and the rest of a bill can be given to
another award (decision 0021).

Play 2 found the agent could link the shared invoice for its part, $5,833.33 of $10,000.00, but
no tool could write the link's `share` or `stated_amount`, so the checks sent the charge to Needs a
human (`part_without_basis`), and no tool could write the `remainder` the highlight shows. These
go through the agent's own tools, and the share's effect through the real checks.
"""

from dataclasses import replace
from datetime import datetime
from typing import Any

from anthropic.types import CitationCharLocation

from app.agent.citations import LabelLine
from app.agent.context import RunContext
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool, tool_definitions
from app.checks.run import run_checks
from app.contracts.checks import ChecksInput
from app.contracts.fixtures import DOCUMENTS_DIR, load_sample_grant
from app.contracts.records import Cited, Link, Record, Remainder
from app.contracts.runs import Trigger

from .fakes import sample_inputs

SAMPLE = load_sample_grant()
INVOICE = SAMPLE.document("file-invoice-1001")
SPLIT = (
    "From: Robin Example <robin.example@university.example>\n"
    "Subject: Sediment core liners\n\n"
    "Of the liners on invoice INV-1001, 56 of the 96 are for our grant.\n"
    "The rest are for award SYN-2507264.\n"
)
# 56 of 96 of $1,240.00 is $723.33 (0021: within a cent of the worked-out share).
PART = 72333


def _context() -> RunContext:
    """The sample run before L-1001 is linked, with the split email on the grant, and both
    the invoice (document 0) and the email (document 1) open."""
    records: list[Record] = []
    for r in SAMPLE.records:
        if r.id == "rec-link-l-1001":
            break
        records.append(r)
    invoice = next(f for f in SAMPLE.files if f.id == "file-invoice-1001")
    split = invoice.model_copy(
        update={
            "id": "file-split",
            "name": "split.txt",
            "storage_path": f"{SAMPLE.workspace.id}/{SAMPLE.grant.id}/file-split/split.txt",
            "sha256": "split",
        }
    )
    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-14T00:00:00+00:00"),
        trigger=Trigger(kind="charge", id="chg-l-1001"),  # pyright: ignore[reportArgumentType]
        records=records,
        charge_ids=["chg-l-1001"],
    )
    inputs = replace(
        inputs,
        files=[*inputs.files, split],
        read_file=lambda f: (
            SPLIT.encode() if f.id == "file-split" else (DOCUMENTS_DIR / f.name).read_bytes()
        ),
    )
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook())
    for file_id in ("file-invoice-1001", "file-split"):
        _, error = run_tool(ctx, "open_file", {"file_id": file_id})
        assert not error
    return ctx


def _label(ctx: RunContext, name: str, value: str, chunk: str, text: str, index: int) -> None:
    start = text.find(chunk)
    assert start >= 0, chunk
    ctx.labels[name] = LabelLine(
        label=name,
        text=value,
        citations=[
            CitationCharLocation(
                type="char_location",
                cited_text=chunk,
                document_index=index,
                start_char_index=start,
                end_char_index=start + len(chunk),
            )
        ],
    )


def _share_labels(ctx: RunContext) -> None:
    _label(ctx, "share", "56", "56 of the 96 are for our grant.", SPLIT, 1)
    _label(ctx, "out_of", "96", "56 of the 96 are for our grant.", SPLIT, 1)
    _label(ctx, "total", "$1,240.00", "Total Due: $1,240.00", INVOICE, 0)


def _link(**extra: Any) -> dict[str, Any]:
    return {
        "record_id": "rec-bill-inv-1001",
        "charge_id": "chg-l-1001",
        "amount_cents": PART,
        "default_item": "bill",
        **extra,
    }


SHARE = {
    "share": {"field": "share", "label": "share"},
    "out_of": {"field": "out_of", "label": "out_of"},
    "total": {"field": "total", "label": "total"},
}


def _part_without_basis(ctx: RunContext) -> bool:
    """Whether the real checks find L-1001's link for part of its bill without a basis."""
    i = ctx.inputs
    out = run_checks(
        ChecksInput(
            now=i.now, charges=tuple(i.charges), files=tuple(i.files), records=tuple(ctx.records)
        )
    )
    status = next(s for s in out.charges if s.charge_id == "chg-l-1001")
    return any(r.problem.startswith("part_without_basis") for r in status.reasons)


def _file_of(value: Cited[Any]) -> str:
    assert value.citation is not None
    return value.citation.file_id


def _staged_link(ctx: RunContext) -> Link:
    data = ctx.staged[-1].record.data
    assert isinstance(data, Link)
    return data


def test_the_tools_offer_a_share_a_stated_amount_and_a_remainder() -> None:
    tools = {t["name"]: t for t in tool_definitions()}
    assert {"share", "stated_amount"} <= set(tools["link"]["input_schema"]["properties"])
    assert "suggest_remainder" in tools


def test_a_link_for_part_of_a_bill_carries_its_cited_share() -> None:
    ctx = _context()
    _share_labels(ctx)
    result, error = run_tool(ctx, "link", _link(share=SHARE))
    assert not error, result
    share = _staged_link(ctx).share
    assert share is not None
    assert (share.share.value, share.out_of.value, share.total.value) == (56, 96, 124000)
    assert _file_of(share.share) == "file-split"
    assert _file_of(share.total) == "file-invoice-1001"
    assert share.matches(PART)
    assert not _part_without_basis(ctx)


def test_without_its_basis_the_part_goes_to_a_person() -> None:
    """The regression play 2 found: the same link with no share."""
    ctx = _context()
    result, error = run_tool(ctx, "link", _link())
    assert not error, result
    assert _part_without_basis(ctx)


def test_a_link_for_part_of_a_bill_carries_its_cited_stated_amount() -> None:
    ctx = _context()
    _label(ctx, "part", "$1,240.00", "Sediment core liners, 50 count: $1,240.00", INVOICE, 0)
    result, error = run_tool(
        ctx, "link", _link(amount_cents=124000, stated_amount={"field": "x", "label": "part"})
    )
    assert not error, result
    stated = _staged_link(ctx).stated_amount
    assert stated is not None
    assert stated.value == 124000 and _file_of(stated) == "file-invoice-1001"


def test_a_share_whose_text_isnt_a_number_is_refused() -> None:
    ctx = _context()
    _share_labels(ctx)
    _label(ctx, "share", "most", "56 of the 96 are for our grant.", SPLIT, 1)
    result, error = run_tool(ctx, "link", _link(share=SHARE))
    assert error and "share" in result


def test_the_rest_of_a_bill_can_be_suggested_for_another_award() -> None:
    ctx = _context()
    _label(ctx, "award", "SYN-2507264", "The rest are for award SYN-2507264.", SPLIT, 1)
    result, error = run_tool(
        ctx,
        "suggest_remainder",
        {
            "record_id": "rec-bill-inv-1001",
            "other_award": {"field": "other_award", "label": "award"},
            "reason": "The email gives the other 40 liners to another award.",
            "quotes": [{"label": "award"}],
        },
    )
    assert not error, result
    staged = ctx.staged[-1]
    assert staged.record.kind == "remainder" and staged.waits
    data = staged.record.data
    assert isinstance(data, Remainder)
    assert data.other_award.value == "SYN-2507264" and _file_of(data.other_award) == "file-split"
