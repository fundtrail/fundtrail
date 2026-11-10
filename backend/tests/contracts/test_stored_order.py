"""Issue 70: an answer's new evidence is ordered by stored order, not clock dates."""

from app.contracts.evidence import EvidenceFile
from app.contracts.records import Record
from app.contracts.rules import RecordState
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
