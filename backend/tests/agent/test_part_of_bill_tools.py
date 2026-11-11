"""A link for part of a bill carries its cited basis, and the rest of a bill can be given to
another award (decision 0021).

Play 2 found the agent could link the shared invoice for its part, $5,833.33 of $10,000.00, but
no tool could write the link's `share` or `stated_amount`, so the checks sent the charge to Needs a
human (`part_without_basis`), and no tool could write the `remainder` the highlight shows. These
go through the agent's own tools, and the share's effect through the real checks.
"""

import io
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from anthropic.types import CitationCharLocation
from PIL import Image

from app.agent.citations import LabelLine
from app.agent.context import RunContext
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool, tool_definitions
from app.checks.run import run_checks
from app.contracts.checks import ChecksInput
from app.contracts.fixtures import DOCUMENTS_DIR, load_sample_grant
from app.contracts.records import Author, Cited, ImageBox, Link, Record, Remainder
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
# A second invoice, $2,000.00, whose own lines state each award's part.
INVOICE_2 = (
    "Example Lab Supply Co.\n"
    "Invoice Number: INV-1077\n"
    "Liners for award SYN-2300117: $1,240.00\n"
    "Liners for award SYN-2507264: $760.00\n"
    "Total Due: $2,000.00\n"
)


def _photo() -> bytes:
    """A photo of the invoice: a plain page, on which a box is drawn around its total."""
    out = io.BytesIO()
    Image.new("RGB", (1200, 800), "white").save(out, format="PNG")
    return out.getvalue()


EXTRA = {
    "file-split": ("split.txt", "text/plain", SPLIT.encode()),
    "file-invoice-2": ("invoice_1077.txt", "text/plain", INVOICE_2.encode()),
    "file-photo": ("invoice_photo.png", "image/png", _photo()),
}


def _context() -> RunContext:
    """The sample run before L-1001 is linked, with the split email, a second invoice and a
    photo of the invoice on the grant, all open: the invoice is document 0, the email 1, the
    second invoice 2, and the photo an image."""
    records: list[Record] = []
    for r in SAMPLE.records:
        if r.id == "rec-link-l-1001":
            break
        records.append(r)
    invoice = next(f for f in SAMPLE.files if f.id == "file-invoice-1001")
    extra = [
        invoice.model_copy(
            update={
                "id": file_id,
                "name": name,
                "media_type": media_type,
                "storage_path": f"{SAMPLE.workspace.id}/{SAMPLE.grant.id}/{file_id}/{name}",
                "sha256": file_id,
            }
        )
        for file_id, (name, media_type, _) in EXTRA.items()
    ]
    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-14T00:00:00+00:00"),
        trigger=Trigger(kind="charge", id="chg-l-1001"),  # pyright: ignore[reportArgumentType]
        records=records,
        charge_ids=["chg-l-1001"],
    )
    inputs = replace(
        inputs,
        files=[*inputs.files, *extra],
        read_file=lambda f: (
            EXTRA[f.id][2] if f.id in EXTRA else (DOCUMENTS_DIR / f.name).read_bytes()
        ),
    )
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook())
    for file_id in ("file-invoice-1001", "file-split", "file-invoice-2", "file-photo"):
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


def _problems(ctx: RunContext, prefix: str) -> list[str]:
    """L-1001's reasons from the real checks whose problem starts with `prefix`."""
    i = ctx.inputs
    out = run_checks(
        ChecksInput(
            now=i.now, charges=tuple(i.charges), files=tuple(i.files), records=tuple(ctx.records)
        )
    )
    status = next(s for s in out.charges if s.charge_id == "chg-l-1001")
    return [r.problem for r in status.reasons if r.problem.startswith(prefix)]


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


def _object(node: dict[str, Any]) -> dict[str, Any]:
    """An optional field's schema, without its anyOf with null."""
    return next((n for n in node.get("anyOf", [node]) if n.get("type") == "object"), node)


def test_the_tools_offer_a_share_a_stated_amount_and_a_remainder() -> None:
    tools = {t["name"]: t for t in tool_definitions()}
    assert {"share", "stated_amount"} <= set(tools["link"]["input_schema"]["properties"])
    assert "suggest_remainder" in tools


def test_the_schema_the_model_sees_keeps_each_fields_description() -> None:
    """A field whose type is another model ($ref) keeps the description written on the field,
    so the model sees what each basis value is."""
    tools = {t["name"]: t for t in tool_definitions()}
    share = _object(tools["link"]["input_schema"]["properties"]["share"])["properties"]
    assert share["share"]["description"] == "This grant's part, for example 56."
    assert share["out_of"]["description"] == "The whole it's a part of, for example 96."
    assert share["total"]["description"] == "The bill's total the share is of."
    remainder = tools["suggest_remainder"]["input_schema"]["properties"]
    assert remainder["other_award"]["description"] == "The award the passage names, cited."


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
    """INV-1077 is $2,000.00; its own line states $1,240.00 for this grant, which L-1001 is
    linked for. The real checks find the part's basis on the bill."""
    ctx = _context()
    _label(ctx, "total2", "$2,000.00", "Total Due: $2,000.00", INVOICE_2, 2)
    result, error = run_tool(
        ctx, "write_fact", {"kind": "bill", "values": [{"field": "total", "label": "total2"}]}
    )
    assert not error, result
    bill_id = ctx.staged[-1].record.id
    _label(ctx, "part", "$1,240.00", "Liners for award SYN-2300117: $1,240.00", INVOICE_2, 2)
    args = _link(
        record_id=bill_id, amount_cents=124000, stated_amount={"field": "x", "label": "part"}
    )
    result, error = run_tool(ctx, "link", args)
    assert not error, result
    stated = _staged_link(ctx).stated_amount
    assert stated is not None
    assert stated.value == 124000 and _file_of(stated) == "file-invoice-2"
    assert not _part_without_basis(ctx)
    assert not _problems(ctx, "part_")


def test_a_share_whose_text_isnt_a_number_is_refused() -> None:
    ctx = _context()
    _share_labels(ctx)
    _label(ctx, "share", "most", "56 of the 96 are for our grant.", SPLIT, 1)
    result, error = run_tool(ctx, "link", _link(share=SHARE))
    assert error and "share.share: 'most' can't be read as a share" in result, result


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


def test_a_basis_value_can_be_a_box_on_a_photo() -> None:
    """The share's total read from a box on a photo of the invoice: no passage, a box."""
    ctx = _context()
    _share_labels(ctx)
    total = {
        "field": "total",
        "text": "$1,240.00",
        "box": {"file_id": "file-photo", "left": 800, "top": 600, "right": 1000, "bottom": 650},
    }
    result, error = run_tool(ctx, "link", _link(share={**SHARE, "total": total}))
    assert not error, result
    share = _staged_link(ctx).share
    assert share is not None and share.total.value == 124000
    citation = share.total.citation
    assert citation is not None and citation.file_id == "file-photo"
    assert citation.passage is None and isinstance(citation.location, ImageBox)


def _bill_problems(ctx: RunContext, records: list[Record], now: datetime) -> list[str]:
    i = ctx.inputs
    out = run_checks(
        ChecksInput(now=now, charges=tuple(i.charges), files=tuple(i.files), records=tuple(records))
    )
    return [
        p.problem
        for status in out.records
        if status.record_id == "rec-bill-inv-1001"
        for p in status.problems
    ]


def test_an_accepted_remainder_stops_the_bills_unused_problem() -> None:
    """60 days on, the rest of INV-1001 that no charge uses is a problem on the bill, until the
    accountant accepts the agent's remainder for another award."""
    ctx = _context()
    _share_labels(ctx)
    result, error = run_tool(ctx, "link", _link(share=SHARE))
    assert not error, result
    later = ctx.inputs.now + timedelta(days=61)
    assert "unused" in _bill_problems(ctx, list(ctx.records), later)
    _label(ctx, "award", "SYN-2507264", "The rest are for award SYN-2507264.", SPLIT, 1)
    result, error = run_tool(
        ctx,
        "suggest_remainder",
        {
            "record_id": "rec-bill-inv-1001",
            "other_award": {"field": "other_award", "label": "award"},
            "reason": "The email gives the other 40 liners to another award.",
        },
    )
    assert not error, result
    remainder = ctx.staged[-1].record
    accepted = Record.model_validate(
        {
            "id": "rec-accept-remainder",
            "workspace_id": remainder.workspace_id,
            "grant_id": remainder.grant_id,
            "author": Author.USER,
            "author_user_id": "user-accountant",
            "written_at": later,
            "data": {"kind": "confirmation", "record_ids": [remainder.id]},
        }
    )
    assert "unused" not in _bill_problems(ctx, [*ctx.records, accepted], later)
