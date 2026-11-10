"""Issue 118: the grant's award number and title come from the notices that count."""

from typing import Any

from app.contracts.fixtures import load_sample_grant
from app.contracts.records import Notice, Record
from app.contracts.rules import RecordState, award_number_and_title
from tests.contracts.factory import agent, cited, confirm, problems, user

SAMPLE = load_sample_grant()
TITLE = "Sediment Microbiome Survey of Example Bay"


def test_the_sample_award_letters_notice_carries_the_award_number_and_title():
    notice = next(r.data for r in SAMPLE.records if isinstance(r.data, Notice))
    assert notice.award_number is not None and notice.award_number.value == "SYN-2300117"
    assert notice.title is not None and notice.title.value == TITLE


def test_they_fill_in_once_the_notice_is_confirmed():
    confirmation = next(r for r in SAMPLE.records if r.id == "rec-confirm-award-terms")
    waiting = [r for r in SAMPLE.records if r.written_at < confirmation.written_at]
    assert award_number_and_title(RecordState(waiting)) == (None, None)
    assert award_number_and_title(RecordState(SAMPLE.records)) == ("SYN-2300117", TITLE)


def notice(dated: str, number: str, title: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "kind": "notice",
        "dated": cited(dated, dated, file_id="f3"),
        "amendment_number": cited(number, number, f"Amendment Number: {number}", "f3"),
        "amendment_type": cited("Increment", "Increment", file_id="f3"),
        "award_number": cited("SYN-2300999", "SYN-2300999", file_id="f3"),
    }
    if title is not None:
        data["title"] = cited(title, title, file_id="f3")
    return data


def test_the_latest_confirmed_notice_that_prints_a_value_wins():
    first = agent("n0", notice("2023-01-10", "000", "First title"))
    later = agent("n1", notice("2024-06-01", "001", "Renamed title"), 1)
    no_title = agent("n2", notice("2025-01-01", "002"), 2)
    written: list[Record] = [first, later, no_title]
    assert problems(no_title, [first, later]) == []
    assert award_number_and_title(RecordState(written)) == (None, None)  # all still wait
    confirmed = [*written, user("ok", confirm("n0", "n1", "n2"), 3)]
    assert award_number_and_title(RecordState(confirmed)) == ("SYN-2300999", "Renamed title")
