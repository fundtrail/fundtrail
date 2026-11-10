"""The agent (W1): reads evidence, writes cited records and links, answers the questions code
asks, and suggests changes the accountant decides.

    from app.agent import run_agent

`run_agent(agent_input)` is what the platform (#25) calls: it returns the records and thread
messages to save (AgentResult) or raises AgentRunFailed, and nothing is saved. `run_once` is the
same run on the agent's own inputs. The model is claude-opus-5-5, with no fallback.
"""

from .graph import recheck_before_save, run_once
from .inputs import CHARGE_BATCH_SIZE, RunFailed, RunInputs, RunResult, RunSaved
from .platform import AgentResult, AgentRunFailed, charges_for_run, run_agent

__all__ = [
    "CHARGE_BATCH_SIZE",
    "AgentResult",
    "AgentRunFailed",
    "RunFailed",
    "RunInputs",
    "RunResult",
    "RunSaved",
    "charges_for_run",
    "recheck_before_save",
    "run_agent",
    "run_once",
]
