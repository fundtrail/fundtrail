"""No code turns LangSmith tracing on (#82): the startup check covers the environment, and
this covers the code. It fails if `traceable` or `tracing_context(enabled=True)` appears
anywhere in the backend's code outside the agent's guard (app/agent/no_tracing.py), which
names them to refuse them."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
GUARD = APP / "agent" / "no_tracing.py"
FORBIDDEN = re.compile(r"\btraceable\b|tracing_context\(\s*enabled\s*=\s*True")


def test_no_code_turns_tracing_on() -> None:
    found = [
        f"{path.relative_to(APP.parent)}:{n}"
        for path in APP.rglob("*.py")
        if path != GUARD
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if FORBIDDEN.search(line)
    ]
    assert found == [], f"tracing turned on in code: {found}"
