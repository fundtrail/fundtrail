"""The agent refuses to run with LangSmith tracing turned on (issue #82)."""

from datetime import datetime
from typing import Any

import pytest
from langsmith import utils as ls_utils

from app.agent import TracingTurnedOn, check_no_tracing, no_tracing, run_agent, run_once
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
    for name in TRACING_VARIABLES:
        monkeypatch.setenv(name, value)
    check_no_tracing()


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
