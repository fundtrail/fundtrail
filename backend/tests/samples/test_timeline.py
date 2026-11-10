"""The timeline player's pure logic (issue 165)."""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contracts.api import ArrivalSource
from app.samples.pack import LARGER_SAMPLE, SMALL_SAMPLE, SamplePack, load_folder, load_pack
from app.samples.timeline import (
    ChecksDate,
    ItemKind,
    MoveRefused,
    OnGrant,
    TimelineItem,
    checks_items,
    coming_up,
    delivered_at,
    deliveries,
    finished,
    merge,
    pack_items,
    plan_move,
    plan_start,
    still_reading,
)

from .packs import write_pack


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


@pytest.fixture
def pack(tmp_path: Path) -> SamplePack:
    return load_folder(write_pack(tmp_path / "test-sample"))


@pytest.fixture
def items(pack: SamplePack) -> tuple[TimelineItem, ...]:
    return pack_items(pack)


def names(items: Sequence[TimelineItem]) -> list[str]:
    return [i.name for i in items]


def test_a_ledger_files_later_lines_are_on_the_timeline(items: tuple[TimelineItem, ...]) -> None:
    # L-9001-0001 posted before the ledger arrived, so it arrives with the file; the other
    # two arrive at 00:00 UTC on their posting dates (decision 0023).
    assert names(items) == [
        "award_letter.txt",
        "ledger.csv",
        "invoice_INV-1.txt",
        "invoice_INV-2.txt",
        "receipt_R-3.txt",
        "email_INV-4.eml",
        "L-9001-0002",
        "L-9001-0003",
    ]
    later = items[6:]
    assert [i.at for i in later] == [at("2026-11-24T00:00:00Z"), at("2026-12-07T00:00:00Z")]
    assert all(i.event is None and i.source is ArrivalSource.LEDGER for i in later)
    assert [i.id for i in later] == ["e002-L-9001-0002", "e002-L-9001-0003"]
    assert [i.kind for i in items[4:6]] == [ItemKind.USER_DELIVERY] * 2


def test_a_sample_starts_at_its_first_event(
    pack: SamplePack, items: tuple[TimelineItem, ...]
) -> None:
    move = plan_start(items, pack.starts_at)
    assert [e.name for e in move.play] == ["award_letter.txt"]
    assert move.stopped_on is not None and move.stopped_on.name == "award_letter.txt"


def test_next_moves_to_the_next_item_and_plays_everything_at_that_time(
    items: tuple[TimelineItem, ...],
) -> None:
    move = plan_move(items, at("2026-11-16T17:45:00Z"), None)
    assert move.until == at("2026-11-16T17:50:00Z")
    assert [e.name for e in move.play] == ["invoice_INV-1.txt", "invoice_INV-2.txt"]
    assert move.stopped_on is not None and move.stopped_on.name == "invoice_INV-1.txt"


def test_go_to_a_date_plays_everything_between_in_order(items: tuple[TimelineItem, ...]) -> None:
    move = plan_move(items, at("2026-11-16T17:30:00Z"), at("2026-11-30T00:00:00Z"))
    assert names(move.passed) == [
        "ledger.csv",
        "invoice_INV-1.txt",
        "invoice_INV-2.txt",
        "receipt_R-3.txt",
        "email_INV-4.eml",
        "L-9001-0002",
    ]
    # The user's items are passed but never delivered by the clock, and the ledger's later
    # line is passed but not played: the clock releases it.
    assert [e.name for e in move.play] == ["ledger.csv", "invoice_INV-1.txt", "invoice_INV-2.txt"]
    assert move.stopped_on is None


def test_the_clock_stops_once_on_a_users_item_and_delivers_nothing(
    items: tuple[TimelineItem, ...],
) -> None:
    move = plan_move(items, at("2026-11-16T17:50:00Z"), None)
    assert move.until == at("2026-11-18T17:00:00Z")
    assert move.stopped_on is not None and move.stopped_on.name == "receipt_R-3.txt"
    assert move.play == ()
    following = plan_move(items, move.until, None)
    assert following.stopped_on is not None and following.stopped_on.name == "email_INV-4.eml"


def test_next_stops_at_a_ledger_files_later_line(items: tuple[TimelineItem, ...]) -> None:
    move = plan_move(items, at("2026-11-19T17:00:00Z"), None)
    assert move.until == at("2026-11-24T00:00:00Z")
    assert move.play == ()
    assert move.stopped_on is not None and move.stopped_on.line_id == "L-9001-0002"


def test_the_timeline_only_moves_forward(items: tuple[TimelineItem, ...]) -> None:
    with pytest.raises(MoveRefused, match="forward"):
        plan_move(items, at("2026-11-20T00:00:00Z"), at("2026-11-19T00:00:00Z"))
    # Moving to "now" itself plays nothing.
    still = plan_move(items, at("2026-11-20T00:00:00Z"), at("2026-11-20T00:00:00Z"))
    assert still.play == () and still.passed == ()


def test_next_with_nothing_left_is_refused(items: tuple[TimelineItem, ...]) -> None:
    with pytest.raises(MoveRefused, match="Nothing"):
        plan_move(items, at("2026-12-07T00:00:00Z"), None)


def test_checks_dates_are_stops_and_come_after_arrivals_at_the_same_time(
    items: tuple[TimelineItem, ...],
) -> None:
    dates = checks_items(
        [
            ChecksDate(at("2026-11-24T00:00:00Z"), "The closeout window opens"),
            ChecksDate(at("2026-11-20T00:00:00Z"), "A snooze ends"),
        ]
    )
    merged = merge(items, dates)
    move = plan_move(merged, at("2026-11-19T17:00:00Z"), None)
    assert move.until == at("2026-11-20T00:00:00Z")
    assert move.stopped_on is not None and move.stopped_on.kind is ItemKind.CHECKS_DATE
    assert move.play == ()
    nov24 = [i.name for i in merged if i.at == at("2026-11-24T00:00:00Z")]
    assert nov24 == ["L-9001-0002", "The closeout window opens"]
    assert dates[0].id == "checks-20261120T000000-1"


def test_finished_ignores_checks_dates_and_waiting_items(items: tuple[TimelineItem, ...]) -> None:
    later = checks_items([ChecksDate(at("2027-01-01T00:00:00Z"), "The closeout window opens")])
    merged = merge(items, later)
    assert not finished(merged, at("2026-12-06T00:00:00Z"))
    # The user's two items were never delivered, and the timeline is still finished.
    assert finished(merged, at("2026-12-07T00:00:00Z"))


def test_a_users_item_waits_from_its_date_until_its_delivered(
    pack: SamplePack, items: tuple[TimelineItem, ...]
) -> None:
    nothing = OnGrant()
    assert deliveries(pack, items, at("2026-11-18T16:59:00Z"), nothing) == []
    assert names(deliveries(pack, items, at("2026-11-18T17:00:00Z"), nothing)) == [
        "receipt_R-3.txt"
    ]
    # It stays whatever moves come after.
    waiting = deliveries(pack, items, at("2027-06-01T00:00:00Z"), nothing)
    assert names(waiting) == ["receipt_R-3.txt", "email_INV-4.eml"]

    receipt = OnGrant(by_sha={pack.sha256("receipt_R-3.txt"): at("2026-11-18T18:00:00Z")})
    assert names(deliveries(pack, items, at("2027-06-01T00:00:00Z"), receipt)) == [
        "email_INV-4.eml"
    ]


def test_an_email_counts_as_delivered_by_its_message_id(
    pack: SamplePack, items: tuple[TimelineItem, ...]
) -> None:
    email = items[5].event
    assert email is not None
    forwarded = at("2026-11-19T18:00:00Z")
    by_id = OnGrant(by_message_id={"fwd-inv-4@university.example": forwarded})
    assert delivered_at(pack, email, by_id) == forwarded
    # Or by the same bytes, by any channel; the first arrival counts.
    earlier = at("2026-11-19T17:30:00Z")
    both = OnGrant(
        by_sha={pack.sha256("email_INV-4.eml"): earlier}, by_message_id=by_id.by_message_id
    )
    assert delivered_at(pack, email, both) == earlier
    assert delivered_at(pack, email, OnGrant(by_message_id={"other@x.example": forwarded})) is None


def test_a_delivered_item_leaves_coming_up(
    pack: SamplePack, items: tuple[TimelineItem, ...]
) -> None:
    now = at("2026-11-17T00:00:00Z")
    assert "receipt_R-3.txt" in names(coming_up(pack, items, now, OnGrant()))
    early = OnGrant(by_sha={pack.sha256("receipt_R-3.txt"): at("2026-11-16T20:00:00Z")})
    assert "receipt_R-3.txt" not in names(coming_up(pack, items, now, early))


def test_still_reading() -> None:
    assert still_reading(1)
    assert not still_reading(0)


def test_the_repos_samples_play_in_order() -> None:
    for sample in (SMALL_SAMPLE, LARGER_SAMPLE):
        pack = load_pack(sample)
        items = pack_items(pack)
        start = plan_start(items, pack.starts_at)
        assert start.play and all(e.at == pack.starts_at for e in start.play)
        now, played = pack.starts_at, list(start.play)
        while not finished(items, now):
            move = plan_move(items, now, None)
            assert move.until > now
            played += move.play
            now = move.until
        assert [e.id for e in played] == [e.id for e in pack.events if not e.deliver_by_user]
