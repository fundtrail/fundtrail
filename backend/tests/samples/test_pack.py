"""Reading a sample's folder (issue 165)."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contracts.api import ArrivalSource
from app.samples.pack import (
    LARGER_SAMPLE,
    SMALL_SAMPLE,
    EventKind,
    PackError,
    load_folder,
    load_pack,
)

from .packs import ACTIONS, EVENTS, FILES, write_pack


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def test_reads_the_seed_builders_layout(tmp_path: Path) -> None:
    pack = load_folder(write_pack(tmp_path / "test-sample"))
    assert pack.sample == "test-sample"
    assert pack.starts_at == pack.opens_at == at("2026-11-16T17:30:00Z")
    assert [e.id for e in pack.events] == ["e001", "e002", "e003", "e004", "e005"]
    assert [e.kind for e in pack.events] == [
        EventKind.FILE,
        EventKind.LEDGER,
        EventKind.FILE,
        EventKind.FILE,
        EventKind.FILE,
    ]
    gmail = pack.events[3]
    assert gmail.source is ArrivalSource.GMAIL and gmail.sender == "pi@university.example"
    assert pack.events[1].source is ArrivalSource.LEDGER
    assert [e.deliver_by_user for e in pack.events] == [False, False, False, False, True]
    assert [(a.action, a.file) for a in pack.actions] == [(a["action"], a["file"]) for a in ACTIONS]
    assert pack.meta == {"award_number": "SYN-9009001"}
    assert pack.sha256("receipt_R-3.txt") == hashlib.sha256(FILES["receipt_R-3.txt"]).hexdigest()


def test_events_are_in_time_order_and_keep_their_ids(tmp_path: Path) -> None:
    events = [EVENTS[2], EVENTS[0], EVENTS[1]]
    pack = load_folder(write_pack(tmp_path / "s", events=events, actions=[]))
    assert [(e.id, e.name) for e in pack.events] == [
        ("e002", "award_letter.txt"),
        ("e003", "ledger.csv"),
        ("e001", "invoice_INV-1.txt"),
    ]
    assert pack.event("e001") is pack.events[2]


def test_ledger_row_is_the_header_and_that_line(tmp_path: Path) -> None:
    pack = load_folder(write_pack(tmp_path / "s"))
    lines = pack.ledger_row("L-9001-0002").decode().splitlines()
    assert lines[0].startswith("line_id,transaction_date")
    assert lines[1].startswith("L-9001-0002,2026-11-20")
    assert len(lines) == 2
    with pytest.raises(PackError):
        pack.ledger_row("L-0000-0000")


@pytest.mark.parametrize(
    ("event", "message"),
    [
        ({"at": "2026-11-16T18:00:00Z", "kind": "accountant", "action": "confirm_terms"}, "user"),
        (
            {"at": "2026-11-16T18:00:00Z", "kind": "file", "file": "nope.txt", "source": "upload"},
            "isn't in",
        ),
        (
            {
                "at": "2026-11-16T18:00:00Z",
                "kind": "file",
                "file": "../ledger.csv",
                "source": "upload",
            },
            "plain",
        ),
        (
            {
                "at": "2026-11-16T18:00:00Z",
                "kind": "file",
                "file": "receipt_R-3.txt",
                "source": "fax",
            },
            "source",
        ),
        (
            {
                "at": "2026-11-16T18:00:00",
                "kind": "file",
                "file": "receipt_R-3.txt",
                "source": "upload",
            },
            "zone",
        ),
        ({"at": "2026-11-16T18:00:00Z", "kind": "ledger_line", "line_id": "L-1"}, "no line"),
        (
            {
                "at": "2026-11-01T18:00:00Z",
                "kind": "file",
                "file": "receipt_R-3.txt",
                "source": "upload",
            },
            "before",
        ),
        (
            {
                "at": "2026-11-16T18:00:00Z",
                "kind": "file",
                "file": "receipt_R-3.txt",
                "source": "upload",
                "available_at": "2026-11-16T17:30:00Z",
            },
            "available_at",
        ),
    ],
)
def test_refuses_a_bad_event(tmp_path: Path, event: dict[str, str], message: str) -> None:
    with pytest.raises(PackError, match=message):
        load_folder(write_pack(tmp_path / "s", events=[EVENTS[0], event], actions=[]))


def test_refuses_both_a_ledger_and_ledger_lines(tmp_path: Path) -> None:
    line = {"at": "2026-11-16T18:00:00Z", "kind": "ledger_line", "line_id": "L-9001-0001"}
    with pytest.raises(PackError, match="not both"):
        load_folder(write_pack(tmp_path / "s", events=[*EVENTS, line], actions=[]))


def test_refuses_a_delivery_of_a_file_not_marked_for_the_user(tmp_path: Path) -> None:
    action = {"at": "2026-11-17T00:00:00Z", "action": "deliver_file", "file": "invoice_INV-1.txt"}
    with pytest.raises(PackError, match="not marked"):
        load_folder(write_pack(tmp_path / "s", actions=[action]))


def test_refuses_opening_before_the_start(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="opens before"):
        load_folder(write_pack(tmp_path / "s", opens_at="2026-11-01T00:00:00Z"))


def test_an_unknown_sample_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="no sample"):
        load_pack("no-such-sample", tmp_path)


def test_data_samples_wins_over_todays_layout(tmp_path: Path) -> None:
    write_pack(tmp_path / "samples" / SMALL_SAMPLE)
    assert load_pack(SMALL_SAMPLE, tmp_path).files_folder == tmp_path / "samples" / SMALL_SAMPLE


# The two samples in the repo, read from today's layout until data/samples/ lands.


def test_the_larger_sample() -> None:
    pack = load_pack(LARGER_SAMPLE)
    assert pack.starts_at == at("2024-01-18T17:00:00Z")
    assert pack.opens_at == at("2026-11-16T17:00:00Z")
    assert not any(e.deliver_by_user for e in pack.events)
    assert [(a.action, a.file) for a in pack.actions] == [("confirm_terms", "award_letter.txt")]
    lines = [e.name for e in pack.events if e.kind is EventKind.LEDGER_LINE]
    assert sorted(lines) == sorted(pack.ledger_line_ids())
    times = [e.at for e in pack.events]
    assert times == sorted(times)
    for e in pack.events:
        if e.kind is EventKind.FILE:
            assert pack.file_bytes(e.name)


def test_the_small_sample() -> None:
    pack = load_pack(SMALL_SAMPLE)
    assert pack.starts_at == pack.opens_at == at("2026-11-16T17:30:00Z")
    assert pack.events[0].name == "award_letter.pdf"
    assert [(a.action, a.file) for a in pack.actions] == [("confirm_terms", "award_letter.pdf")]
    assert sorted(e.name for e in pack.events if e.kind is EventKind.LEDGER_LINE) == sorted(
        pack.ledger_line_ids()
    )


def test_ids_are_the_same_on_every_load() -> None:
    first, second = load_pack(LARGER_SAMPLE), load_pack(LARGER_SAMPLE)
    assert [(e.id, e.name) for e in first.events] == [(e.id, e.name) for e in second.events]
    assert len({e.id for e in first.events}) == len(first.events)
