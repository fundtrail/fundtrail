"""The agent (W1): reads evidence, writes cited records and links, answers the questions code
asks, and suggests changes the accountant decides.

    from app.agent import RunInputs, run_agent

`run_agent(inputs)` returns the records to save (RunSaved) or a failure (RunFailed). Saving to the
database and queuing jobs are W4's. The model is claude-opus-5-5, with no fallback.
"""

from .graph import recheck_before_save, run_agent
from .inputs import CHARGE_BATCH_SIZE, RunFailed, RunInputs, RunResult, RunSaved, batch_charge_ids

__all__ = [
    "CHARGE_BATCH_SIZE",
    "RunFailed",
    "RunInputs",
    "RunResult",
    "RunSaved",
    "batch_charge_ids",
    "recheck_before_save",
    "run_agent",
]
