"""The agent refuses to run with LangSmith tracing turned on (issue #82).

langsmith comes in with langgraph. With tracing on, it sends each run's state, evidence file
contents included, to a third party. So before any LangGraph or langsmith call the agent checks
the environment, and refuses with an error that names the variable and prints no value.

The variables, read from langsmith 0.14 and langchain_core 1.7:

- `LANGSMITH_TRACING_V2`, `LANGCHAIN_TRACING_V2`, `LANGSMITH_TRACING`, `LANGCHAIN_TRACING`: what
  `langsmith.utils.tracing_is_enabled` reads (`get_env_var("TRACING_V2")`, then `"TRACING"`, in
  both namespaces). langchain_core's tracer uses the same function.
- `LANGCHAIN_HANDLER`: langchain_core's old way to turn tracing on.
- `LANGSMITH_OTEL_ENABLED`, `LANGCHAIN_OTEL_ENABLED`, `LANGSMITH_OTEL_ONLY`, `LANGCHAIN_OTEL_ONLY`:
  send traces through OpenTelemetry instead of, or as well as, LangSmith.

A variable counts as on unless it's empty or plainly false ("0", "false", "no", "off"). That's
stricter than langsmith, which turns tracing on only for "true", so a value langsmith would
read differently in a later version is still refused. Runs also go through
`langsmith.tracing_context(enabled=False)`, which turns tracing off in code as a second guard.
"""

import os
from collections.abc import Mapping

TRACING_VARIABLES = (
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING",
    "LANGCHAIN_HANDLER",
    "LANGSMITH_OTEL_ENABLED",
    "LANGCHAIN_OTEL_ENABLED",
    "LANGSMITH_OTEL_ONLY",
    "LANGCHAIN_OTEL_ONLY",
)

_OFF = frozenset({"", "0", "false", "no", "off", "n", "f"})


class TracingTurnedOn(RuntimeError):
    """LangSmith tracing is turned on in the environment, so the agent won't run."""


def tracing_variables_on(environ: Mapping[str, str] | None = None) -> list[str]:
    """The names of the tracing variables that are turned on. Never their values."""
    env = os.environ if environ is None else environ
    return [name for name in TRACING_VARIABLES if env.get(name, "").strip().lower() not in _OFF]


def check_no_tracing(environ: Mapping[str, str] | None = None) -> None:
    """Refuse to run if LangSmith tracing is turned on in the environment.

    Call it before any LangGraph or langsmith call. The platform can also call it at startup.
    """
    names = tracing_variables_on(environ)
    if names:
        raise TracingTurnedOn(
            "The agent won't run with LangSmith tracing turned on, because tracing would send "
            "evidence to a third party. Unset "
            + ", ".join(names)
            + " in the backend's environment."
        )
