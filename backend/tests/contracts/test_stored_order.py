"""Issue 70: an answer's new evidence is ordered by stored order, not clock dates."""

import pytest

from app.contracts.evidence import EvidenceFile
from app.contracts.records import Record
from app.contracts.rules import RecordState, check_new_record, read_by_run, run_read_point
from app.contracts.runs import Trigger, TriggerKind
from tests.contracts.factory import (
    CHARGE,
    CHARGES,
    FILES,
    agent,
    answer,
    at,
    bill,
    budget_line,
    confirm,
    defaults,
    file,
    ids,
    link,
    problems,
    user,
)


def stored(record: Record, seq: int) -> Record:
    return record.model_copy(update={"stored_seq": seq})


def receipt(seq: int | None, hours: float = 0) -> EvidenceFile:
    return file("f9", arrived_hours=hours).model_copy(update={"stored_seq": seq})


def test_the_demos_main_move_counts_as_new_evidence():
    """Unsure, a receipt uploaded at the same frozen now, then supports."""
    unsure = stored(agent("j1", answer("unsure")), 1)
    supports = stored(agent("j2", answer("supports"), replaces_id="j1"), 3)
    assert RecordState([unsure, supports], [*FILES, receipt(2)]).waits("j2") is False
    beside = stored(agent("j3", answer("supports")), 3)
    assert RecordState([unsure, beside], [*FILES, receipt(2)]).waits("j3") is False
    # The answer being checked isn't stored yet: it comes after everything stored.
    checking = agent("j4", answer("supports"), replaces_id="j1")
    assert RecordState([unsure, checking], [*FILES, receipt(2)]).waits("j4") is False


def test_a_file_stored_before_the_answer_at_the_same_time_isnt_new():
    unsure = stored(agent("j1", answer("unsure")), 2)
    supports = stored(agent("j2", answer("supports"), replaces_id="j1"), 3)
    assert RecordState([unsure, supports], [*FILES, receipt(1)]).waits("j2") is True


def test_a_file_stored_after_the_new_answer_isnt_what_it_rests_on():
    unsure = stored(agent("j1", answer("unsure")), 1)
    supports = stored(agent("j2", answer("supports"), replaces_id="j1"), 2)
    assert RecordState([unsure, supports], [*FILES, receipt(3)]).waits("j2") is True
    later = stored(agent("j2", answer("supports"), -1, replaces_id="j1"), 2)
    assert RecordState([unsure, later], [*FILES, receipt(1, hours=0)]).waits("j2") is True


def test_a_file_that_arrived_later_than_the_answer_still_counts():
    unsure = stored(agent("j1", answer("unsure")), 5)
    supports = stored(agent("j2", answer("supports"), 2, replaces_id="j1"), 7)
    assert RecordState([unsure, supports], [*FILES, receipt(None, hours=1)]).waits("j2") is False


def test_a_term_confirmation_counts_by_stored_order_only():
    term = stored(agent("t1", budget_line()), 1)
    unsure = stored(agent("j1", answer("unsure"), 5), 2)
    # Stamped with an earlier clock time (catch-up) but stored after the answer: counts.
    late = stored(user("ok", confirm("t1"), 1), 3)
    supports = stored(agent("j2", answer("supports"), 5, replaces_id="j1"), 4)
    assert RecordState([term, unsure, late, supports], FILES).waits("j2") is False
    # Stamped later but stored before the answer: doesn't count.
    early = stored(user("ok", confirm("t1"), 9), 2)
    unsure_after = stored(agent("j1", answer("unsure"), 5), 3)
    assert RecordState([term, early, unsure_after, supports], FILES).waits("j2") is True


def test_records_are_put_in_stored_order():
    b = stored(agent("b1", bill()), 2)
    first = stored(agent("l1", link(), 5), 3)
    second = stored(agent("l2", link(), 0), 4)  # an earlier clock, stored later: it's the second
    assert ids(RecordState([second, b, first]).records) == ["b1", "l1", "l2"]
    assert RecordState([second, b, first]).waits("l2") is True


def test_a_rejected_suggestion_comes_back_after_a_file_stored_since_the_rejection():
    b = stored(agent("b1", bill()), 1)
    original = stored(agent("l1", link()), 2)
    fix = stored(agent("l2", link(amount=600), replaces_id="l1"), 3)
    rejected = stored(user("no", confirm("l2", decision="rejected")), 4)
    again = agent("l3", link(amount=600), replaces_id="l1")
    written = [b, original, fix, rejected]
    assert any("rejected the same suggestion" in p for p in problems(again, written))
    assert problems(again, written, [*FILES, receipt(5)]) == []
    assert any(
        "rejected the same suggestion" in p for p in problems(again, written, [*FILES, receipt(3)])
    )


# The review of PR 77.


def test_d1_a_new_record_cant_claim_a_stored_order():
    written = [stored(agent("b1", bill()), 1)]
    claiming = stored(agent("l1", link()), 0)
    assert any("stored order when it's saved" in p for p in problems(claiming, written))
    assert problems(agent("l1", link()), written) == []


def test_d2_a_stored_record_missing_its_order_is_refused():
    """The reviewer's mixed case: a stored record read without its stored_seq, before
    other stored records, would read as "after everything" and clear a problem."""
    unsure = stored(agent("j1", answer("unsure")), 1)
    unread = agent("j2", answer("supports"), replaces_id="j1")  # stored, seq not read
    after = stored(agent("b1", bill()), 100)
    with pytest.raises(ValueError, match="stored_seq"):
        RecordState([unsure, unread, after], [*FILES, receipt(99)])


def test_d2_only_the_record_being_checked_comes_after_everything():
    # In data with no stored order at all, a record that isn't last is never treated
    # as being checked, so a file at the same time isn't counted for it.
    unsure = agent("j1", answer("unsure"))
    supports = agent("j2", answer("supports"), replaces_id="j1")
    tail = agent("b1", bill(), 1)
    state = RecordState([unsure, supports, tail], [*FILES, receipt(None)])
    assert state.waits("j2") is True
    # The last record, not stored yet, is the one being checked.
    assert RecordState([stored(unsure, 1), supports], [*FILES, receipt(2)]).waits("j2") is False


# Call 40: each run's read point.


def read(record: Record, seq: int, read_point: int) -> Record:
    return record.model_copy(update={"stored_seq": seq, "read_through_seq": read_point})


def test_a_receipt_stored_before_the_run_read_counts_at_once():
    """The demo move: the receipt is stored, then the run reads, then answers supports."""
    unsure = read(agent("j1", answer("unsure")), 1, 0)
    supports = read(agent("j2", answer("supports"), replaces_id="j1"), 3, 2)
    assert RecordState([unsure, supports], [*FILES, receipt(2)]).waits("j2") is False


def test_a_receipt_stored_mid_run_makes_the_supports_wait_until_the_next_run():
    unsure = read(agent("j1", answer("unsure")), 1, 0)
    # The run read up to 2; the receipt was stored at 3, while it ran.
    supports = read(agent("j2", answer("supports"), replaces_id="j1"), 4, 2)
    files = [*FILES, receipt(3)]
    assert RecordState([unsure, supports], files).waits("j2") is True
    # The follow-up run reads up to 4 and answers again: the receipt is new for it.
    again = read(agent("j3", answer("supports"), replaces_id="j1"), 5, 4)
    assert RecordState([unsure, supports, again], files).waits("j3") is False


def test_a_term_confirmed_mid_run_isnt_new_for_that_run():
    term = stored(agent("t1", budget_line()), 1)
    unsure = read(agent("j1", answer("unsure")), 2, 1)
    confirmed = stored(user("ok", confirm("t1")), 3)
    mid_run = read(agent("j2", answer("supports"), replaces_id="j1"), 4, 2)
    assert RecordState([term, unsure, confirmed, mid_run], FILES).waits("j2") is True
    after = read(agent("j2", answer("supports"), replaces_id="j1"), 4, 3)
    assert RecordState([term, unsure, confirmed, after], FILES).waits("j2") is False


def test_only_the_agents_records_carry_a_read_point():
    with pytest.raises(ValueError):
        Record.model_validate(user("b1", bill()).model_dump() | {"read_through_seq": 3})


# The ruling on N3: the window runs from the earlier answer's read point to this run's.


def test_a_receipt_uploaded_during_the_first_run_counts_for_the_follow_up_run():
    """The reviewer's case: the first run read up to 1; the receipt was stored at 2,
    while it ran, and its unsure answer at 3. The follow-up run read up to 4."""
    unsure = read(agent("j1", answer("unsure")), 3, 1)
    supports = read(agent("j2", answer("supports"), replaces_id="j1"), 5, 4)
    assert RecordState([unsure, supports], [*FILES, receipt(2)]).waits("j2") is False


def test_what_the_earlier_run_had_read_isnt_new():
    unsure = read(agent("j1", answer("unsure")), 3, 2)
    supports = read(agent("j2", answer("supports"), replaces_id="j1"), 5, 4)
    assert RecordState([unsure, supports], [*FILES, receipt(2)]).waits("j2") is True


def test_a_term_confirmed_during_the_first_run_counts_for_the_follow_up_run():
    term = stored(agent("t1", budget_line()), 1)
    confirmed = stored(user("ok", confirm("t1")), 2)  # while the first run worked
    unsure = read(agent("j1", answer("unsure")), 3, 1)
    supports = read(agent("j2", answer("supports"), replaces_id="j1"), 4, 3)
    assert RecordState([term, confirmed, unsure, supports], FILES).waits("j2") is False


# N1: a run's staged records come after the stored ones, each not stored yet.


def test_a_runs_second_and_third_staged_records_are_checked():
    b = stored(agent("b1", bill()), 1)
    first = agent("l1", link(), 1).model_copy(update={"read_through_seq": 1})
    second = agent(
        "a1",
        {"kind": "budget_assignment", "charge_id": "c1", "record_id": "t1", "reason": "Supplies."},
        1,
    ).model_copy(update={"read_through_seq": 1})
    third = agent("j1", answer("supports"), 1).model_copy(update={"read_through_seq": 1})
    line = stored(user("t1", budget_line()), 0)
    state = RecordState([line, b, first, second])
    assert ids(state.records) == ["t1", "b1", "l1", "a1"]
    assert problems(third, [line, b, first, second]) == []
    with pytest.raises(ValueError):  # a stored record after the staged ones
        RecordState([line, first, b])


# N2: the agent's record carries its run's read point.


def test_the_agents_record_without_a_read_point_is_refused():
    found = check_new_record(
        agent("b1", bill()),
        [],
        CHARGES,
        FILES,
        default_items=defaults,
        trigger=Trigger(kind=TriggerKind.CLOCK),
    )
    assert any("read point" in p for p in found)


# What a run read (the third review and the main coordinator): stored by its read point
# AND arrived or written by its clock. Seeded-style numbering: the seed's files are
# stored at reset, first, with arrival dates in the future; records come later.


def seeded_receipt(arrives: float) -> EvidenceFile:
    return file("f9", arrived_hours=arrives).model_copy(update={"stored_seq": 3})


def run_answer(
    id: str, data: dict[str, object], clock: float, seq: int, read_point: int, **kw: str
) -> Record:
    return agent(id, data, clock, **kw).model_copy(
        update={"stored_seq": seq, "read_through_seq": read_point}
    )


def test_the_clock_releases_a_seeded_receipt_and_the_next_runs_supports_counts():
    unsure = run_answer("j1", answer("unsure"), 0, 51, 50)
    supports = run_answer("j2", answer("supports"), 5, 61, 60, replaces_id="j1")
    files = [*FILES, seeded_receipt(arrives=5)]
    assert RecordState([unsure, supports], files).waits("j2") is False


def test_a_supports_from_a_run_before_the_receipt_arrives_doesnt_count_on_it():
    unsure = run_answer("j1", answer("unsure"), 0, 51, 50)
    early = run_answer("j2", answer("supports"), 4, 61, 60, replaces_id="j1")
    files = [*FILES, seeded_receipt(arrives=5)]
    assert RecordState([unsure, early], files).waits("j2") is True


def test_a_replay_run_at_an_earlier_clock_doesnt_read_a_later_confirmation():
    """Case A: a high read point alone doesn't make a later confirmation read."""
    term = stored(agent("t1", budget_line(), -1), 5)
    unsure = run_answer("j1", answer("unsure"), 0, 11, 10)
    confirmed = stored(user("ok", confirm("t1"), 3), 20)
    replay = run_answer("j2", answer("supports"), 2, 31, 30, replaces_id="j1")
    assert RecordState([term, unsure, confirmed, replay], FILES).waits("j2") is True
    caught_up = run_answer("j2", answer("supports"), 3, 31, 30, replaces_id="j1")
    assert RecordState([term, unsure, confirmed, caught_up], FILES).waits("j2") is False


def test_a_seeded_file_arriving_after_the_new_record_doesnt_reopen_a_rejection():
    """The fallback's unsafe case: the window starts at the accountant's rejection, and a
    seeded file stored early but arriving later isn't read by the new run."""
    b = stored(agent("b1", bill()), 10)
    original = stored(agent("l1", link()), 11)
    fix = stored(agent("l2", link(amount=600), replaces_id="l1"), 12)
    rejected = stored(user("no", confirm("l2", decision="rejected"), 1), 13)
    again = agent("l3", link(amount=600), 2, replaces_id="l1").model_copy(
        update={"read_through_seq": 100}
    )
    written = [b, original, fix, rejected]
    later = [*FILES, seeded_receipt(arrives=5)]
    assert any("rejected the same suggestion" in p for p in problems(again, written, later))
    arrived = [*FILES, seeded_receipt(arrives=1.5)]
    assert problems(again, written, arrived) == []


def test_the_read_point_and_read_by_run_helpers():
    b = stored(agent("b1", bill()), 7)
    seeded = seeded_receipt(arrives=5)
    charge = CHARGE.model_copy(update={"stored_seq": 9})
    assert run_read_point([b], [charge], [seeded]) == 9
    assert run_read_point() == 0
    assert read_by_run(b, read_through_seq=9, clock_now=at(0))
    assert not read_by_run(b, read_through_seq=6, clock_now=at(0))
    assert not read_by_run(seeded, read_through_seq=9, clock_now=at(4))  # not arrived yet
    assert read_by_run(seeded, read_through_seq=9, clock_now=at(5))
    assert read_by_run(charge, read_through_seq=9, clock_now=at(0))
    unstored = agent("b2", bill())
    assert not read_by_run(unstored, read_through_seq=9, clock_now=at(0))
