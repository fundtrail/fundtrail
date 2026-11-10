"""A $0 charge and a rate-math-only charge (issue #87, Alex's decision in call 34).

They stay Evidence complete, as the checks give them, but the agent looks at each when it
arrives and may flag one that looks off. A flag sends the charge to the accountant like any
other. These tests use the real checks (app.checks), not a stand-in.
"""

from datetime import datetime

from app.agent import RunSaved, run_once
from app.agent.inputs import RunInputs
from app.agent.prompts import SYSTEM_PROMPT
from app.checks.checklist import default_items
from app.checks.run import run_checks
from app.contracts.charges import Charge
from app.contracts.checks import Bucket, ChecksInput
from app.contracts.fixtures import DOCUMENTS_DIR, load_sample_grant
from app.contracts.records import Record
from app.contracts.runs import Trigger

from .fakes import FakeModel, calls, tool

SAMPLE = load_sample_grant()
NOW = datetime.fromisoformat("2025-11-14T00:00:00+00:00")
TERMS = [r for r in SAMPLE.records if r.id != "rec-confirm-award-terms"][:10]
CONFIRMED = [*TERMS, next(r for r in SAMPLE.records if r.id == "rec-confirm-award-terms")]


def zero_charge() -> Charge:
    """A $0 supplies line on the sample grant, inside its period."""
    return SAMPLE.charges[0].model_copy(
        update={"id": "chg-zero", "ledger_line_id": "L-0000", "amount_cents": 0, "reference": None}
    )


def bucket(records: list[Record], charge: Charge) -> Bucket:
    out = run_checks(
        ChecksInput(
            now=NOW, charges=(charge,), files=tuple(SAMPLE.files[:1]), records=tuple(records)
        )
    )
    return out.charges[0].bucket


def inputs(charge: Charge) -> RunInputs:
    ids = iter(["rec-zero-budget", "rec-zero-flag"])
    return RunInputs(
        run_id="run-zero",
        grant=SAMPLE.grant,
        now=NOW,
        trigger=Trigger(kind="charge", id=charge.id),  # pyright: ignore[reportArgumentType]
        records=CONFIRMED,
        charges=[charge],
        files=SAMPLE.files[:1],
        read_file=lambda f: (DOCUMENTS_DIR / f.name).read_bytes(),
        default_items=default_items,
        run_checks=run_checks,
        charge_ids=[charge.id],
        new_id=lambda: next(ids),
    )


def assign(charge: Charge):
    return tool(
        "assign_budget_line",
        charge_id=charge.id,
        budget_line_id="rec-budget-materials-and-supplies",
        reason="A supplies line.",
    )


def test_a_zero_dollar_charge_is_evidence_complete_until_the_agent_flags_it():
    charge = zero_charge()

    # The agent looks and finds nothing off: the charge stays Evidence complete.
    looked = run_once(
        inputs(charge),
        FakeModel([lambda r: calls(assign(charge), tool("finish", summary="Fine."))]),
    )
    assert isinstance(looked, RunSaved)
    assert bucket([*CONFIRMED, *looked.records], charge) == Bucket.EVIDENCE_COMPLETE

    # The agent flags it: the charge leaves Evidence complete for the accountant.
    flag = tool(
        "flag",
        charge_id=charge.id,
        question="Should this supplies line be $0?",
        reasoning="A $0 line for lab supplies with no credit or reversal looks off.",
    )
    flagged = run_once(
        inputs(charge),
        FakeModel([lambda r: calls(assign(charge), flag, tool("finish", summary="Flagged."))]),
    )
    assert isinstance(flagged, RunSaved)
    assert bucket([*CONFIRMED, *flagged.records], charge) == Bucket.NEEDS_HUMAN


def test_the_agent_is_told_to_look_at_charges_with_nothing_to_link():
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "Look at every charge that arrives, even one with nothing to link" in flat
    assert "a $0 line that shouldn't be $0" in flat and "per diem whose days or rate" in flat
    model = FakeModel([lambda r: calls(assign(zero_charge()), tool("finish", summary="Fine."))])
    run_once(inputs(zero_charge()), model)
    first = " ".join(model.requests[0].messages[0]["content"][-1]["text"].split())
    assert "look at each one even when there's nothing to link" in first
