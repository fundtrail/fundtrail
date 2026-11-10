"""Ledger line IDs are unique per grant, not per workspace (issue 165).

Two grants in one workspace, such as two copies of a sample, can hold the same line
ID. Every rule that resolves a charge by its line ID looks only on the charge's grant.
"""

from app.contracts.charges import Charge
from app.contracts.corrections import corrected_line, net_amounts
from app.contracts.rules import RecordState, check_new_record
from app.contracts.runs import Trigger, TriggerKind
from tests.contracts.factory import CHARGE, FILES, RUN_READ_THROUGH, agent, confirm, user


def line(grant: str, line_id: str, cents: int, original: str | None = None) -> Charge:
    return CHARGE.model_copy(
        update={
            "id": f"{grant}-{line_id}",
            "grant_id": grant,
            "ledger_line_id": line_id,
            "amount_cents": cents,
            "original_line_id": original,
        }
    )


# The same ledger on two grants: the other grant's copy is listed first.
OTHER = [line("copy", "L-1", 40000), line("copy", "L-2", -40000, original="L-1")]
OURS = [line("g", "L-1", 40000), line("g", "L-2", -40000, original="L-1")]


def test_a_correcting_line_nets_into_the_line_on_its_own_grant():
    assert corrected_line(OURS[1], OTHER + OURS, RecordState([])) == OURS[0]
    nets = net_amounts(OTHER + OURS, RecordState([]))
    assert nets["g-L-1"].corrections == ("g-L-2",) and nets["g-L-1"].reversed
    assert nets["copy-L-1"].corrections == ("copy-L-2",) and nets["copy-L-1"].reversed


def test_a_correction_record_names_a_line_on_its_own_grant():
    other = [line("copy", "L-1", 40000), line("copy", "L-2", -40000)]
    ours = [line("g", "L-1", 40000), line("g", "L-2", -40000)]
    data = {"kind": "correction", "charge_id": "g-L-2", "corrects_line_id": "L-1", "reason": "r"}
    accepted = RecordState([agent("x1", data), user("ok", confirm("x1"), 1)])
    assert corrected_line(ours[1], other + ours, accepted) == ours[0]
    assert corrected_line(other[1], other + ours, accepted) is None  # not its record


def test_the_ledgers_naming_counts_only_when_the_named_line_is_on_this_grant():
    # Our L-2 names L-1, which is only on the other grant, so a correction record
    # may name another line here.
    charges = [line("copy", "L-1", 40000), line("g", "L-2", -40000, original="L-1")]
    data = {"kind": "correction", "charge_id": "g-L-2", "corrects_line_id": "L-9", "reason": "r"}
    new = agent("x1", data).model_copy(update={"read_through_seq": RUN_READ_THROUGH})
    problems = check_new_record(
        new,
        [],
        charges,
        FILES,
        default_items=lambda c, r: [],
        trigger=Trigger(kind=TriggerKind.CLOCK),
    )
    assert not any("the ledger says" in p for p in problems)
    # With L-1 on this grant too, the ledger's naming wins.
    problems = check_new_record(
        new,
        [],
        [*charges, line("g", "L-1", 40000)],
        FILES,
        default_items=lambda c, r: [],
        trigger=Trigger(kind=TriggerKind.CLOCK),
    )
    assert any("the ledger says" in p for p in problems)
