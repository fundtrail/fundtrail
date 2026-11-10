"""Issue 114: what accepting each kind of the agent's suggestion changes, worded by code."""

from typing import Any

from app.checks.suggestions import suggestion_change
from app.contracts.checks import ChecklistEntry, ItemSource
from app.contracts.records import Record
from tests.contracts.factory import (
    CHARGES,
    FILES,
    agent,
    answer,
    bill,
    budget_line,
    citation,
    cited,
    link,
    user,
)

BILL = agent("b1", bill())
LINE = user("t1", budget_line())
OTHER_LINE = user("t2", budget_line("Other"))
RECORDS = [BILL, LINE, OTHER_LINE]


def words(record: Record, replaces: Record | None = None, **kw: Any):
    return suggestion_change(record, replaces, records=RECORDS, files=FILES, charges=CHARGES, **kw)


def test_a_link_fix_says_what_is_in_force_and_what_is_suggested():
    old = agent("l1", link())
    fix = agent("l2", link(amount=600), replaces_id="l1")
    change = words(fix, old)
    assert change.title == "Change the link"
    assert change.now == "bill, f1.txt for ledger line L-1, $12.00"
    assert change.suggested == "bill, f1.txt for ledger line L-1, $6.00"


def test_a_second_link_says_it_adds_one():
    change = words(agent("l2", link()))
    assert change.title == "Add a link for ledger line L-1"
    assert change.suggested == "bill, f1.txt for ledger line L-1, $12.00"


def test_a_new_answer_names_the_question_and_both_answers():
    old = user("j1", answer("contradicts"))
    new = agent("j2", answer("supports"), replaces_id="j1")
    change = words(new, old)
    assert change.title == "Change the Allowable answer on ledger line L-1"
    assert (change.now, change.suggested) == ("Contradicts", "Supports")


def test_withdrawing_a_flag_and_withdrawing_a_link():
    flag = agent("f1", answer("unsure", question="flag", text="Is this a duplicate?"))
    change = words(agent("x1", {"kind": "retraction"}, replaces_id="f1"), flag)
    assert (change.title, change.now) == ("Withdraw the agent's flag", "Is this a duplicate?")
    old = agent("l1", link())
    change = words(agent("x2", {"kind": "retraction"}, replaces_id="l1"), old)
    assert change.title == "Withdraw the link"
    assert change.now == "bill, f1.txt for ledger line L-1, $12.00"


def test_a_checklist_removal_names_the_item():
    removal = agent("r1", {"kind": "checklist_removal", "charge_id": "c1", "default_item": "bill"})
    entry = ChecklistEntry(
        default_item="bill",
        added_by=ItemSource.DEFAULT,
        needed="A bill that adds up to the charge",
        filled=False,
        removal_waiting_id="r1",
    )
    change = words(removal, checklist=[entry])
    assert (
        change.title
        == "Remove “A bill that adds up to the charge” from the checklist of ledger line L-1"
    )
    assert words(removal).title.startswith("Remove “bill”")  # the key when no checklist is given


def test_a_dispute_a_duplicate_a_correction_and_a_remainder():
    dispute = agent(
        "d1",
        {
            "kind": "dispute",
            "charge_id": "c1",
            "check": "period_of_performance",
            "reasoning": "Ordered before the end date.",
            "quotes": [citation()],
        },
    )
    assert words(dispute).title == (
        "Accept the agent's dispute of the period of performance check on ledger line L-1, "
        "with its reasoning as the note"
    )
    copy = agent("m1", {"kind": "duplicate", "copy_file_id": "f2", "original_file_id": "f1"})
    assert words(copy).title == "Mark f2.txt as a copy of f1.txt"
    correction = agent(
        "x1", {"kind": "correction", "charge_id": "c2", "corrects_line_id": "L-1", "reason": "r"}
    )
    assert words(correction).title == "Count ledger line L-2 as correcting ledger line L-1"
    remainder = agent(
        "x2",
        {
            "kind": "remainder",
            "record_id": "b1",
            "other_award": cited("SYN-2300999", "SYN-2300999", file_id="f2"),
            "reason": "r",
        },
    )
    assert words(remainder).title == (
        "Record that the rest of the bill in f1.txt belongs to award SYN-2300999"
    )


def test_a_budget_line_change_and_records_a_thread_run_added():
    old = agent(
        "a1", {"kind": "budget_assignment", "charge_id": "c1", "record_id": "t1", "reason": "r"}
    )
    new = agent(
        "a2",
        {"kind": "budget_assignment", "charge_id": "c1", "record_id": "t2", "reason": "r"},
        replaces_id="a1",
    )
    change = words(new, old)
    assert (change.title, change.now, change.suggested) == (
        "Change the budget line assignment",
        "Materials and Supplies",
        "Other",
    )
    item = agent("i1", {"kind": "checklist_item", "charge_id": "c1", "needed": "Packing slip"})
    assert (words(item).title, words(item).suggested) == ("Add the checklist item", "Packing slip")
    first = agent("j1", answer("supports"))
    assert (words(first).title, words(first).suggested) == (
        "Answer Allowable on ledger line L-1",
        "Supports",
    )
    flag = agent("f1", answer("unsure", question="flag", text="Odd vendor?"))
    assert (words(flag).title, words(flag).suggested) == ("Raise the agent's flag", "Odd vendor?")
    assert words(BILL).title == "Add the bill"


# PR 132's review.


def test_a_correction_nets_only_when_the_signs_are_opposite():
    credit = CHARGES[1].model_copy(update={"amount_cents": -1200})
    correction = agent(
        "x1", {"kind": "correction", "charge_id": "c2", "corrects_line_id": "L-1", "reason": "r"}
    )
    change = suggestion_change(correction, charges=[CHARGES[0], credit])
    assert change.title == "Count ledger line L-2 as correcting ledger line L-1, and net the two"
    same_sign = suggestion_change(correction, charges=CHARGES)  # both add money
    assert same_sign.title == "Count ledger line L-2 as correcting ledger line L-1"


def test_a_term_correction_reads_differently_on_each_side():
    old = agent("t1", budget_line())
    fixed_data = budget_line() | {
        "amount": cited(4100000, "$41,000", "Materials and Supplies $41,000", "f3")
    }
    fixed = agent("t2", fixed_data, replaces_id="t1")
    change = words(fixed, old)
    assert (change.now, change.suggested) == (
        "Materials and Supplies: $40,000.00",
        "Materials and Supplies: $41,000.00",
    )


# Ruling 56: ledger line IDs are unique per grant.


def test_a_correction_looks_for_the_line_it_corrects_on_its_own_grant_only():
    """Another grant holds a line with the same ID. It isn't the line the correction
    names, so only this grant's line decides whether the two net."""
    correction = agent(
        "x1", {"kind": "correction", "charge_id": "c2", "corrects_line_id": "L-1", "reason": "r"}
    )
    elsewhere = CHARGES[0].model_copy(update={"id": "o1", "grant_id": "g2"})
    credit = CHARGES[1].model_copy(update={"amount_cents": -1200})
    # Only the other grant's L-1 has the opposite sign, and it's listed first: no netting.
    other_credit = elsewhere.model_copy(update={"amount_cents": -1200})
    change = suggestion_change(correction, charges=[other_credit, CHARGES[0], CHARGES[1]])
    assert change.title == "Count ledger line L-2 as correcting ledger line L-1"
    # Only this grant's L-1 has the opposite sign, listed after the other grant's: they net.
    change = suggestion_change(correction, charges=[elsewhere, CHARGES[0], credit])
    assert change.title == "Count ledger line L-2 as correcting ledger line L-1, and net the two"
