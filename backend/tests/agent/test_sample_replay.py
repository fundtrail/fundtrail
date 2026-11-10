"""The sample grant (contracts.md section 15) replayed through the agent with a fake model.

The fake model reads each document the way the API would cite it (a paragraph at a time), writes
its label lines in a message of their own, then the records. Every record passes the write check
as it's staged and again before it's handed back, and the agent's records come out equal to the
sample's own, citations included: the line narrowing reproduces the sample's one-line passages.
"""

from datetime import datetime
from typing import Any

from app.agent import RunSaved, run_agent
from app.agent.model import ModelRequest
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import Author, Record, cited_values
from app.contracts.rules import check_new_record
from app.contracts.runs import Trigger

from .fakes import (
    FakeModel,
    api_chunk,
    calls,
    label_for,
    label_message,
    results_of,
    sample_inputs,
    tool,
)

SAMPLE = load_sample_grant()
BY_ID = {r.id: r for r in SAMPLE.records}

TERM_KINDS = {
    "period_of_performance",
    "budget_line",
    "person",
    "approval_rule",
    "notice",
    "other_term",
    "rate",
}


def _lines(request: ModelRequest, records: list[Record]) -> list[tuple[str, str, str, str]]:
    lines: dict[str, tuple[str, str, str, str]] = {}
    for r in records:
        for path, v in cited_values(r.data):
            assert v.citation is not None and v.citation.passage is not None and v.text
            doc = SAMPLE.document(v.citation.file_id)
            chunk = api_chunk(doc, v.citation.passage, v.text)
            label = label_for(r.id, path)
            lines[label] = (label, v.text, v.citation.file_id, chunk)
    return list(lines.values())


def _values(r: Record) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path, v in cited_values(r.data):
        item: dict[str, Any] = {"field": path, "label": label_for(r.id, path)}
        if not isinstance(v.value, str):
            item["value"] = str(v.value)
        out.append(item)
    return out


def _write(r: Record):
    data = r.data
    extra: dict[str, Any] = {}
    if getattr(data, "category", None) is not None:
        extra["category"] = data.category.value  # pyright: ignore[reportAttributeAccessIssue]
    if getattr(data, "label", None) is not None:
        extra["label"] = data.label  # pyright: ignore[reportAttributeAccessIssue]
    name = "write_term" if data.kind in TERM_KINDS else "write_fact"
    return tool(name, kind=data.kind.value, values=_values(r), **extra)


def file_run(file_id: str, record_ids: list[str], now: str, db: list[Record]) -> RunSaved:
    expected = [BY_ID[i] for i in record_ids]

    def read(request: ModelRequest):
        return label_message(request, _lines(request, expected))

    def write(request: ModelRequest):
        assert "Recorded with citations" in request.messages[-1]["content"]
        return calls(*[_write(r) for r in expected], tool("finish", summary=f"Read {file_id}."))

    model = FakeModel([read, write])
    result = run_agent(
        sample_inputs(
            now=datetime.fromisoformat(now),
            trigger=Trigger(kind="file", id=file_id),  # pyright: ignore[reportArgumentType]
            records=db,
            ids=iter(record_ids),
        ),
        model,
    )
    assert isinstance(result, RunSaved), getattr(result, "error", result)
    return result


def charge_run(line: str, now: str, db: list[Record]) -> RunSaved:
    key = line.lower()
    link, budget, allowable = (
        BY_ID[f"rec-link-{key}"],
        BY_ID[f"rec-budget-{key}"],
        BY_ID[f"rec-allowable-{key}"],
    )
    ld, bd, ad = link.data, budget.data, allowable.data

    def match(request: ModelRequest):
        return calls(
            tool(
                "link",
                record_id=ld.record_id,  # pyright: ignore[reportAttributeAccessIssue]
                charge_id=ld.charge_id,  # pyright: ignore[reportAttributeAccessIssue]
                amount_cents=ld.amount_cents,  # pyright: ignore[reportAttributeAccessIssue]
                default_item=ld.default_item,  # pyright: ignore[reportAttributeAccessIssue]
                reason=ld.reason,  # pyright: ignore[reportAttributeAccessIssue]
            ),
            tool(
                "assign_budget_line",
                charge_id=bd.charge_id,  # pyright: ignore[reportAttributeAccessIssue]
                budget_line_id=bd.record_id,  # pyright: ignore[reportAttributeAccessIssue]
                reason=bd.reason,  # pyright: ignore[reportAttributeAccessIssue]
            ),
            tool("finish", summary="Linked and assigned."),
        )

    def answer(request: ModelRequest):
        finish = results_of(request)[-1]
        assert finish["is_error"] and "allowable" in finish["content"], finish
        return calls(
            tool(
                "answer",
                charge_id=ad.charge_id,  # pyright: ignore[reportAttributeAccessIssue]
                question="allowable",
                answer="supports",
                reasoning=ad.reasoning,  # pyright: ignore[reportAttributeAccessIssue]
                quotes=[{"record_id": ld.record_id, "field": "description"}],  # pyright: ignore[reportAttributeAccessIssue]
                rests_on=ad.rests_on,  # pyright: ignore[reportAttributeAccessIssue]
            ),
            tool("finish", summary="Answered allowable."),
        )

    charge_id = f"chg-{key}"
    result = run_agent(
        sample_inputs(
            now=datetime.fromisoformat(now),
            trigger=Trigger(kind="charge", id=charge_id),  # pyright: ignore[reportArgumentType]
            records=db,
            ids=iter([link.id, budget.id, allowable.id]),
            charge_ids=[charge_id],
        ),
        FakeModel([match, answer]),
    )
    assert isinstance(result, RunSaved), getattr(result, "error", result)
    return result


def test_sample_grant_replays_through_the_agent():
    db: list[Record] = []
    produced: list[Record] = []

    def run(result: RunSaved) -> None:
        db.extend(result.records)
        produced.extend(result.records)

    terms = [r.id for r in SAMPLE.records[:10]]
    run(file_run("file-award-letter", terms, "2023-01-12T15:00:00+00:00", db))
    db.append(BY_ID["rec-confirm-award-terms"])
    run(file_run("file-invoice-1001", ["rec-bill-inv-1001"], "2025-11-12T18:00:00+00:00", db))
    run(charge_run("L-1001", "2025-11-14T00:00:00+00:00", db))
    run(
        file_run(
            "file-sequencing-statement", ["rec-bill-seq-0207"], "2026-02-21T17:30:00+00:00", db
        )
    )
    run(charge_run("L-1002", "2026-02-24T00:00:00+00:00", db))
    run(
        file_run("file-extension-notice", ["rec-period-extension"], "2026-04-09T16:00:00+00:00", db)
    )
    db.append(BY_ID["rec-confirm-extension"])

    expected = [r for r in SAMPLE.records if r.author == Author.AGENT]
    assert [r.id for r in produced] == [r.id for r in expected]
    for got, want in zip(produced, expected, strict=True):
        assert got.model_dump() == want.model_dump(), got.id

    # Every record passes the write check when the whole grant is replayed in order.
    for i, r in enumerate(db):
        assert (
            check_new_record(
                r, db[:i], SAMPLE.charges, SAMPLE.files, default_items=SAMPLE.sample_default_items
            )
            == []
        )
