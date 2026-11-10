"""The write check, check_new_record (docs/contracts.md section 1, "Checking a write")."""

from typing import Any

from tests.contracts.factory import (
    FILES,
    agent,
    answer,
    approval,
    bill,
    budget_line,
    citation,
    confirm,
    file,
    link,
    other_term,
    problems,
    user,
)


def has(found: list[str], words: str) -> bool:
    return any(words in p for p in found)


def test_a_good_write_has_no_problems():
    b = agent("b1", bill())
    assert problems(b, []) == []
    assert problems(agent("l1", link(), 1), [b]) == []


def test_every_quoted_value_appears_in_its_passage():
    wrong = bill()
    wrong["total"]["text"] = "$13.00"
    assert has(problems(agent("b1", wrong), []), "doesn't contain '$13.00'")


def test_every_citation_has_been_matched():
    assert has(problems(agent("b1", bill(match=None)), []), "hasn't been matched")


def test_cited_files_exist_and_are_on_the_grant():
    assert has(problems(agent("b1", bill(file_id="nope")), []), "file nope doesn't exist")
    elsewhere = [*FILES, file("f9", grant_id="other")]
    assert has(problems(agent("b1", bill(file_id="f9")), [], elsewhere), "each grant is isolated")


def test_the_id_is_new():
    b = agent("b1", bill())
    assert has(problems(agent("b1", bill(), 1), [b]), "already used")


def test_pointed_records_and_charges_exist_and_are_current():
    b = agent("b1", bill())
    assert has(problems(agent("l1", link(record_id="nope")), [b]), "doesn't exist")
    assert has(problems(agent("l1", link(charge_id="nope")), [b]), "charge nope doesn't exist")
    gone = user("x", {"kind": "retraction"}, 1, replaces_id="b1")
    assert has(problems(agent("l1", link(), 2), [b, gone]), "isn't current")


def test_records_may_point_to_a_waiting_term():
    term = agent("t1", budget_line())
    assignment = {
        "kind": "budget_assignment",
        "charge_id": "c1",
        "record_id": "t1",
        "reason": "Supplies.",
    }
    assert problems(agent("a1", assignment, 1), [term]) == []


def test_the_agent_replaces_only_the_accountants_links_and_answers():
    b = agent("b1", bill())
    their_link = user("l1", link(), 1)
    their_answer = user("j1", answer("contradicts"), 1)
    their_bill = user("b2", bill(1300, "$13.00"), 1, replaces_id="b1")
    written = [b, their_link, their_answer]
    assert problems(agent("l2", link(amount=600), 2, replaces_id="l1"), written) == []
    assert problems(agent("x", {"kind": "retraction"}, 2, replaces_id="l1"), written) == []
    assert problems(agent("j2", answer("supports"), 2, replaces_id="j1"), written) == []
    assert has(
        problems(agent("x", {"kind": "retraction"}, 2, replaces_id="j1"), written),
        "links and answers",
    )
    assert has(
        problems(agent("b3", bill(1400, "$14.00"), 2, replaces_id="b2"), [b, their_bill]),
        "links and answers",
    )


def test_a_replacement_is_the_same_kind_or_a_retraction():
    b = agent("b1", bill())
    assert has(problems(agent("a1", approval(), 1, replaces_id="b1"), [b]), "can't replace a bill")


def test_a_new_answer_is_to_the_same_question():
    first = agent("j1", answer("unsure"))
    other = answer("unsure", question="flag", text="Odd?")
    assert has(problems(agent("j2", other, 1, replaces_id="j1"), [first]), "same question")


def test_a_link_points_to_a_bill_approval_or_note():
    t = user("t1", budget_line())
    assert has(
        problems(agent("l1", link(record_id="t1", part=citation(file_id="f3"))), [t]),
        "not a budget_line",
    )


def test_a_link_carries_an_amount_only_when_its_item_does():
    b, a = agent("b1", bill()), agent("a1", approval())
    approval_link = link(
        record_id="a1", amount=None, default_item=None, part=citation("Approved: travel", "f2")
    )
    assert problems(agent("l1", approval_link, 1), [b, a]) == []
    assert has(
        problems(agent("l1", approval_link | {"amount_cents": 100}, 1), [b, a]),
        "carries an amount only",
    )
    assert has(problems(agent("l1", link(amount=None), 1), [b]), "says how much")


def test_a_link_names_an_item_on_its_charge():
    b = agent("b1", bill())
    assert has(
        problems(agent("l1", link(default_item="nope"), 1), [b]),
        "isn't one of this charge's default",
    )
    item: dict[str, Any] = {
        "kind": "checklist_item",
        "charge_id": "c2",
        "needed": "Receipt",
        "amount_cents": 1200,
    }
    added = agent("i1", item)
    assert has(
        problems(agent("l1", link(default_item=None, item_record_id="i1"), 1), [b, added]),
        "isn't a checklist item",
    )
    mine = agent("i2", item | {"charge_id": "c1"})
    assert problems(agent("l1", link(default_item=None, item_record_id="i2"), 1), [b, mine]) == []


def test_a_links_part_is_in_the_linked_records_own_file():
    b = agent("b1", bill())
    assert has(problems(agent("l1", link(part=citation(file_id="f2")), 1), [b]), "own file")


def test_a_link_doesnt_point_at_a_confirmed_duplicate():
    copy = agent("b1", bill(file_id="f2"))
    mark = agent("d1", {"kind": "duplicate", "copy_file_id": "f2", "original_file_id": "f1"}, 1)
    the_link = agent("l1", link(part=citation(file_id="f2")), 3)
    assert problems(the_link, [copy, mark]) == []  # the mark still waits
    confirmed = user("ok", confirm("d1"), 2)
    assert has(problems(the_link, [copy, mark, confirmed]), "duplicate")


def test_the_agent_doesnt_answer_beside_the_accountant():
    theirs = user("j1", answer("contradicts"))
    assert has(problems(agent("j2", answer("supports"), 1), [theirs]), "suggest a new answer")
    flag = answer("unsure", question="flag", text="Odd?")
    assert problems(agent("j3", flag, 1), [theirs]) == []


def test_a_judgments_question_is_about_the_right_kind_of_record():
    a, t = agent("a1", approval()), user("t1", other_term())
    covers = answer(
        "supports", question="covers", record_id="a1", text="Does this approval cover this charge?"
    )
    assert problems(agent("j1", covers, 1), [a, t]) == []
    assert has(problems(agent("j1", covers | {"record_id": "t1"}, 1), [a, t]), "about an approval")
    unusual = answer(
        "supports", question="unusual_term", record_id="t1", text="Does this term change anything?"
    )
    assert problems(agent("j2", unusual, 1), [a, t]) == []


def test_a_confirmation_lists_only_records_that_wait_or_have_an_unconfirmed_value():
    b, term = agent("b1", bill()), agent("t1", budget_line())
    assert problems(user("ok", confirm("t1"), 1), [b, term]) == []
    assert has(problems(user("ok", confirm("b1"), 1), [b, term]), "doesn't wait")
    lost = agent("b2", bill(match="not_found"))
    assert problems(user("ok", confirm("b2"), 1), [lost]) == []
    assert has(problems(user("ok", confirm("nope"), 1), [b]), "doesn't exist")


def test_the_accountant_confirms_at_most_one_replacement():
    written = [
        agent("b1", bill()),
        agent("l1", link()),
        agent("l2", link(amount=600), 1, replaces_id="l1"),
        agent("l3", link(amount=700), 1, replaces_id="l1"),
        user("ok", confirm("l2"), 2),
    ]
    assert has(problems(user("ok2", confirm("l3"), 3), written), "doesn't wait")


def test_a_budget_assignment_points_to_a_budget_line_and_is_the_only_one():
    line, b = user("t1", budget_line()), agent("b1", bill())
    first = agent(
        "a1",
        {"kind": "budget_assignment", "charge_id": "c1", "record_id": "t1", "reason": "Supplies."},
        1,
    )
    assert problems(first, [line, b]) == []
    second = agent(
        "a2",
        {"kind": "budget_assignment", "charge_id": "c1", "record_id": "t1", "reason": "Supplies."},
        2,
    )
    assert has(problems(second, [line, b, first]), "already has a current budget assignment")
    assert problems(second.model_copy(update={"replaces_id": "a1"}), [line, b, first]) == []
    wrong = agent(
        "a3",
        {"kind": "budget_assignment", "charge_id": "c1", "record_id": "b1", "reason": "Supplies."},
        2,
    )
    assert has(problems(wrong, [line, b]), "points to a budget_line")


def test_a_rejected_suggestion_isnt_repeated_without_new_evidence():
    written = [
        agent("b1", bill()),
        agent("l1", link()),
        agent("l2", link(amount=600), 1, replaces_id="l1"),
        user("no", confirm("l2", decision="rejected"), 2),
    ]
    again = agent("l3", link(amount=600), 3, replaces_id="l1")
    assert has(problems(again, written), "rejected the same suggestion")
    arrived = [*FILES, file("f9", arrived_hours=2.5)]
    assert problems(again, written, arrived) == []


def test_a_rejected_dispute_isnt_repeated_without_new_evidence():
    dispute: dict[str, Any] = {
        "kind": "dispute",
        "charge_id": "c1",
        "check": "period_of_performance",
        "reasoning": "The order was placed before the end date.",
        "quotes": [citation()],
    }
    written = [agent("d1", dispute), user("no", confirm("d1", decision="rejected"), 1)]
    assert has(problems(agent("d2", dispute, 2), written), "rejected the same suggestion")
    other_check = dispute | {"check": "approvals"}
    assert problems(agent("d3", other_check, 2), written) == []


def test_each_grant_is_isolated():
    b = agent("b1", bill())
    elsewhere = b.model_copy(update={"grant_id": "other"})
    assert has(problems(agent("l1", link(), 1), [elsewhere]), "each grant is isolated")
    assert has(
        problems(agent("l1", link(charge_id="c3"), 1), [b]),
        "charge c3 doesn't exist",
    )


def test_accepted_reasons_and_snoozes_point_at_what_exists():
    reason = {"check": "period_of_performance", "problem": "after_end_date"}
    accepted = {
        "kind": "accepted_reason",
        "charge_id": "c1",
        "reason": reason,
        "note": "Ordered before the end date.",
    }
    assert problems(user("a1", accepted), []) == []
    assert has(problems(user("a1", accepted | {"charge_id": "nope"}), []), "doesn't exist")
    on_grant = {
        "kind": "snooze",
        "until": "2026-03-01",
        "note": "Refund coming.",
        "reasons": [reason],
    }
    assert problems(user("s1", on_grant), []) == []
    reuse = accepted | {"reuses_id": "a1"}
    assert has(problems(user("a2", reuse, 1), [user("a1", accepted)]), "isn't a reusable note")
    reusable = user("a1", accepted | {"reusable": True})
    assert problems(user("a2", reuse, 1), [reusable]) == []
