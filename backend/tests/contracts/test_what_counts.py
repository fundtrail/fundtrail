"""The rules in docs/contracts.md section 1, "What counts"."""

import pytest

from app.contracts.records import Decision
from app.contracts.rules import RecordState, current_records, current_version, waiting_records
from tests.contracts.factory import (
    FILES,
    agent,
    answer,
    bill,
    budget_line,
    confirm,
    file,
    ids,
    link,
    user,
)


def test_the_agents_terms_count_only_once_confirmed():
    term = agent("t1", budget_line())
    assert waiting_records([term]) == [term]
    assert current_records([term]) == []

    confirmed = [term, user("ok", confirm("t1"), 1)]
    assert ids(current_records(confirmed)) == ["t1", "ok"]
    assert waiting_records(confirmed) == []


def test_a_rejected_record_never_counts():
    term = agent("t1", budget_line())
    rejected = [term, user("no", confirm("t1", decision="rejected"), 1)]
    assert ids(current_records(rejected)) == ["no"]
    assert waiting_records(rejected) == []


def test_the_latest_decision_wins():
    term = agent("t1", budget_line())
    records = [term, user("no", confirm("t1", decision="rejected"), 1), user("ok", confirm("t1"), 2)]
    assert RecordState(records).decision("t1") == Decision.CONFIRMED
    assert "t1" in ids(current_records(records))


def test_only_confirmations_nothing_replaced_count():
    term = agent("t1", budget_line())
    ok = user("ok", confirm("t1"), 1)
    undone = user("undo", {"kind": "retraction"}, 2, replaces_id="ok")
    state = RecordState([term, ok, undone])
    assert state.decision("t1") is None
    assert state.waiting() == [term]


def test_the_agents_first_link_counts_right_away():
    records = [agent("b1", bill()), agent("l1", link())]
    assert waiting_records(records) == []
    assert ids(current_records(records)) == ["b1", "l1"]


def test_a_fix_waits_and_the_old_link_stays_in_force():
    written = [agent("b1", bill()), agent("l1", link()), agent("l2", link(amount=600), 1, replaces_id="l1")]
    assert ids(waiting_records(written)) == ["l2"]
    assert ids(current_records(written)) == ["b1", "l1"]

    approved = [*written, user("ok", confirm("l2"), 2)]
    assert ids(current_records(approved)) == ["b1", "l2", "ok"]

    rejected = [*written, user("no", confirm("l2", decision="rejected"), 2)]
    assert ids(current_records(rejected)) == ["b1", "l1", "no"]


def test_the_agents_retraction_waits():
    written = [agent("b1", bill()), agent("l1", link()), agent("x", {"kind": "retraction"}, 1, replaces_id="l1")]
    assert ids(waiting_records(written)) == ["x"]
    assert ids(current_records([*written, user("ok", confirm("x"), 2)])) == ["b1", "ok"]


def test_the_agents_correction_to_its_own_fact_waits():
    written = [agent("b1", bill()), agent("b2", bill(1300, "$13.00"), 1, replaces_id="b1")]
    assert ids(waiting_records(written)) == ["b2"]


def test_a_second_link_between_a_bill_and_a_charge_waits():
    written = [agent("b1", bill()), agent("l1", link()), agent("l2", link(amount=1200), 1)]
    assert ids(waiting_records(written)) == ["l2"]
    # The same bill linked to another charge is a split, and counts right away.
    split = [agent("b1", bill()), agent("l1", link(amount=600)), agent("l2", link(charge_id="c2", amount=600), 1)]
    assert waiting_records(split) == []


def test_removals_disputes_and_duplicate_marks_wait():
    removal = agent("r", {"kind": "checklist_removal", "charge_id": "c1", "default_item": "bill"})
    dispute = agent(
        "d",
        {
            "kind": "dispute",
            "charge_id": "c1",
            "check": "period_of_performance",
            "reasoning": "The amendment allows it.",
            "quotes": [
                {
                    "file_id": "f1",
                    "passage": "x",
                    "location": {"type": "char_location", "start_char_index": 0, "end_char_index": 1},
                }
            ],
        },
    )
    duplicate = agent("dup", {"kind": "duplicate", "copy_file_id": "f2", "original_file_id": "f1"})
    assert ids(waiting_records([removal, dispute, duplicate])) == ["r", "d", "dup"]


def test_the_accountants_records_never_wait():
    records = [user("t1", budget_line()), user("l1", link(), 1)]
    assert waiting_records(records) == []
    assert ids(current_records(records)) == ["t1", "l1"]


@pytest.mark.parametrize(
    ("before", "after", "waits"),
    [
        ("supports", "supports", False),  # a refreshed answer that says the same thing
        ("unsure", "unsure", False),
        ("supports", "unsure", False),  # toward a concern
        ("supports", "contradicts", False),
        ("unsure", "contradicts", False),
        ("contradicts", "unsure", True),  # contradicts turning into anything milder
        ("contradicts", "supports", True),
        ("unsure", "supports", True),  # waits unless new evidence has arrived
    ],
)
def test_a_new_answer_over_the_agents_own(before: str, after: str, waits: bool):
    records = [agent("j1", answer(before)), agent("j2", answer(after), 5, replaces_id="j1")]
    assert RecordState(records, FILES).waits("j2") is waits


def test_unsure_to_supports_counts_once_a_file_has_arrived():
    records = [agent("j1", answer("unsure")), agent("j2", answer("supports"), 5, replaces_id="j1")]
    arrived = [*FILES, file("f9", arrived_hours=2)]
    assert RecordState(records, arrived).waits("j2") is False
    # A file that was already on file doesn't count, even if the agent links it later.
    assert RecordState(records, FILES).waits("j2") is True


def test_unsure_to_supports_counts_once_a_term_is_confirmed_after_it():
    records = [
        agent("t1", budget_line()),
        agent("j1", answer("unsure"), 1),
        user("ok", confirm("t1"), 2),
        agent("j2", answer("supports"), 3, replaces_id="j1"),
    ]
    assert RecordState(records, FILES).waits("j2") is False


def test_the_agents_new_answer_to_the_accountants_waits():
    records = [user("j1", answer("contradicts")), agent("j2", answer("supports"), 1, replaces_id="j1")]
    assert ids(waiting_records(records)) == ["j2"]
    assert ids(current_records(records)) == ["j1"]


def test_withdrawing_its_own_flag_waits():
    flag = answer("unsure", question="flag", text="Is this a duplicate?")
    records = [agent("f", flag), agent("x", {"kind": "retraction"}, 1, replaces_id="f")]
    assert ids(waiting_records(records)) == ["x"]


def test_a_pointer_follows_a_correction():
    records = [
        agent("b1", bill()),
        agent("l1", link()),
        user("b2", bill(1300, "$13.00"), 1, replaces_id="b1"),
    ]
    follow = current_version("b1", records)
    assert follow is not None and follow.id == "b2"
    assert current_version("b2", records) == follow
    retracted = [*records, user("x", {"kind": "retraction"}, 2, replaces_id="b2")]
    assert current_version("b1", retracted) is None


def test_a_pointer_waits_with_the_correction():
    records = [agent("b1", bill()), agent("b2", bill(1300, "$13.00"), 1, replaces_id="b1")]
    assert current_version("b1", records) == records[0]
    confirmed = [*records, user("ok", confirm("b2"), 2)]
    follow = current_version("b1", confirmed)
    assert follow is not None and follow.id == "b2"


def test_several_records_may_replace_the_same_one():
    written = [
        agent("b1", bill()),
        agent("l1", link()),
        agent("l2", link(amount=600), 1, replaces_id="l1"),
        agent("l3", link(amount=700), 2, replaces_id="l1"),
    ]
    assert ids(waiting_records(written)) == ["l2", "l3"]
    chosen = [*written, user("ok", confirm("l3"), 3)]
    assert ids(current_records(chosen)) == ["b1", "l3", "ok"]
    # The other suggestion replaces a record that's no longer current, so it no longer waits.
    assert waiting_records(chosen) == []


def test_unconfirmed_values():
    lost = agent("b1", bill(match="not_found"))
    state = RecordState([lost])
    assert state.unconfirmed_values(lost) == ["total"]
    confirmed = RecordState([lost, user("ok", confirm("b1"), 1)])
    assert confirmed.unconfirmed_values(lost) == []
    found = agent("b2", bill(match="close"))
    assert RecordState([found]).unconfirmed_values(found) == []


def test_records_are_unique():
    with pytest.raises(ValueError, match="twice"):
        RecordState([agent("b1", bill()), agent("b1", bill())])
