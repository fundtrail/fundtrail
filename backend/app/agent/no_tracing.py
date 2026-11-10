"""The agent refuses to run with LangSmith tracing turned on (issues #82 and #97).

langsmith comes in with langgraph. With tracing on, it sends each run's state, evidence file
contents included, to a third party. So before any LangGraph or langsmith call the agent checks,
and refuses with an error that names what turned tracing on and prints no value.

Tracing can be turned on two ways, and both are refused:

- **In the environment.** The variables, read from langsmith 0.14 and langchain_core 1.7:
  - `LANGSMITH_TRACING_V2`, `LANGCHAIN_TRACING_V2`, `LANGSMITH_TRACING`, `LANGCHAIN_TRACING`:
    what `langsmith.utils.tracing_is_enabled` reads. langchain_core's tracer uses it too.
  - `LANGCHAIN_HANDLER`, and `LANGCHAIN_TRACING` again: langchain_core's old switch. It counts
    them as set unless they're "", "0", "false" or "False" (`env_var_is_set`), so they're read
    the same way here: "no" or "FALSE" still counts as set.
  - `LANGSMITH_OTEL_ENABLED`, `LANGCHAIN_OTEL_ENABLED`, `LANGSMITH_OTEL_ONLY`,
    `LANGCHAIN_OTEL_ONLY`: send traces through OpenTelemetry.
  - `LANGSMITH_TRACING_MODE`, `LANGCHAIN_TRACING_MODE`: where traces go. Any value is refused.
  The other variables count as on unless they're empty or plainly false ("0", "false", "no",
  "off"), which is stricter than langsmith's own "true".
- **In code.** A caller can turn tracing on around the agent, for example its own `@traceable`
  inside `tracing_context(enabled=True)`. Then its span would carry what the agent returns. So
  the agent also refuses when `langsmith.utils.tracing_is_enabled()` is true or a run tree is
  current.

Runs also go through `langsmith.tracing_context(enabled=False)`, which turns the agent's own
spans off in code as a second guard.

The refusal is an AgentRunFailed that isn't retryable: nothing is saved, and trying again
can't help until the environment or the caller changes.
"""

import json
import os
from collections.abc import Mapping

from .inputs import AgentRunFailed

# Counted on unless empty or plainly false.
_ON_UNLESS_FALSE = (
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_TRACING",
    "LANGSMITH_OTEL_ENABLED",
    "LANGCHAIN_OTEL_ENABLED",
    "LANGSMITH_OTEL_ONLY",
    "LANGCHAIN_OTEL_ONLY",
)
# Counted as set the way langchain_core's env_var_is_set reads them.
_SET_LIKE_LANGCHAIN = ("LANGCHAIN_TRACING", "LANGCHAIN_HANDLER")
# Any value at all.
_ANY_VALUE = ("LANGSMITH_TRACING_MODE", "LANGCHAIN_TRACING_MODE")

TRACING_VARIABLES = (*_ON_UNLESS_FALSE, *_SET_LIKE_LANGCHAIN, *_ANY_VALUE)

_OFF = frozenset({"", "0", "false", "no", "off", "n", "f"})
_LANGCHAIN_UNSET = frozenset({"", "0", "false", "False"})


class TracingTurnedOn(AgentRunFailed):
    """LangSmith tracing is turned on, so the agent won't run. Not retryable."""

    def __init__(self, error: str):
        log = json.dumps({"outcome": "refused", "error": error}).encode("utf-8")
        super().__init__(error, retryable=False, log=log)


def tracing_variables_on(environ: Mapping[str, str] | None = None) -> list[str]:
    """The names of the tracing variables that are turned on, in list order. Never their values."""
    env = os.environ if environ is None else environ
    on: list[str] = []
    for name in TRACING_VARIABLES:
        value = env.get(name, "")
        if name in _SET_LIKE_LANGCHAIN:
            is_on = value not in _LANGCHAIN_UNSET or value.strip().lower() not in _OFF
        elif name in _ANY_VALUE:
            is_on = value.strip() != ""
        else:
            is_on = value.strip().lower() not in _OFF
        if is_on:
            on.append(name)
    return on


def tracing_on_in_code() -> list[str]:
    """What turns tracing on in this process outside the environment: a caller's tracing context
    or global setting, or a run tree it has open."""
    from langsmith import run_helpers
    from langsmith import utils as ls_utils

    found: list[str] = []
    if run_helpers.get_current_run_tree() is not None:
        found.append("a LangSmith run tree is open around the agent")
    if ls_utils.tracing_is_enabled():
        found.append("langsmith.utils.tracing_is_enabled() is true")
    return found


def check_no_tracing(environ: Mapping[str, str] | None = None) -> None:
    """Refuse to run if LangSmith tracing is turned on, in the environment or in code.

    Call it before any LangGraph call. The platform can also call it at startup.
    """
    names = tracing_variables_on(environ)
    if names:
        raise TracingTurnedOn(
            "The agent won't run with LangSmith tracing turned on, because tracing would send "
            "evidence to a third party. Unset "
            + ", ".join(names)
            + " in the backend's environment."
        )
    in_code = tracing_on_in_code()
    if in_code:
        raise TracingTurnedOn(
            "The agent won't run with LangSmith tracing turned on, because tracing would send "
            "evidence to a third party: "
            + "; ".join(in_code)
            + ". Call the agent outside any tracing context."
        )
