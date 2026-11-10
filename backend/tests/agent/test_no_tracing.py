"""The agent refuses to run with LangSmith tracing turned on (issues #82 and #97)."""

import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

import pytest
from langsmith import utils as ls_utils

from app.agent import (
    AgentRunFailed,
    TracingTurnedOn,
    check_no_tracing,
    no_tracing,
    run_agent,
    run_once,
)
from app.agent import graph as graph_module
from app.agent.no_tracing import TRACING_VARIABLES
from app.contracts.runs import Trigger

from .fakes import FakeModel, message, sample_inputs, text

SECRET_LOOKING = "true-7f3c"  # a value that must never show up in an error


def clear_langsmith_cache() -> None:
    """langsmith caches what it read from the environment."""
    ls_utils.get_env_var.cache_clear()  # pyright: ignore[reportAttributeAccessIssue, reportFunctionMemberAccess]


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch):
    for name in TRACING_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    clear_langsmith_cache()
    yield
    clear_langsmith_cache()


@pytest.mark.parametrize("name", TRACING_VARIABLES)
@pytest.mark.parametrize("value", ["true", "True", "1", "yes", SECRET_LOOKING])
def test_each_tracing_variable_stops_the_agent_and_is_named_without_its_value(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
):
    monkeypatch.setenv(name, value)
    with pytest.raises(TracingTurnedOn) as refused:
        check_no_tracing()
    error = str(refused.value)
    assert name in error
    assert value not in error.replace("LangSmith tracing turned on", "")
    assert SECRET_LOOKING not in error


@pytest.mark.parametrize("value", ["", " ", "0", "false", "False", "FALSE", "no", "off"])
def test_a_variable_set_to_false_is_fine(monkeypatch: pytest.MonkeyPatch, value: str):
    for name in no_tracing._ON_UNLESS_FALSE:  # pyright: ignore[reportPrivateUsage]
        monkeypatch.setenv(name, value)
    check_no_tracing()


@pytest.mark.parametrize("value", ["", "0", "false", "False"])
@pytest.mark.parametrize("name", ["LANGCHAIN_TRACING", "LANGCHAIN_HANDLER"])
def test_langchains_own_switches_are_off_only_the_way_langchain_reads_them(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
):
    monkeypatch.setenv(name, value)
    check_no_tracing()


@pytest.mark.parametrize("value", ["no", "off", "FALSE"])
@pytest.mark.parametrize("name", ["LANGCHAIN_TRACING", "LANGCHAIN_HANDLER"])
def test_langchain_counts_these_values_as_set_so_they_are_refused(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
):
    """langchain_core's env_var_is_set counts anything but "", "0", "false", "False" as set."""
    from langchain_core.utils.env import env_var_is_set

    monkeypatch.setenv(name, value)
    assert env_var_is_set(name)
    with pytest.raises(TracingTurnedOn):
        check_no_tracing()


@pytest.mark.parametrize("name", ["LANGSMITH_TRACING_MODE", "LANGCHAIN_TRACING_MODE"])
@pytest.mark.parametrize("value", ["langsmith", "otel", "hybrid"])
def test_a_tracing_mode_of_any_kind_is_refused(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
):
    monkeypatch.setenv(name, value)
    with pytest.raises(TracingTurnedOn) as refused:
        check_no_tracing()
    assert name in str(refused.value) and value not in str(refused.value)


def test_the_refusal_is_a_run_failure_that_isnt_retried(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LANGSMITH_TRACING", SECRET_LOOKING)
    with pytest.raises(AgentRunFailed) as refused:
        check_no_tracing()
    assert isinstance(refused.value, TracingTurnedOn) and refused.value.retryable is False
    assert SECRET_LOOKING not in refused.value.log.decode()


def test_every_variable_that_is_on_is_named(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    assert no_tracing.tracing_variables_on() == ["LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING"]


@pytest.mark.parametrize(
    "name",
    ["LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING", "LANGCHAIN_TRACING"],
)
def test_the_list_covers_what_langsmith_itself_reads(monkeypatch: pytest.MonkeyPatch, name: str):
    """Each of these turns langsmith's own tracing on, so the check has to cover it."""
    assert ls_utils.tracing_is_enabled() is False
    monkeypatch.setenv(name, "true")
    clear_langsmith_cache()
    assert ls_utils.tracing_is_enabled() is True
    assert name in TRACING_VARIABLES


def _inputs():
    return sample_inputs(
        now=datetime.fromisoformat("2025-11-12T18:00:00+00:00"),
        trigger=Trigger(kind="file", id="file-invoice-1001"),  # pyright: ignore[reportArgumentType]
        records=[],
    )


def test_a_run_is_refused_before_any_langgraph_call(monkeypatch: pytest.MonkeyPatch):
    def no_graph(*args: Any, **kwargs: Any):
        raise AssertionError("LangGraph was called")

    monkeypatch.setattr(graph_module, "build_graph", no_graph)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    model = FakeModel([])
    with pytest.raises(TracingTurnedOn):
        run_once(_inputs(), model)
    assert model.requests == []


def test_the_platforms_entry_point_refuses_too(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    with pytest.raises(TracingTurnedOn):
        run_agent(object(), FakeModel([]))  # refused before the input is even read


def test_tracing_is_also_off_in_code_during_a_run(monkeypatch: pytest.MonkeyPatch):
    """The second guard: even if the environment check were bypassed, a run doesn't trace."""
    monkeypatch.setattr(graph_module, "check_no_tracing", lambda: None)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    clear_langsmith_cache()
    seen: list[bool | str] = []

    def step(request: Any):
        seen.append(ls_utils.tracing_is_enabled())
        return message(text("Done."))

    run_once(_inputs(), FakeModel([step]))
    assert seen == [False]


# Tracing turned on in code, by a caller (issue #97).


class _StandIn(BaseHTTPRequestHandler):
    """A local stand-in for the LangSmith endpoint: it keeps every request body."""

    bodies: ClassVar[list[bytes]] = []

    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if body[:4] == b"\x28\xb5\x2f\xfd":  # zstd
            import zstandard

            body = zstandard.ZstdDecompressor().decompressobj().decompress(body)
        _StandIn.bodies.append(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    do_GET = do_POST = do_PATCH = _answer

    def log_message(self, format: str, *args: Any) -> None:
        return None


@pytest.fixture
def stand_in_endpoint():
    _StandIn.bodies = []
    server = HTTPServer(("127.0.0.1", 0), _StandIn)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_a_caller_that_turns_tracing_on_in_code_is_refused_and_no_evidence_is_sent(
    monkeypatch: pytest.MonkeyPatch, stand_in_endpoint: str
):
    """The reviewer's case: the caller's own span, inside tracing_context(enabled=True)."""
    from langsmith import Client, traceable, tracing_context

    from .fakes import calls, tool
    from .test_platform import CHARGE, agent_input, records_until

    monkeypatch.setenv("LANGSMITH_DISABLE_RUN_COMPRESSION", "true")
    clear_langsmith_cache()
    client = Client(api_url=stand_in_endpoint, api_key="local-stand-in-not-a-key")
    model = FakeModel(
        [
            lambda r: calls(
                tool(
                    "link",
                    record_id="rec-bill-inv-1001",
                    charge_id="chg-l-1001",
                    amount_cents=124000,
                    default_item="bill",
                ),
                tool(
                    "assign_budget_line",
                    charge_id="chg-l-1001",
                    budget_line_id="rec-budget-materials-and-supplies",
                    reason="Lab supplies.",
                ),
                tool(
                    "answer",
                    charge_id="chg-l-1001",
                    question="allowable",
                    answer="supports",
                    reasoning="Supplies.",
                ),
                tool("finish", summary="Linked."),
            )
        ]
    )
    work = agent_input(CHARGE, "2025-11-14T00:00:00+00:00", records_until("rec-link-l-1001"))

    @traceable(client=client, name="caller")
    def caller() -> Any:
        return run_agent(work, model)

    refused: TracingTurnedOn | None = None
    with tracing_context(enabled=True, client=client):
        try:
            caller()
        except TracingTurnedOn as error:
            refused = error
    client.flush()
    sent = b"".join(_StandIn.bodies)
    assert sent, "the stand-in received the caller's own span"
    for evidence in (b"Total Due", b"INV-1001", b"Sediment core liners", b"1,240.00"):
        assert evidence not in sent, evidence
    assert refused is not None and model.requests == []
    assert "tracing_is_enabled" in str(refused) or "run tree" in str(refused)


def test_an_open_run_tree_alone_is_refused():
    from langsmith import tracing_context
    from langsmith.run_trees import RunTree

    with (
        tracing_context(enabled=False, parent=RunTree(name="caller")),
        pytest.raises(TracingTurnedOn),
    ):
        check_no_tracing()
