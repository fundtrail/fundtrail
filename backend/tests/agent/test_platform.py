"""The agent as the platform (#25) calls it, with a stand-in for its AgentInput."""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from app.agent import AgentRunFailed, charges_for_run, run_agent
from app.contracts.charges import Charge
from app.contracts.checks import ChecksInput, ChecksOutput
from app.contracts.evidence import EvidenceFile
from app.contracts.fixtures import DOCUMENTS_DIR, load_sample_grant
from app.contracts.records import DefaultItem, Record
from app.contracts.runs import AgentRun, Trigger
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant

from .fakes import FakeModel, calls, message, sample_checks, text, tool

SAMPLE = load_sample_grant()


class Checks:
    def run_checks(self, checks_input: ChecksInput, /) -> ChecksOutput:
        return sample_checks(SAMPLE)(checks_input)

    def default_items(self, charge: Charge, records: Sequence[Record], /) -> Sequence[DefaultItem]:
        return SAMPLE.sample_default_items(charge, records)


@dataclass(frozen=True)
class AgentInput:
    """The platform's AgentInput, field for field (app/db/ports.py on #25)."""

    run: AgentRun
    grant: Grant
    charges: list[Charge]
    files: list[EvidenceFile]
    records: list[Record]
    thread: list[ThreadMessage]
    read_file: Callable[[EvidenceFile], bytes]
    checks: Any = field(default_factory=Checks)


def agent_input(
    trigger: Trigger, now: str, records: list[Record], charges: list[Charge] | None = None
) -> AgentInput:
    clock = datetime.fromisoformat(now)
    run = AgentRun(
        id="run-9",
        workspace_id=SAMPLE.workspace.id,
        grant_id=SAMPLE.grant.id,
        trigger=trigger,
        status="running",  # pyright: ignore[reportArgumentType]
        clock_now=clock,
        queued_at=clock,
        read_through_seq=10**9,  # the platform records it when the run starts (call 40)
    )
    return AgentInput(
        run=run,
        grant=SAMPLE.grant,
        charges=charges
        if charges is not None
        else [c for c in SAMPLE.charges if c.arrived_at <= clock],
        files=[f for f in SAMPLE.files if f.arrived_at <= clock],
        records=records,
        thread=[],
        read_file=lambda f: (DOCUMENTS_DIR / f.name).read_bytes(),
    )


def records_until(record_id: str) -> list[Record]:
    out: list[Record] = []
    for r in SAMPLE.records:
        if r.id == record_id:
            break
        out.append(r)
    return out


CHARGE = Trigger(kind="charge", id="chg-l-1001")  # pyright: ignore[reportArgumentType]


def test_a_run_returns_what_the_platform_saves():
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
                tool("post_message", charge_id="chg-l-1001", text="Matched INV-1001."),
                tool("finish", summary="Matched the invoice."),
            )
        ]
    )
    result = run_agent(
        agent_input(CHARGE, "2025-11-14T00:00:00+00:00", records_until("rec-link-l-1001")), model
    )
    assert [r.kind for r in result.records] == ["link", "budget_assignment", "judgment"]
    assert all(
        r.author == "agent" and r.written_at == datetime.fromisoformat("2025-11-14T00:00:00+00:00")
        for r in result.records
    )
    assert [m.run_id for m in result.messages] == ["run-9"]
    assert result.summary == "Matched the invoice."
    assert result.log is not None and json.loads(result.log)["run_id"] == "run-9"


def test_a_failed_run_raises_and_keeps_its_log():
    model = FakeModel([lambda r: message(text(""), stop="refusal")])
    with pytest.raises(AgentRunFailed) as failed:
        run_agent(
            agent_input(CHARGE, "2025-11-14T00:00:00+00:00", records_until("rec-link-l-1001")),
            model,
        )
    assert not failed.value.retryable and json.loads(failed.value.log)["outcome"] == "failed"


def _charge(n: int, arrived: str) -> Charge:
    base = SAMPLE.charges[0]
    return base.model_copy(
        update={
            "id": f"chg-{n}",
            "ledger_line_id": f"L-{n}",
            "arrived_at": datetime.fromisoformat(arrived),
        }
    )


def test_a_charge_run_covers_the_unhandled_charges_that_arrived_with_it():
    """The ruling: every charge that arrived at the same moment and isn't handled, in batches."""
    same = "2025-11-14T00:00:00+00:00"
    charges = [
        _charge(1, same),
        _charge(2, same),
        _charge(3, same),
        _charge(4, "2025-11-15T00:00:00+00:00"),
    ]
    assert charges_for_run("chg-2", charges, []) == ["chg-2", "chg-1", "chg-3"]
    assert charges_for_run("chg-2", charges, [], size=2) == ["chg-2", "chg-1"]
    handled = SAMPLE.records[12].model_copy(
        update={"data": SAMPLE.records[12].data.model_copy(update={"charge_id": "chg-2"})}
    )
    assert handled.charge_id == "chg-2"
    assert charges_for_run("chg-2", charges, [handled]) == ["chg-1", "chg-3"]


def test_a_charge_run_with_nothing_left_to_handle_calls_no_model():
    db = records_until("rec-allowable-l-1001")
    result = run_agent(agent_input(CHARGE, "2025-11-14T00:00:00+00:00", db), FakeModel([]))
    assert result.records == [] and "already handled" in (result.summary or "")
