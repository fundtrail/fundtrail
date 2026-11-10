"""A fake model and fake checks, so the agent's tests never need the API key.

The fake model is a script: one function per model turn, each given the request and returning an
assistant message built from the SDK's own types. Citations are built the way the API returns
them: a char_location over a chunk of the document text sent in the request, with the document's
index counted across every document in the request.
"""

import re
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime
from itertools import count
from typing import Any

from anthropic.types import CitationCharLocation, Message, TextBlock, ToolUseBlock, Usage

from app.agent.inputs import RunInputs
from app.agent.model import ModelRequest
from app.contracts.charges import Charge
from app.contracts.checks import (
    ChargeStatus,
    ChecklistEntry,
    ChecksInput,
    ChecksOutput,
    OpenQuestion,
)
from app.contracts.fixtures import DOCUMENTS_DIR, SampleGrant, load_sample_grant
from app.contracts.records import Author, Judgment, Link, Question, Record
from app.contracts.rules import RecordState
from app.contracts.runs import Trigger

Step = Callable[[ModelRequest], Message]
_ids = count(1)


def message(*content: Any, stop: str = "end_turn") -> Message:
    return Message(
        id=f"msg_{next(_ids)}",
        type="message",
        role="assistant",
        model="claude-opus-5-5",
        content=list(content),
        stop_reason=stop,  # pyright: ignore[reportArgumentType]
        stop_sequence=None,
        usage=Usage(input_tokens=10, output_tokens=5),
    )


def text(value: str, citations: list[Any] | None = None) -> TextBlock:
    return TextBlock(type="text", text=value, citations=citations)


def tool(name: str, **args: Any) -> ToolUseBlock:
    return ToolUseBlock(type="tool_use", id=f"toolu_{next(_ids)}", name=name, input=args)


def calls(*blocks: ToolUseBlock) -> Message:
    return message(*blocks, stop="tool_use")


def documents_in(request: ModelRequest) -> list[dict[str, Any]]:
    """Every document block in the request, in order: the API's document_index counts these."""
    found: list[dict[str, Any]] = []

    def walk(content: Any) -> None:
        if isinstance(content, list):
            for block in content:  # pyright: ignore[reportUnknownVariableType]
                walk(block)
        elif isinstance(content, dict):
            if content.get("type") == "document":
                found.append(content)  # pyright: ignore[reportUnknownArgumentType]
            elif content.get("type") == "tool_result":
                walk(content.get("content"))  # pyright: ignore[reportUnknownMemberType]

    for m in request.messages:
        walk(m["content"])
    return found


def cite(request: ModelRequest, file_id: str, chunk: str) -> CitationCharLocation:
    """A char_location citation of `chunk` in the last document sent for `file_id`."""
    docs = documents_in(request)
    index = max(i for i, d in enumerate(docs) if f"({file_id})" in d["title"])
    data = docs[index]["source"]["data"]
    start = data.find(chunk)
    assert start >= 0, f"{chunk!r} isn't in {file_id}"
    return CitationCharLocation(
        type="char_location",
        cited_text=chunk,
        document_index=index,
        document_title=docs[index]["title"],
        start_char_index=start,
        end_char_index=start + len(chunk),
    )


def label_message(request: ModelRequest, lines: Sequence[tuple[str, str, str, str]]) -> Message:
    """One message of label lines: (label, value text, file ID, the chunk the API cites)."""
    blocks: list[Any] = []
    for label, value, file_id, chunk in lines:
        blocks.append(text(f"@{label}: "))
        blocks.append(text(value, [cite(request, file_id, chunk)]))
        blocks.append(text("\n"))
    return message(*blocks)


def api_chunk(document: str, passage: str, value: str) -> str:
    """The chunk the fake API cites for a value whose exact passage is `passage`.

    Like the real API, it cites a whole paragraph, unless the passage isn't a whole line or the
    value appears more than once in the paragraph; then it cites the passage itself.
    """
    start = document.find(passage)
    line_start = document.rfind("\n", 0, start) + 1
    line_end = document.find("\n", start)
    line = document[line_start : line_end if line_end >= 0 else len(document)].strip()
    if line != passage:
        return passage
    para_start = document.rfind("\n\n", 0, start)
    para_start = 0 if para_start < 0 else para_start + 2
    para_end = document.find("\n\n", start)
    paragraph = document[para_start : para_end if para_end >= 0 else len(document)]
    return passage if paragraph.count(value) != 1 else paragraph


class FakeModel:
    def __init__(self, steps: Sequence[Step]):
        self.steps = list(steps)
        self.requests: list[ModelRequest] = []

    def __call__(self, request: ModelRequest) -> Message:
        # The agent keeps appending to its history, so keep a copy of what this request held.
        request = ModelRequest(**{**request.__dict__, "messages": list(request.messages)})
        self.requests.append(request)
        assert self.steps, "the fake model ran out of scripted turns"
        return self.steps.pop(0)(request)


def results_of(request: ModelRequest) -> list[dict[str, Any]]:
    """The tool results in the request's last message."""
    content = request.messages[-1]["content"]
    return (
        [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
        if isinstance(content, list)
        else []
    )


# Checks: a stand-in for W2's run_checks, enough for the sample grant.


def sample_checks(sample: SampleGrant) -> Callable[[ChecksInput], ChecksOutput]:
    def run(inp: ChecksInput) -> ChecksOutput:
        state = RecordState(inp.records, inp.files)
        current = state.current()
        statuses: list[ChargeStatus] = []
        questions: list[OpenQuestion] = []
        for c in inp.charges:
            links = [r for r in current if isinstance(r.data, Link) and r.data.charge_id == c.id]
            entries = [
                ChecklistEntry(
                    default_item=d.key,
                    added_by="default",  # pyright: ignore[reportArgumentType]
                    needed=d.needed,
                    amount_cents=d.amount_cents,
                    filled=any(
                        isinstance(r.data, Link) and r.data.default_item == d.key for r in links
                    ),
                    link_ids=tuple(r.id for r in links),
                )
                for d in sample.default_items.get(c.ledger_line_id, [])
            ]
            filled = all(e.filled for e in entries) and bool(entries)
            statuses.append(
                ChargeStatus(
                    grant_id=c.grant_id,
                    charge_id=c.id,
                    bucket="evidence_complete" if filled else "missing_evidence",  # pyright: ignore[reportArgumentType]
                    reasons=(),
                    checklist=tuple(entries),
                    flagged=False,
                )
            )
            answered = any(
                isinstance(r.data, Judgment)
                and r.data.charge_id == c.id
                and r.data.question == Question.ALLOWABLE
                for r in current
            )
            if links and not answered:
                questions.append(
                    OpenQuestion(
                        charge_id=c.id, question=Question.ALLOWABLE, answer_by=Author.AGENT
                    )
                )
        return ChecksOutput(
            charges=tuple(statuses), records=(), grants=(), questions=tuple(questions), notes=()
        )

    return run


# The run's read point in these tests (call 40): it read everything stored.
RUN_READ_THROUGH = 10**9


def sample_inputs(
    *,
    now: datetime,
    trigger: Trigger,
    records: Sequence[Record],
    ids: Iterator[str] | None = None,
    charge_ids: Sequence[str] = (),
    run_id: str = "run-1",
    read_through_seq: int | None = RUN_READ_THROUGH,
    **extra: Any,
) -> RunInputs:
    """Run inputs on the sample grant, with what's visible at `now`."""
    sample = load_sample_grant()
    charges: list[Charge] = [c for c in sample.charges if c.arrived_at <= now]
    files = [f for f in sample.files if f.arrived_at <= now]
    fresh = count(1)
    return RunInputs(
        run_id=run_id,
        grant=sample.grant,
        now=now,
        trigger=trigger,
        records=list(records),
        charges=charges,
        files=files,
        read_file=lambda f: (DOCUMENTS_DIR / f.name).read_bytes(),
        default_items=sample.sample_default_items,
        run_checks=sample_checks(sample),
        charge_ids=charge_ids,
        new_id=(lambda: next(ids)) if ids is not None else (lambda: f"rec-new-{next(fresh)}"),
        read_through_seq=read_through_seq,
        **extra,
    )


def label_for(record_id: str, path: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", f"{record_id}__{path}")


def document_text(sample: SampleGrant, file_id: str) -> str:
    return sample.document(file_id)
