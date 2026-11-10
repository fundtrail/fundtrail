"""Reading a sample's folder (issue 165)."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.contracts.api import ArrivalSource
from app.contracts.records import RecordKind
from app.samples.pack import (
    LARGER_SAMPLE,
    SMALL_SAMPLE,
    SUGGESTION_KINDS,
    EventKind,
    PackError,
    event_id,
    load_folder,
    load_pack,
)

from .packs import ACTIONS, EVENTS, FILES, write_pack


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def test_reads_the_seed_builders_layout(tmp_path: Path) -> None:
    pack = load_folder(write_pack(tmp_path / "test-sample"))
    assert pack.sample == "test-sample"
    assert pack.starts_at == at("2026-11-16T17:30:00Z")
    assert [e.id for e in pack.events] == [event_id(e.kind, e.name) for e in pack.events]
    assert pack.events[0].id.startswith("file-") and pack.events[1].id.startswith("ledger-")
    assert [e.kind for e in pack.events] == [
        EventKind.FILE,
        EventKind.LEDGER,
        EventKind.FILE,
        EventKind.FILE,
        EventKind.FILE,
        EventKind.FILE,
    ]
    gmail = pack.events[3]
    assert gmail.source is ArrivalSource.GMAIL and gmail.sender == "pi@university.example"
    assert pack.events[1].source is ArrivalSource.LEDGER
    assert [e.deliver_by_user for e in pack.events] == [False, False, False, False, True, True]
    assert [(a.action, a.file) for a in pack.actions] == [(a["action"], a["file"]) for a in ACTIONS]
    assert pack.meta == {"award_number": "SYN-9009001"}
    assert pack.sha256("receipt_R-3.txt") == hashlib.sha256(FILES["receipt_R-3.txt"]).hexdigest()


def test_events_are_in_time_order_and_keep_their_ids(tmp_path: Path) -> None:
    events = [EVENTS[2], EVENTS[0], EVENTS[1]]
    pack = load_folder(write_pack(tmp_path / "s", events=events, actions=[]))
    assert [e.name for e in pack.events] == [
        "award_letter.txt",
        "ledger.csv",
        "invoice_INV-1.txt",
    ]
    assert pack.event(event_id(EventKind.FILE, "invoice_INV-1.txt")) is pack.events[2]


def test_ids_come_from_what_an_event_is_not_where_it_sits(tmp_path: Path) -> None:
    before = load_folder(write_pack(tmp_path / "a"))
    extra = {"at": "2026-11-16T17:35:00Z", "kind": "file", "file": "extra.txt", "source": "upload"}
    folder = write_pack(tmp_path / "b", events=[EVENTS[0], extra, *EVENTS[1:]])
    (folder / "extra.txt").write_bytes(b"An extra synthetic file.")
    after = load_folder(folder)
    ids = {e.name: e.id for e in after.events}
    assert all(ids[e.name] == e.id for e in before.events)


def test_refuses_a_file_scheduled_twice(tmp_path: Path) -> None:
    again = {**EVENTS[2], "at": "2026-11-20T00:00:00Z"}
    with pytest.raises(PackError, match="scheduled twice"):
        load_folder(write_pack(tmp_path / "s", events=[*EVENTS, again], actions=[]))


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
            "first event",
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


def test_refuses_a_delivery_before_its_date(tmp_path: Path) -> None:
    action = {"at": "2026-11-17T00:00:00Z", "action": "deliver_file", "file": "receipt_R-3.txt"}
    with pytest.raises(PackError, match="before its date"):
        load_folder(write_pack(tmp_path / "s", actions=[action]))


def test_starts_at_is_the_first_event(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="first event"):
        load_folder(write_pack(tmp_path / "s", starts_at="2026-11-01T00:00:00Z"))
    # Without one, the sample starts at its first event.
    folder = write_pack(tmp_path / "t")
    timeline = json.loads((folder / "timeline.json").read_text())
    del timeline["starts_at"]
    (folder / "timeline.json").write_text(json.dumps(timeline))
    assert load_folder(folder).starts_at == at("2026-11-16T17:30:00Z")


def test_an_email_files_message_id(tmp_path: Path) -> None:
    pack = load_folder(write_pack(tmp_path / "s"))
    assert pack.message_id("email_INV-4.eml") == "fwd-inv-4@university.example"
    assert pack.message_id("receipt_R-3.txt") is None


def test_an_unknown_sample_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="no sample"):
        load_pack("no-such-sample", tmp_path)


def test_a_pack_is_read_from_data_samples(tmp_path: Path) -> None:
    write_pack(tmp_path / "samples" / SMALL_SAMPLE)
    assert load_pack(SMALL_SAMPLE, tmp_path).files_folder == tmp_path / "samples" / SMALL_SAMPLE


SCRIPT = [
    {"at": "2026-11-16T17:40:00Z", "action": "confirm_terms", "file": "award_letter.txt"},
    {
        "at": "2026-11-20T00:00:00Z",
        "action": "decide_suggestion",
        "suggestion": "link",
        "decision": "accept",
        "line_id": "L-9001-0001",
    },
    {
        "at": "2026-11-21T00:00:00Z",
        "action": "answer_flag",
        "line_id": "L-9001-0001",
        "answer": "supports",
    },
    {
        "at": "2026-11-22T00:00:00Z",
        "action": "enter_share",
        "line_id": "L-9001-0001",
        "file": "invoice_INV-1.txt",
        "share": "56",
        "out_of": 96,
        "basis": "The PI's email gives 56 of the 96 samples.",
        "note": "S3a",
    },
]


def test_the_script_keeps_every_reference(tmp_path: Path) -> None:
    pack = load_folder(write_pack(tmp_path / "s", actions=SCRIPT))
    confirm, decide, answer, share = pack.actions
    assert (confirm.action, confirm.file) == ("confirm_terms", "award_letter.txt")
    assert (decide.suggestion, decide.decision, decide.line_id) == ("link", "accept", "L-9001-0001")
    assert (answer.line_id, answer.answer) == ("L-9001-0001", "supports")
    assert (share.line_id, share.file, share.share, share.out_of) == (
        "L-9001-0001",
        "invoice_INV-1.txt",
        56,
        96,
    )
    assert share.basis and share.note == "S3a"


@pytest.mark.parametrize(
    ("action", "message"),
    [
        ({"at": "2026-11-20T00:00:00Z", "action": "dance"}, "isn't one of"),
        ({"at": "2026-11-20T00:00:00Z", "action": "answer_flag", "line_id": "L-1"}, "takes"),
        (
            {"at": "2026-11-20T00:00:00Z", "action": "confirm_terms", "file": "a", "line_id": "L"},
            "takes",
        ),
        (
            {
                "at": "2026-11-20T00:00:00Z",
                "action": "decide_suggestion",
                "suggestion": "link",
                "decision": "maybe",
                "file": "a",
            },
            "accept or reject",
        ),
        (
            {
                "at": "2026-11-20T00:00:00Z",
                "action": "decide_suggestion",
                "suggestion": "link",
                "decision": "accept",
            },
            "line_id or a file",
        ),
        # Ruling 51: the seed's own rules.
        ({**SCRIPT[2], "answer": "yes"}, "an answer is one of"),
        ({**SCRIPT[1], "suggestion": "bill"}, "suggestion 'bill' isn't one of"),
        ({**SCRIPT[1], "suggestion": "confirmation"}, "isn't one of"),
        ({**SCRIPT[2], "line_id": "L-0000-0000"}, "has no line L-0000-0000"),
        ({**SCRIPT[1], "line_id": None, "file": "nope.txt"}, "isn't on the timeline"),
        # L-9001-0002 arrives at 00:00 UTC on Nov 24: a share on Nov 22 comes too soon.
        ({**SCRIPT[3], "line_id": "L-9001-0002"}, "before line L-9001-0002 arrives"),
        ({**SCRIPT[3], "at": "2026-11-16T17:45:00Z"}, "before line L-9001-0001 arrives"),
        ({**SCRIPT[0], "at": "2026-11-16T17:30:00Z"}, "before award_letter.txt arrives"),
        # A file the user brings in arrives when the script brings it in, and here it never does.
        (
            {"at": "2026-11-20T00:00:00Z", "action": "confirm_terms", "file": "receipt_R-3.txt"},
            "before receipt_R-3.txt arrives",
        ),
        ({**SCRIPT[3], "share": "half"}, "are numbers"),
        ({**SCRIPT[3], "out_of": 0}, "out_of above 0"),
        ({**SCRIPT[3], "share": "97"}, "from 0 to out_of"),
        ({**SCRIPT[3], "share": -1}, "from 0 to out_of"),
        ({**SCRIPT[3], "share": "NaN"}, "are numbers"),
        ({**SCRIPT[3], "share": True}, "are numbers"),
    ],
)
def test_refuses_a_bad_script_step(tmp_path: Path, action: dict[str, Any], message: str) -> None:
    step = {k: v for k, v in action.items() if v is not None}
    with pytest.raises(PackError, match=message):
        load_folder(write_pack(tmp_path / "s", actions=[step]))


def test_a_share_can_be_a_decimal(tmp_path: Path) -> None:
    step = {**SCRIPT[3], "share": "2.5", "out_of": 7.5}
    [share] = load_folder(write_pack(tmp_path / "s", actions=[step])).actions
    assert (share.share, share.out_of) == (Decimal("2.5"), Decimal("7.5"))


def test_a_step_on_a_users_file_comes_after_the_script_brings_it_in(tmp_path: Path) -> None:
    bring = {"at": "2026-11-18T17:00:00Z", "action": "deliver_file", "file": "receipt_R-3.txt"}
    confirm = {"at": "2026-11-18T17:01:00Z", "action": "confirm_terms", "file": "receipt_R-3.txt"}
    assert len(load_folder(write_pack(tmp_path / "s", actions=[bring, confirm])).actions) == 2
    with pytest.raises(PackError, match="before receipt_R-3.txt arrives"):
        load_folder(write_pack(tmp_path / "t", actions=[bring, {**confirm, "at": bring["at"]}]))


def test_suggestion_kinds_are_record_kinds() -> None:
    assert {RecordKind(k) for k in SUGGESTION_KINDS} == set(SUGGESTION_KINDS)


# The two samples in the repo, from data/samples/.


def test_the_larger_sample() -> None:
    pack = load_pack(LARGER_SAMPLE)
    assert pack.starts_at == at("2024-01-18T17:00:00Z")
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
    assert pack.starts_at == at("2026-11-16T17:30:00Z")
    assert pack.events[0].name == "award_letter.pdf"
    marked = {e.name: e.at for e in pack.events if e.deliver_by_user}
    assert sorted(marked) == [
        "email_invoice_ESS-32410.eml",
        "hardware_receipt.jpg",
        "invoice_EES-7420.pdf",
    ]
    assert pack.actions[0].action == "confirm_terms" and pack.actions[0].file == "award_letter.pdf"
    deliveries = [a for a in pack.actions if a.action == "deliver_file"]
    # The script brings in each marked file on its date.
    assert sorted((a.file, a.at) for a in deliveries) == sorted(marked.items())
    assert [e for e in pack.events if e.kind is EventKind.LEDGER] == [pack.events[1]]


def test_ids_are_the_same_on_every_load() -> None:
    first, second = load_pack(LARGER_SAMPLE), load_pack(LARGER_SAMPLE)
    assert [(e.id, e.name) for e in first.events] == [(e.id, e.name) for e in second.events]
    assert len({e.id for e in first.events}) == len(first.events)
