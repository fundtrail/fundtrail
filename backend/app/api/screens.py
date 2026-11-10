"""The one screen body the contracts don't have yet.

The screens' bodies come from `app/contracts/api.py` (#39). The clock also says whether the
agent is still catching up after a jump (decision 0023: "The screen shows the new date at
once and that the agent is catching up"); `ClockView` adds that to the contracts' `Clock`
and can move there under the same name.
"""

from app.contracts.api import Clock


class ClockView(Clock):
    """GET and POST /workspaces/{workspace_id}/clock."""

    catching_up: bool = False  # the agent is still working through arrivals the clock passed
