"""The run as a whole: the loop, the gate, failures, the debug log, and the call to the model."""

from datetime import datetime
from typing import Any

import anthropic
import httpx2
import pytest

from app.agent import RunFailed, RunSaved, run_once
from app.agent.adapter import debug_log_path
from app.agent.graph import MAX_GATE_RETURNS
from app.agent.model import MODEL, AnthropicModel, ModelRequest
from app.agent.prompts import SYSTEM_PROMPT
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import Record
from app.contracts.runs import Trigger
from app.contracts.threads import ThreadMessage

from .fakes import FakeModel, calls, label_message, message, results_of, sample_inputs, text, tool

SAMPLE = load_sample_grant()


def records_until(record_id: str) -> list[Record]:
    out: list[Record] = []
    for r in SAMPLE.records:
        if r.id == record_id:
            break
        out.append(r)
    return out


def charge_inputs(
    until: str = "rec-link-l-1001", now: str = "2025-11-14T00:00:00+00:00", **extra: Any
):
    return sample_inputs(
        now=datetime.fromisoformat(now),
        trigger=Trigger(kind="charge", id="chg-l-1001"),  # pyright: ignore[reportArgumentType]
        records=records_until(until),
        charge_ids=["chg-l-1001"],
        **extra,
    )


def link_l1001():
    return tool(
        "link",
        record_id="rec-bill-inv-1001",
        charge_id="chg-l-1001",
        amount_cents=124000,
        default_item="bill",
    )


def assign_l1001():
    return tool(
        "assign_budget_line",
        charge_id="chg-l-1001",
        budget_line_id="rec-budget-materials-and-supplies",
        reason="Sediment core liners are lab supplies.",
    )


def answer_l1001(charge: str = "chg-l-1001"):
    return tool(
        "answer",
        charge_id=charge,
        question="allowable",
        answer="supports",
        reasoning="Lab supplies.",
    )


def test_a_run_ends_only_when_no_question_waits_for_the_agent():
    model = FakeModel(
        [
            lambda r: calls(link_l1001(), assign_l1001(), tool("finish", summary="Linked.")),
            lambda r: calls(answer_l1001(), tool("finish", summary="Linked and answered.")),
        ]
    )
    result = run_once(charge_inputs(), model)
    assert isinstance(result, RunSaved)
    assert [r.kind for r in result.records] == ["link", "budget_assignment", "judgment"]
    assert result.summary == "Linked and answered."
    finish = results_of(model.requests[1])[-1]
    assert finish["is_error"] and "allowable on charge chg-l-1001" in finish["content"]


def test_a_turn_with_no_tool_call_and_no_labels_counts_as_done():
    model = FakeModel([lambda r: message(text("Nothing to do here."))])
    result = run_once(charge_inputs(until="rec-bill-seq-0207"), model)
    assert isinstance(result, RunSaved) and result.records == []


def test_label_lines_get_codes_reply_and_the_run_goes_on():
    def read(request: ModelRequest):
        return label_message(
            request, [("total", "$1,240.00", "file-invoice-1001", "Total Due: $1,240.00")]
        )

    def write(request: ModelRequest):
        assert request.messages[-1]["content"] == "Recorded with citations: total."
        return calls(
            tool("write_fact", kind="bill", values=[{"field": "total", "label": "total"}]),
            tool("finish", summary="Read it."),
        )

    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-12T18:00:00+00:00"),
        trigger=Trigger(kind="file", id="file-invoice-1001"),  # pyright: ignore[reportArgumentType]
        records=records_until("rec-bill-inv-1001"),
    )
    result = run_once(inputs, FakeModel([read, write]))
    assert isinstance(result, RunSaved) and [r.kind for r in result.records] == ["bill"]


def test_a_file_run_hands_over_the_file_and_the_award_notice_guidance():
    """Answer 9, and the file's missing checklist items."""
    model = FakeModel([lambda r: message(text("Done."))])
    inputs = sample_inputs(
        now=datetime.fromisoformat("2025-11-14T00:00:00+00:00"),
        trigger=Trigger(kind="file", id="file-invoice-1001"),  # pyright: ignore[reportArgumentType]
        records=records_until("rec-link-l-1001"),
    )
    run_once(inputs, model)
    first = model.requests[0].messages[0]["content"]
    joined = " ".join(b.get("text", "") for b in first)
    assert (
        "free-text conditions" in joined
        and "NSF category" in joined
        and "exactly one notice term" in joined
    )
    assert "Which of these does this file fill?" in joined and "chg-l-1001" in joined
    assert any(b.get("type") == "document" for b in first)


def test_a_thread_runs_gate_covers_only_its_charge():
    """Answer 3: other open questions are reported, so an ordinary run gets queued."""
    message_in = ThreadMessage(
        id="msg-1",
        workspace_id=SAMPLE.workspace.id,
        grant_id=SAMPLE.grant.id,
        charge_id="chg-l-1001",
        author="user",  # pyright: ignore[reportArgumentType]
        author_user_id=SAMPLE.user.id,
        text="Is this invoice the right one?",
        written_at=datetime.fromisoformat("2026-02-24T12:00:00+00:00"),
    )
    db = [r for r in records_until("rec-period-extension") if not r.id.startswith("rec-allowable")]
    inputs = sample_inputs(
        now=datetime.fromisoformat("2026-02-24T12:00:00+00:00"),
        trigger=Trigger(kind="thread_message", id="msg-1"),  # pyright: ignore[reportArgumentType]
        records=db,
        thread_messages=[message_in],
    )
    model = FakeModel(
        [
            lambda r: calls(
                tool(
                    "post_message",
                    charge_id="chg-l-1001",
                    text="Yes: INV-1001 matches the ledger reference.",
                ),
                answer_l1001(),
                tool("finish", summary="Replied."),
            )
        ]
    )
    result = run_once(inputs, model)
    assert isinstance(result, RunSaved)
    assert [q.charge_id for q in result.other_open_questions] == ["chg-l-1002"]
    assert [m.text for m in result.messages] == ["Yes: INV-1001 matches the ledger reference."]
    assert "Is this invoice the right one?" in model.requests[0].messages[0]["content"][-1]["text"]


def test_a_refusal_fails_the_run_with_no_other_model():
    """Answer 4."""
    model = FakeModel([lambda r: message(text(""), stop="refusal")])
    result = run_once(charge_inputs(), model)
    assert isinstance(result, RunFailed) and not result.retryable and "refusal" in result.error


def test_a_run_that_fails_saves_nothing_and_says_whether_to_retry():
    """All or nothing, and answer 7: the failure names its trigger for the problem list."""

    def boom(request: ModelRequest):
        raise anthropic.APIConnectionError(
            request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        )

    model = FakeModel([lambda r: calls(link_l1001()), boom])
    result = run_once(charge_inputs(), model)
    assert isinstance(result, RunFailed) and result.retryable
    assert result.trigger.id == "chg-l-1001"
    assert not hasattr(result, "records")

    def bad(request: ModelRequest):
        raise anthropic.BadRequestError(
            "bad",
            response=httpx2.Response(400, request=httpx2.Request("POST", "https://x.example")),
            body=None,
        )

    result = run_once(charge_inputs(), FakeModel([bad]))
    assert isinstance(result, RunFailed) and not result.retryable


def test_the_gate_sends_the_model_back_only_so_many_times():
    model = FakeModel(
        [lambda r: calls(link_l1001(), tool("finish", summary="x"))]
        + [lambda r: calls(tool("finish", summary="x"))] * MAX_GATE_RETURNS
    )
    result = run_once(charge_inputs(), model)
    assert isinstance(result, RunFailed) and "still waited" in result.error


def test_a_charge_run_needs_a_budget_line_or_a_flag_for_each_charge():
    """The main coordinator's ruling: a run can't finish without a budget line for each charge."""
    model = FakeModel(
        [
            lambda r: calls(tool("finish", summary="Nothing yet.")),
            lambda r: calls(
                tool(
                    "flag",
                    charge_id="chg-l-1001",
                    question="Which budget line does this belong to?",
                    reasoning="No bill on file says what was bought.",
                ),
                tool("finish", summary="Flagged."),
            ),
        ]
    )
    result = run_once(charge_inputs(until="rec-bill-inv-1001"), model)
    assert isinstance(result, RunSaved) and [r.kind for r in result.records] == ["judgment"]
    finish = results_of(model.requests[1])[-1]
    assert finish["is_error"] and "no budget line yet: chg-l-1001" in finish["content"]


def test_a_turn_cut_off_at_the_output_limit_is_asked_again_once():
    model = FakeModel(
        [lambda r: message(text("..."), stop="max_tokens"), lambda r: message(text("Done."))]
    )
    assert isinstance(run_once(charge_inputs(until="rec-bill-seq-0207"), model), RunSaved)
    assert model.requests[1].max_tokens > model.requests[0].max_tokens
    model = FakeModel([lambda r: message(text("..."), stop="max_tokens")] * 2)
    assert isinstance(run_once(charge_inputs(), model), RunFailed)


def test_each_run_keeps_one_debug_log():
    """Answer 5: one log per run, for private storage, referenced from the run."""
    result = run_once(
        charge_inputs(),
        FakeModel([lambda r: calls(link_l1001()), lambda r: message(text("Done?"))]),
    )
    assert result.log_path == debug_log_path(SAMPLE.workspace.id, SAMPLE.grant.id, "run-1")
    events = [e["event"] for e in result.log["events"]]
    assert (
        events[0] == "first_message"
        and "response" in events
        and "tool" in events
        and "gate" in events
    )
    assert result.log["model"] == MODEL and result.log["usage"]["input_tokens"] == 20
    assert len(result.log["prompt_sha256"]) == 64


def test_the_prompt_states_how_a_rules_kind_decides_the_answer():
    """Answer 10, as guidance."""
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "for a not-allowed rule, contradicts" in flat
    assert (
        "supports when a document shows the condition is met and contradicts when none does" in flat
    )
    assert "for a judgment rule, a flag rather than contradicts" in flat


class _Stream:
    def __init__(self, sent: dict[str, Any]):
        self.sent = sent

    def __enter__(self):
        return self

    def __exit__(self, *exc: Any):
        return False

    def get_final_message(self):
        return message(text("ok"))


class _Messages:
    def __init__(self):
        self.sent: dict[str, Any] = {}

    def stream(self, **kwargs: Any):
        self.sent = kwargs
        return _Stream(kwargs)


class _Client:
    def __init__(self):
        self.messages = _Messages()


def test_the_model_call_uses_only_claude_opus_5_5_with_no_fallback():
    """Answer 4: the request names one model and carries no fallbacks."""
    client = _Client()
    AnthropicModel(client)(  # pyright: ignore[reportArgumentType]
        ModelRequest(
            system=[{"type": "text", "text": "s"}],
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    sent = client.messages.sent
    assert sent["model"] == "claude-opus-5-5"
    assert "fallbacks" not in sent and "betas" not in sent
    assert sent["thinking"] == {"type": "adaptive"} and sent["output_config"] == {"effort": "high"}


@pytest.mark.parametrize("charges", [["chg-l-1001", "chg-l-1002"]])
def test_charges_that_arrive_together_come_in_one_run(charges: list[str]):
    """Answer 8: every charge in the batch is handed over in full."""
    inputs = sample_inputs(
        now=datetime.fromisoformat("2026-02-24T00:00:00+00:00"),
        trigger=Trigger(kind="charge", id=charges[0]),  # pyright: ignore[reportArgumentType]
        records=records_until("rec-link-l-1001"),
        charge_ids=charges,
    )
    model = FakeModel([lambda r: message(text("Done."))])
    run_once(inputs, model)
    trigger_text = model.requests[0].messages[0]["content"][-1]["text"]
    assert "2 charge(s)" in trigger_text and "L-1001" in trigger_text and "L-1002" in trigger_text
