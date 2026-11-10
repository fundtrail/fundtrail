"""The timeline player's pure logic (issue 165)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contracts.api import ArrivalSource
from app.samples.pack import LARGER_SAMPLE, SMALL_SAMPLE, SamplePack, load_folder, load_pack
from app.samples.timeline import (
    ChecksDate,
    ItemKind,
    MoveRefused,
    TimelineItem,
    checks_items,
    coming_up,
    deliveries,
    finished,
    merge,
    pack_items,
    plan_move,
    plan_start,
    reading_history,
    skip_delivery,
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


def names(items: tuple[TimelineItem, ...] | list[TimelineItem]) -> list[str]:
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
        "L-9001-0002",
        "L-9001-0003",
    ]
    later = items[5:]
    assert [i.at for i in later] == [at("2026-11-24T00:00:00Z"), at("2026-12-07T00:00:00Z")]
    assert all(i.event is None and i.source is ArrivalSource.LEDGER for i in later)
    assert [i.id for i in later] == ["e002-L-9001-0002", "e002-L-9001-0003"]
    assert items[4].kind is ItemKind.USER_DELIVERY


def test_start_plays_everything_at_the_start(items: tuple[TimelineItem, ...]) -> None:
    move = plan_start(items, at("2026-11-16T17:30:00Z"))
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
    # The ledger's later line is passed but not played: the clock releases it.
    assert names(list(move.passed)) == [
        "ledger.csv",
        "invoice_INV-1.txt",
        "invoice_INV-2.txt",
        "receipt_R-3.txt",
        "L-9001-0002",
    ]
    assert [e.name for e in move.play] == names(list(move.passed))[:4]
    assert move.stopped_on is None


def test_next_stops_at_a_ledger_files_later_line(items: tuple[TimelineItem, ...]) -> None:
    move = plan_move(items, at("2026-11-18T17:00:00Z"), None)
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
    move = plan_move(merged, at("2026-11-18T17:00:00Z"), None)
    assert move.until == at("2026-11-20T00:00:00Z")
    assert move.stopped_on is not None and move.stopped_on.kind is ItemKind.CHECKS_DATE
    assert move.play == ()
    nov24 = [i.name for i in merged if i.at == at("2026-11-24T00:00:00Z")]
    assert nov24 == ["L-9001-0002", "The closeout window opens"]
    assert dates[0].id == "checks-20261120T000000-1"


def test_finished_ignores_checks_dates(items: tuple[TimelineItem, ...]) -> None:
    later = checks_items([ChecksDate(at("2027-01-01T00:00:00Z"), "The closeout window opens")])
    merged = merge(items, later)
    assert not finished(merged, at("2026-12-06T00:00:00Z"))
    assert finished(merged, at("2026-12-07T00:00:00Z"))


def test_a_delivered_file_is_skipped_and_leaves_coming_up(
    pack: SamplePack, items: tuple[TimelineItem, ...]
) -> None:
    receipt = items[4]
    assert receipt.event is not None
    sha = pack.sha256("receipt_R-3.txt")
    assert not skip_delivery(pack, receipt.event, [])
    assert skip_delivery(pack, receipt.event, [sha])
    # Only a file marked for the user is ever skipped.
    invoice = items[2].event
    assert invoice is not None
    assert not skip_delivery(pack, invoice, [pack.sha256("invoice_INV-1.txt")])

    now = at("2026-11-17T00:00:00Z")
    assert "receipt_R-3.txt" in names(coming_up(pack, items, now, []))
    assert "receipt_R-3.txt" not in names(coming_up(pack, items, now, [sha]))


def test_deliveries_wait_from_the_opening_until_the_fallback(
    pack: SamplePack, items: tuple[TimelineItem, ...]
) -> None:
    sha = pack.sha256("receipt_R-3.txt")
    waiting = deliveries(pack, items, at("2026-11-16T17:30:00Z"), {})
    assert [(d.item.name, d.delivered_at) for d in waiting] == [("receipt_R-3.txt", None)]

    brought = at("2026-11-17T09:00:00Z")
    done = deliveries(pack, items, at("2026-11-17T10:00:00Z"), {sha: brought})
    assert [(d.item.name, d.delivered_at) for d in done] == [("receipt_R-3.txt", brought)]

    # At the fallback, the clock delivers it: it's no longer the user's to bring in.
    assert deliveries(pack, items, at("2026-11-18T17:00:00Z"), {}) == []


def test_available_at_sets_when_a_delivery_starts_waiting(tmp_path: Path) -> None:
    from .packs import EVENTS

    late = {**EVENTS[4], "available_at": "2026-11-17T12:00:00Z"}
    pack = load_folder(write_pack(tmp_path / "s", events=[*EVENTS[:4], late]))
    items = pack_items(pack)
    assert deliveries(pack, items, at("2026-11-17T11:00:00Z"), {}) == []
    assert len(deliveries(pack, items, at("2026-11-17T12:00:00Z"), {})) == 1


def test_reading_history() -> None:
    opens = at("2026-11-16T17:00:00Z")
    before, after = at("2025-01-01T00:00:00Z"), at("2026-11-20T00:00:00Z")
    assert reading_history(before, opens, [])  # the clock hasn't reached the opening
    assert reading_history(opens, opens, [before])  # a run for the history is still waiting
    assert not reading_history(opens, opens, [])
    assert not reading_history(after, opens, [opens, after])  # runs after the opening don't count


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
        assert [e.id for e in played] == [e.id for e in pack.events]


def test_the_larger_sample_jumps_to_its_opening() -> None:
    pack = load_pack(LARGER_SAMPLE)
    items = pack_items(pack)
    start = plan_start(items, pack.starts_at)
    jump = plan_move(items, pack.starts_at, pack.opens_at)
    history = [*start.play, *jump.play]
    assert history == [e for e in pack.events if e.at <= pack.opens_at]
    assert any(e.at > pack.opens_at for e in pack.events)  # arrivals left for the user to watch
