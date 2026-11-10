"""Which screen pings go out, on which channel.

Two private channels:

- `grant:{grant_id}`: everything a grant's screens show.
  - event `changed`, payload `{"grant_id", "what": [...]}` where `what` names the
    parts to refetch: `charges`, `evidence`, `records`, `statuses`, `thread`.
  - event `run`, payload `{"grant_id", "run_id", "status", "trigger": {"kind", "id"}}`,
    each time a run is queued, starts, saves, is retried or fails. It drives the
    "agent is busy" notice.
- `workspace:{workspace_id}`: the grant list. Event `changed`, payload `{"grant_id"}`,
  when a grant is added or its statuses change.

Pings are sent after the transaction commits, so a refetch sees the change.
"""

from __future__ import annotations

from app.contracts.runs import AgentRun

from .ports import Pinger


def grant_topic(grant_id: str) -> str:
    return f"grant:{grant_id}"


def workspace_topic(workspace_id: str) -> str:
    return f"workspace:{workspace_id}"


def ping_changed(pinger: Pinger, workspace_id: str, grant_id: str, *what: str) -> None:
    pinger.ping(grant_topic(grant_id), "changed", {"grant_id": grant_id, "what": sorted(set(what))})
    if "statuses" in what or not what:
        pinger.ping(workspace_topic(workspace_id), "changed", {"grant_id": grant_id})


def ping_run(pinger: Pinger, run: AgentRun) -> None:
    pinger.ping(
        grant_topic(run.grant_id),
        "run",
        {
            "grant_id": run.grant_id,
            "run_id": run.id,
            "status": run.status.value,
            "trigger": {"kind": run.trigger.kind.value, "id": run.trigger.id},
        },
    )
