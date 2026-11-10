"""One test per defect the independent review of PR 35 found.

Each fails on the code before its fix."""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts.rules import RecordState, current_records, current_version, waiting_records
from tests.contracts.factory import (
    FILES,
    agent,
    answer,
    bill,
    budget_line,
    citation,
    cited,
    confirm,
    file,
    ids,
    link,
    problems,
    user,
)


def test_1_a_second_answer_beside_its_own_is_a_new_answer_over_it():
    first = agent("j1", answer("contradicts"))
    beside = agent("j2", answer("supports"), 1)  # no replaces_id
    state = RecordState([first, beside], FILES)
    assert state.waits("j2") is True
    assert ids(state.current()) == ["j1"]
    toward_a_concern = agent("j3", answer("contradicts"), 1)
    assert (
        RecordState([agent("j1", answer("supports")), toward_a_concern], FILES).waits("j3") is False
    )


def test_2_new_evidence_is_on_the_answers_own_grant():
    records = [agent("j1", answer("unsure")), agent("j2", answer("supports"), 5, replaces_id="j1")]
    elsewhere = [*FILES, file("fx", arrived_hours=2, grant_id="other")]
    assert RecordState(records, elsewhere).waits("j2") is True
    written = [
        agent("b1", bill()),
        agent("l1", link()),
        agent("l2", link(amount=600), 1, replaces_id="l1"),
        user("no", confirm("l2", decision="rejected"), 2),
    ]
    again = agent("l3", link(amount=600), 3, replaces_id="l1")
    elsewhere = [*FILES, file("fx", arrived_hours=2.5, grant_id="other")]
    assert any("rejected the same suggestion" in p for p in problems(again, written, elsewhere))


def test_3_one_confirmation_cant_confirm_two_replacements_of_the_same_record():
    written = [
        agent("b1", bill()),
        agent("l1", link()),
        agent("l2", link(amount=600), 1, replaces_id="l1"),
        agent("l3", link(amount=700), 1, replaces_id="l1"),
    ]
    assert any(
        "replace the same record" in p
        for p in problems(user("ok", confirm("l2", "l3"), 2), written)
    )


def test_4_an_item_may_use_a_rate_term_that_still_waits():
    passage = "Per diem $100"
    rate = agent(
        "r1",
        {
            "kind": "rate",
            "dated": cited("2023-01-10", "January 10, 2023", file_id="f3"),
            "name": cited("Per diem", "Per diem", passage, "f3"),
            "rate": cited(Decimal(10000), "$100", passage, "f3"),
        },
    )
    item = agent(
        "i1",
        {
            "kind": "checklist_item",
            "charge_id": "c1",
            "needed": "Per diem",
            "amount_cents": 50000,
            "rate": {"quantity": cited(Decimal(5), "5 days", "5 days", "f1"), "rate_id": "r1"},
        },
        1,
    )
    assert problems(item, [rate]) == []


def test_5_the_accountant_can_replace_a_waiting_or_rejected_record_of_the_agents():
    term = agent("t1", budget_line())
    typed_data: dict[str, Any] = budget_line() | {"amount": {"value": 4100000}}
    typed = user("t2", typed_data, 1, replaces_id="t1")
    assert problems(typed, [term]) == []
    assert waiting_records([term, typed]) == []
    follow = current_version("t1", [term, typed])
    assert follow is not None and follow.id == "t2"

    rejected = user("no", confirm("t1", decision="rejected"), 1)
    later = typed.model_copy(update={"written_at": typed.written_at.replace(hour=20)})
    assert problems(later, [term, rejected]) == []
    follow = current_version("t1", [term, rejected, later])
    assert follow is not None and follow.id == "t2"
    # Confirming a record the accountant already replaced is refused.
    assert problems(user("ok", confirm("t1"), 21), [term, typed])
    # The agent still can't replace a record of its own that waits.
    assert problems(agent("t3", budget_line(), 2, replaces_id="t1"), [term])


def test_7_a_budget_assignment_has_a_reason():
    with pytest.raises(ValidationError):
        agent("a1", {"kind": "budget_assignment", "charge_id": "c1", "record_id": "t1"})


def test_8_a_fact_with_only_an_unconfirmed_value_can_be_confirmed_but_not_rejected():
    lost = agent("b1", bill(match="not_found"))
    assert problems(user("ok", confirm("b1"), 1), [lost]) == []
    rejecting = problems(user("no", confirm("b1", decision="rejected"), 1), [lost])
    assert any("not rejected" in p for p in rejecting)


def test_9_a_confirmed_term_isnt_confirmed_again_and_that_isnt_new_evidence():
    written = [
        agent("t1", budget_line()),
        user("ok", confirm("t1"), 0.5),
        agent("j1", answer("unsure"), 1),
    ]
    again = user("ok2", confirm("t1"), 2)
    assert any("already confirmed" in p for p in problems(again, written))
    records = [*written, again, agent("j2", answer("supports"), 3, replaces_id="j1")]
    assert RecordState(records, FILES).waits("j2") is True


def test_10_no_repeats_catches_only_a_repeated_waiting_suggestion():
    written = [
        agent("b1", bill()),
        agent("l1", link()),
        agent("l2", link(), 1),  # a second link, which waits
        user("no", confirm("l2", decision="rejected"), 2),
        user("x", {"kind": "retraction"}, 3, replaces_id="l1"),
    ]
    assert problems(agent("l3", link(), 4), written) == []  # a first link again: it doesn't wait
    before_the_retraction = written[:4]
    repeated = problems(agent("l3", link(), 4), before_the_retraction)
    assert any("rejected the same suggestion" in p for p in repeated)


def test_a_duplicate_mark_is_the_same_suggestion_either_way_round():
    mark = {"kind": "duplicate", "copy_file_id": "f2", "original_file_id": "f1"}
    written = [agent("d1", mark), user("no", confirm("d1", decision="rejected"), 1)]
    reversed_mark = {"kind": "duplicate", "copy_file_id": "f1", "original_file_id": "f2"}
    assert any(
        "rejected the same suggestion" in p
        for p in problems(agent("d2", reversed_mark, 2), written)
    )


def test_list_fields_are_tuples_so_frozen_means_frozen():
    r = user("ok", confirm("a", "b"))
    assert r.data.record_ids == ("a", "b")  # type: ignore[union-attr]


# The agreed contract change: a value may lack its citation only when it's marked uncited.


def uncited_bill() -> dict[str, Any]:
    return bill() | {"vendor": {"value": "Example Co.", "text": "Example Co.", "uncited": True}}


def test_the_agent_marks_a_value_uncited_or_cites_it():
    agent("b1", uncited_bill())
    with pytest.raises(ValidationError):
        agent("b1", bill() | {"vendor": {"value": "Example Co.", "text": "Example Co."}})
    with pytest.raises(ValidationError):  # the mark is valid only with no citation
        agent("b1", bill() | {"vendor": cited("Example Co.", "Example Co.") | {"uncited": True}})


def test_an_uncited_value_is_unconfirmed_until_the_accountant_confirms_the_record():
    b = agent("b1", uncited_bill())
    assert problems(b, []) == []
    assert RecordState([b]).unconfirmed_values(b) == ["vendor"]
    ok = user("ok", confirm("b1"), 1)
    assert problems(ok, [b]) == []
    assert RecordState([b, ok]).unconfirmed_values(b) == []


def test_a_flag_about_a_file_that_doesnt_exist_is_refused():
    flag = answer("unsure", question="flag", charge_id=None, file_id="nope", text="Can't read it?")
    assert any("file nope doesn't exist" in p for p in problems(agent("f", flag), []))


# The re-review of 6ca0fc2.


def test_r1_to_fix_a_suggested_replacement_the_accountant_replaces_its_target():
    written = [
        agent("b1", bill()),
        agent("l1", link()),
        agent("l2", link(amount=600), 1, replaces_id="l1"),
    ]
    over_the_fix = user("l3", link(amount=700), 2, replaces_id="l2")
    assert any("isn't current" in p for p in problems(over_the_fix, written))
    over_the_target = user("l3", link(amount=700), 2, replaces_id="l1")
    assert problems(over_the_target, written) == []
    assert ids(current_records([*written, over_the_target])) == ["b1", "l3"]

    answers = [
        user("j1", answer("contradicts")),
        agent("j2", answer("supports"), 1, replaces_id="j1"),
    ]
    over_the_answer = user("j3", answer("unsure"), 2, replaces_id="j2")
    assert any("isn't current" in p for p in problems(over_the_answer, answers))


def test_r2_the_accountant_rejects_a_waiting_suggestion_rather_than_retracting_it():
    dispute: dict[str, Any] = {
        "kind": "dispute",
        "charge_id": "c1",
        "check": "period_of_performance",
        "reasoning": "The order was placed before the end date.",
        "quotes": [citation()],
    }
    written = [agent("d1", dispute)]
    retracting = problems(user("x", {"kind": "retraction"}, 1, replaces_id="d1"), written)
    assert any("reject it instead" in p for p in retracting)


def test_r3_a_rejected_answer_doesnt_come_back_beside_the_agents_own():
    written = [
        agent("j1", answer("contradicts")),
        agent("j2", answer("supports"), 1, replaces_id="j1"),
        user("no", confirm("j2", decision="rejected"), 2),
    ]
    beside = agent("j3", answer("supports"), 3)
    assert any("rejected the same suggestion" in p for p in problems(beside, written))
