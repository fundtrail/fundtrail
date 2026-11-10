"""The checker against the disk stand-ins: no Google account needed."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.ingest.checker import CheckState, check_drive, check_mail, check_once
from app.ingest.drive_files import SETTLE, folder_id_from_link
from app.ingest.incoming import GrantRoute, HeldMail, IncomingFile
from app.ingest.sources import GOOGLE_DOC, DiskDrive, DiskMailbox

from .mail_factory import MAILBOX, PI, STRANGER, email, with_attachments

WORKSPACE_NOW = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
ROUTE = GrantRoute(
    workspace_id="w1",
    grant_id="g1",
    tag="abc23def",
    drive_folder_id="grant-g1",
    known_senders=frozenset({PI}),
)


class MemorySink:
    def __init__(self) -> None:
        self.stored: list[IncomingFile] = []
        self.held: list[HeldMail] = []

    def store(self, files: list[IncomingFile]) -> None:
        self.stored.extend(files)

    def hold(self, held: HeldMail) -> None:
        self.held.append(held)


def now(_workspace_id: str) -> datetime:
    return WORKSPACE_NOW


def write_mail(folder: Path, name: str, msg) -> None:
    (folder / f"{name}.eml").write_bytes(msg.as_bytes())


@pytest.fixture
def mailbox(tmp_path: Path) -> tuple[DiskMailbox, Path, CheckState]:
    folder = tmp_path / "mail"
    folder.mkdir()
    write_mail(folder, "000-before", email())  # was there before the first check
    source = DiskMailbox(folder)
    state = CheckState()
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=MemorySink())
    return source, folder, state


def test_first_check_starts_from_now(mailbox) -> None:
    source, _, state = mailbox
    sink = MemorySink()
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=sink)
    assert sink.stored == [] and sink.held == []


def test_known_sender_arrives_at_workspace_now(mailbox) -> None:
    source, folder, state = mailbox
    write_mail(
        folder, "001", with_attachments(email(delivered_to="fundtrail-demo+abc23def@mail.example"))
    )
    sink = MemorySink()
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=sink)
    assert [f.name for f in sink.stored][1:] == ["invoice_1001.pdf"]
    assert all(f.arrived_at == WORKSPACE_NOW and f.grant_id == "g1" for f in sink.stored)
    # The same message seen again doesn't arrive twice.
    state.mail_cursor = "000-before"
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=sink)
    assert len(sink.stored) == 2


def test_no_tag_or_unknown_tag_is_ignored(mailbox) -> None:
    source, folder, state = mailbox
    write_mail(folder, "001", email(to=MAILBOX))
    write_mail(folder, "002", email(to="fundtrail-demo+zzzz9999@mail.example"))
    sink = MemorySink()
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=sink)
    assert sink.stored == [] and sink.held == []


def test_unknown_sender_is_held_and_arrives_when_let_in(mailbox) -> None:
    source, folder, state = mailbox
    write_mail(folder, "001", with_attachments(email(sender=STRANGER)))
    sink = MemorySink()
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=sink)
    assert sink.stored == []
    (held,) = sink.held
    assert held.sender == STRANGER and held.held_at == WORKSPACE_NOW
    assert all(f.arrived_at is None for f in held.files)
    later = WORKSPACE_NOW + timedelta(days=2)
    assert {f.arrived_at for f in held.let_in(later)} == {later}


# Drive


def touch(path: Path, data: bytes, age: timedelta) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    stamp = (datetime.now(UTC) - age).timestamp()
    os.utime(path, (stamp, stamp))


OLD = SETTLE * 2


def test_drive_new_modified_settling_and_exports(tmp_path: Path) -> None:
    folder = tmp_path / "grant-g1"
    touch(folder / "quote.pdf", b"%PDF quote v1", OLD)
    touch(folder / "receipts" / "photo.jpg", b"jpeg bytes", OLD)
    touch(folder / "Budget justification.gdoc", b"%PDF exported", OLD)
    touch(folder / "draft.pdf", b"%PDF being written", timedelta(minutes=1))
    source, state, sink = DiskDrive(tmp_path), CheckState(), MemorySink()

    check_drive(source, routes=[ROUTE], state=state, now=now, sink=sink)
    by_name = {f.name: f for f in sink.stored}
    assert set(by_name) == {"quote.pdf", "photo.jpg", "Budget justification.pdf"}
    export = by_name["Budget justification.pdf"]
    assert export.exported_from == GOOGLE_DOC and export.media_type == "application/pdf"
    assert by_name["quote.pdf"].exported_from is None
    assert all(f.arrived_at == WORKSPACE_NOW and f.source == "drive" for f in sink.stored)

    # Nothing changed: nothing new.
    check_drive(source, routes=[ROUTE], state=state, now=now, sink=sink)
    assert len(sink.stored) == 3

    # A modified file arrives again as a new file once it settles; the draft too.
    touch(folder / "quote.pdf", b"%PDF quote v2", SETTLE + timedelta(minutes=1))
    touch(folder / "draft.pdf", b"%PDF being written", OLD)
    check_drive(source, routes=[ROUTE], state=state, now=now, sink=sink)
    assert [f.name for f in sink.stored[3:]] == ["draft.pdf", "quote.pdf"]
    assert sink.stored[-1].data == b"%PDF quote v2"


def test_check_once_survives_a_failing_source(tmp_path: Path) -> None:
    class Broken:
        def fetch_new(self, cursor):
            raise RuntimeError("down")

    touch(tmp_path / "grant-g1" / "quote.pdf", b"%PDF", OLD)
    sink = MemorySink()
    check_once(
        mail=Broken(),
        drive=DiskDrive(tmp_path),
        mailbox=MAILBOX,
        routes=[ROUTE],
        state=CheckState(),
        now=now,
        sink=sink,
    )
    assert [f.name for f in sink.stored] == ["quote.pdf"]


@pytest.mark.parametrize(
    "link",
    [
        "https://drive.google.com/drive/folders/1AbC-d_E?usp=sharing",
        "https://drive.google.com/drive/u/0/folders/1AbC-d_E",
        "https://drive.google.com/open?id=1AbC-d_E",
    ],
)
def test_folder_id_from_link(link: str) -> None:
    assert folder_id_from_link(link) == "1AbC-d_E"


def test_folder_link_rejects_other_links() -> None:
    with pytest.raises(ValueError):
        folder_id_from_link("https://example.com/folders/x")
