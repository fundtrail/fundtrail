"""The checker against the disk stand-ins: no Google account needed."""

import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.contracts.mail import CheckerProgress, HeldFile, HeldMail, SkippedFile
from app.ingest import drive_files, email_files
from app.ingest.checker import CheckState, check_drive, check_mail, check_once
from app.ingest.drive_files import SETTLE, folder_id_from_link
from app.ingest.incoming import (
    GrantRoute,
    IncomingFile,
    PendingHold,
    let_in_skips,
    to_held_mail,
)
from app.ingest.sources import (
    EXPORT_LIMIT_BYTES,
    GOOGLE_DOC,
    GOOGLE_DRAWING,
    DiskDrive,
    DiskMailbox,
)

from .mail_factory import (
    MAILBOX,
    PI,
    STRANGER,
    email,
    forwarding,
    gmail_auth,
    with_attachments,
    with_from_lines,
)

# Grant g1's "now". Most tests use one grant; the grant-clock tests below add g2's.
G1_NOW = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
ROUTE = GrantRoute(
    workspace_id="w1",
    grant_id="g1",
    tag="abc23def",
    drive_folder_id="grant-g1",
    known_senders=frozenset({PI}),
    address_created_at=datetime(2026, 3, 1, tzinfo=UTC),
)
ROUTE_2 = GrantRoute(
    workspace_id="w1", grant_id="g2", tag="g2tag234", known_senders=frozenset({PI})
)


class MemorySink:
    def __init__(self) -> None:
        self.stored: list[IncomingFile] = []
        self.held: list[PendingHold] = []
        self.skipped: list[SkippedFile] = []

    def store(self, files: list[IncomingFile], skipped: Sequence[SkippedFile] = ()) -> None:
        self.stored.extend(files)
        self.skipped.extend(skipped)

    def hold(self, held: PendingHold) -> None:
        self.held.append(held)

    def skip(self, skipped: SkippedFile) -> None:
        self.skipped.append(skipped)


def stored_hold(pending: PendingHold) -> HeldMail:
    """The contract's held message a sink would save for `pending`."""
    files = tuple(
        HeldFile(
            name=f.name, media_type=f.media_type, storage_path=f"held/{f.key}", sha256=f.sha256
        )
        for f in pending.files
    )
    return to_held_mail(pending, held_id="h1", files=files)


def now(_grant_id: str) -> datetime:
    return G1_NOW


def write_mail(folder: Path, name: str, msg) -> None:
    (folder / f"{name}.eml").write_bytes(msg.as_bytes())


@pytest.fixture
def mailbox(tmp_path: Path) -> tuple[DiskMailbox, Path, CheckState]:
    """A mailbox already checked once, with nothing in it yet."""
    folder = tmp_path / "mail"
    folder.mkdir()
    source = DiskMailbox(folder)
    state = CheckState()
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=MemorySink())
    return source, folder, state


def check(source, state, routes=(ROUTE,)) -> MemorySink:
    sink = MemorySink()
    check_mail(source, mailbox=MAILBOX, routes=list(routes), state=state, now=now, sink=sink)
    return sink


def test_first_check_takes_everything_sent_to_the_address_since_it_was_made(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "mail"
    folder.mkdir()
    write_mail(folder, "000-old", email(sent="Mon, 02 Feb 2026 09:00:00 +0000"))
    write_mail(folder, "001-sent", email(subject="Before the first check"))
    write_mail(folder, "002-other", email(to=MAILBOX, subject="Never sent to the grant"))
    source, state = DiskMailbox(folder), CheckState()

    sink = check(source, state)
    assert [f.name for f in sink.stored] == ["Before the first check.eml"]
    assert sink.stored[0].arrived_at == G1_NOW

    # From then on the saved position is used, and nothing arrives twice.
    write_mail(folder, "003-new", email(subject="Later"))
    sink = check(source, state)
    assert [f.name for f in sink.stored] == ["Later.eml"]

    # A grant added later gets its own first read.
    write_mail(folder, "004-g2", email(to="fundtrail-demo+g2tag234@mail.example", subject="G2"))
    sink = check(source, state, routes=(ROUTE, ROUTE_2))
    assert [(f.grant_id, f.name) for f in sink.stored] == [("g2", "G2.eml")]
    assert check(source, state, routes=(ROUTE, ROUTE_2)).stored == []


def test_known_sender_arrives_at_the_grants_now(mailbox) -> None:
    source, folder, state = mailbox
    write_mail(
        folder, "001", with_attachments(email(delivered_to="fundtrail-demo+abc23def@mail.example"))
    )
    sink = check(source, state)
    assert [f.name for f in sink.stored][1:] == ["invoice_1001.pdf"]
    assert all(f.arrived_at == G1_NOW and f.grant_id == "g1" for f in sink.stored)
    # The same message seen again doesn't arrive twice.
    state.mail_cursor = "000"
    assert check(source, state).stored == []


def test_no_tag_or_unknown_tag_is_ignored(mailbox) -> None:
    source, folder, state = mailbox
    write_mail(folder, "001", email(to=MAILBOX))
    write_mail(folder, "002", email(to="fundtrail-demo+zzzz9999@mail.example"))
    sink = check(source, state)
    assert sink.stored == [] and sink.held == []


@pytest.mark.parametrize(
    "auth",
    [
        "fail",
        None,  # no result
        "mx.forged.example; dmarc=pass header.from=university.example",  # not the mailbox's
    ],
)
def test_known_sender_that_cant_be_verified_is_held(mailbox, auth) -> None:
    source, folder, state = mailbox
    write_mail(folder, "001", email(auth=auth))
    sink = check(source, state)
    assert sink.stored == []
    (held,) = sink.held
    assert held.sender == PI and held.reason == "unverified_sender"


def test_a_forged_result_below_the_mailboxs_own_is_not_read(mailbox) -> None:
    source, folder, state = mailbox
    msg = email(auth="fail")
    msg["Authentication-Results"] = gmail_auth(PI, "pass")  # added below Gmail's own
    write_mail(folder, "001", msg)
    assert check(source, state).held[0].reason == "unverified_sender"


def test_forwarded_message_is_judged_on_the_forwarder(mailbox) -> None:
    source, folder, state = mailbox
    inner = email(sender="vendor@vendor.example", subject="Invoice 1001", auth="fail")
    write_mail(folder, "001", forwarding(inner))
    sink = check(source, state)
    assert sink.held == [] and sink.stored[0].sender == PI


def test_unknown_sender_is_held_and_arrives_when_let_in(mailbox) -> None:
    source, folder, state = mailbox
    write_mail(folder, "001", with_attachments(email(sender=STRANGER)))
    sink = check(source, state)
    assert sink.stored == []
    (held,) = sink.held
    assert held.sender == STRANGER and held.held_at == G1_NOW
    assert held.reason == "unknown_sender"
    assert all(f.arrived_at is None for f in held.files)
    contract = stored_hold(held)
    assert contract.source_ref == "001" and contract.reason == "unknown_sender"
    assert [f.name for f in contract.files][1:] == ["invoice_1001.pdf"]


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
    assert all(f.arrived_at == G1_NOW and f.source == "drive" for f in sink.stored)

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

        def fetch_delivered_to(self, address, since):
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


@pytest.mark.parametrize(
    "link",
    [
        "https://evil.example/?u=drive.google.com/drive/folders/1AbC",
        "https://evil.example/drive.google.com/open?id=1AbC",
    ],
)
def test_folder_link_must_be_on_drives_host(link: str) -> None:
    with pytest.raises(ValueError):
        folder_id_from_link(link)


# Review fixes


def test_known_senders_and_tags_are_lower_cased() -> None:
    route = GrantRoute(
        "w1", "g1", "ABC23DEF", known_senders=frozenset({"Pat.Rivera@University.example"})
    )
    assert route.known_senders == {PI} and route.tag == "abc23def"


def test_a_forged_from_line_is_held_as_unverified(mailbox) -> None:
    source, folder, state = mailbox
    raw = with_from_lines(email(), [f"{PI} <evil@bad.example>"])
    (folder / "001.eml").write_bytes(raw)
    sink = check(source, state)
    assert sink.stored == []
    (held,) = sink.held
    assert held.reason == "unverified_sender" and held.sender is None
    assert "evil@bad.example" in held.from_header


class FlakySink(MemorySink):
    """Fails the first `failures` stores."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    def store(self, files: list[IncomingFile], skipped: Sequence[SkippedFile] = ()) -> None:
        if self.failures:
            self.failures -= 1
            raise RuntimeError("database down")
        super().store(files, skipped)


def test_a_failed_store_loses_no_mail(mailbox) -> None:
    source, folder, state = mailbox
    cursor_before = state.mail_cursor
    write_mail(folder, "001", email(subject="First"))
    write_mail(folder, "002", email(subject="Second"))
    sink = FlakySink(failures=1)
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=sink)
    assert [f.name for f in sink.stored] == ["Second.eml"]
    assert state.mail_cursor == cursor_before  # the batch had a failure: position kept
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=sink)
    assert [f.name for f in sink.stored] == ["Second.eml", "First.eml"]
    assert state.mail_cursor == "002"


def test_a_failed_first_read_is_tried_again(tmp_path: Path) -> None:
    folder = tmp_path / "mail"
    folder.mkdir()
    write_mail(folder, "001", email(subject="Early"))
    source, state = DiskMailbox(folder), CheckState()
    sink = FlakySink(failures=1)
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=sink)
    assert sink.stored == [] and ROUTE.grant_id not in state.first_search_done
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=sink)
    assert [f.name for f in sink.stored] == ["Early.eml"]


def test_one_grants_drive_failure_doesnt_stop_the_others(tmp_path: Path) -> None:
    touch(tmp_path / "grant-g2" / "quote.pdf", b"%PDF", OLD)
    gone = GrantRoute("w1", "g1", "abc23def", drive_folder_id="no-longer-shared")
    g2 = GrantRoute("w1", "g2", "g2tag234", drive_folder_id="grant-g2")

    class Unshared(DiskDrive):
        def list_tree(self, folder_id: str):
            if folder_id == "no-longer-shared":
                raise PermissionError("not shared")
            return super().list_tree(folder_id)

    sink = MemorySink()
    check_drive(Unshared(tmp_path), routes=[gone, g2], state=CheckState(), now=now, sink=sink)
    assert [(f.grant_id, f.name) for f in sink.stored] == [("g2", "quote.pdf")]


def test_a_new_modified_time_alone_stores_no_copy(tmp_path: Path) -> None:
    path = tmp_path / "grant-g1" / "quote.pdf"
    touch(path, b"%PDF same", OLD * 2)
    source, state, sink = DiskDrive(tmp_path), CheckState(), MemorySink()
    check_drive(source, routes=[ROUTE], state=state, now=now, sink=sink)
    touch(path, b"%PDF same", OLD)  # touched, bytes unchanged
    check_drive(source, routes=[ROUTE], state=state, now=now, sink=sink)
    assert len(sink.stored) == 1


def test_google_files_that_cant_be_exported_are_skipped_once(tmp_path: Path) -> None:
    folder = tmp_path / "grant-g1"
    touch(folder / "Survey.gform", b"", OLD)
    touch(folder / "Diagram.gdraw", b"%PDF drawing", OLD)
    touch(folder / "Huge.gdoc", b"x" * (EXPORT_LIMIT_BYTES + 1), OLD)

    class Counting(DiskDrive):
        exports = 0

        def export_pdf(self, file_id: str) -> bytes:
            Counting.exports += 1
            return super().export_pdf(file_id)

    source, state, sink = Counting(tmp_path), CheckState(), MemorySink()
    check_drive(source, routes=[ROUTE], state=state, now=now, sink=sink)
    assert [(f.name, f.exported_from) for f in sink.stored] == [("Diagram.pdf", GOOGLE_DRAWING)]
    exports = Counting.exports
    check_drive(source, routes=[ROUTE], state=state, now=now, sink=sink)
    assert Counting.exports == exports  # not tried again every check
    assert len(sink.stored) == 1
    # Each file that wasn't taken in is reported once, so the grant shows a problem.
    assert sorted((s.name, s.reason) for s in sink.skipped) == [
        ("Huge", "too_large"),
        ("Survey", "not_exportable"),
    ]
    assert all(
        s.source == "drive"
        and s.source_ref == "grant-g1"
        and s.skipped_at == G1_NOW
        and s.grant_id == "g1"
        for s in sink.skipped
    )


def test_drive_files_over_the_size_limit_are_skipped(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(drive_files, "MAX_FILE_BYTES", 3)
    touch(tmp_path / "grant-g1" / "big.pdf", b"%PDF big", OLD)
    sink = MemorySink()
    check_drive(DiskDrive(tmp_path), routes=[ROUTE], state=CheckState(), now=now, sink=sink)
    assert sink.stored == []
    assert [(s.name, s.reason) for s in sink.skipped] == [("big.pdf", "too_large")]


def test_a_too_large_attachment_is_reported_when_the_mail_arrives(mailbox, monkeypatch) -> None:
    monkeypatch.setattr(email_files, "MAX_FILE_BYTES", 10)
    source, folder, state = mailbox
    write_mail(folder, "001", with_attachments(email()))
    sink = check(source, state)
    assert [(s.name, s.reason, s.source, s.source_ref) for s in sink.skipped] == [
        ("invoice_1001.pdf", "too_large", "gmail", "001")
    ]
    assert sink.skipped[0].skipped_at == G1_NOW


@pytest.mark.parametrize("auth", ["pass", "fail"])  # a stranger, and an unverified known sender
def test_held_mail_never_reports_a_skipped_file_until_let_in(mailbox, monkeypatch, auth) -> None:
    monkeypatch.setattr(email_files, "MAX_FILE_BYTES", 10)
    source, folder, state = mailbox
    sender = STRANGER if auth == "pass" else PI
    write_mail(folder, "001", with_attachments(email(sender=sender, auth=auth)))
    sink = check(source, state)
    assert sink.skipped == [] and sink.stored == []
    (held,) = sink.held
    contract = stored_hold(held)
    assert [(s.name, s.source_ref, s.skipped_at) for s in contract.skipped] == [
        ("invoice_1001.pdf", "001", G1_NOW)
    ]
    later = G1_NOW + timedelta(days=1)
    assert [(s.name, s.skipped_at) for s in let_in_skips(contract, later)] == [
        ("invoice_1001.pdf", later)
    ]


def test_progress_round_trips_through_the_contract(mailbox, tmp_path: Path) -> None:
    source, folder, state = mailbox
    write_mail(folder, "001", email())
    touch(tmp_path / "grant-g1" / "quote.pdf", b"%PDF", OLD)
    check(source, state)
    check_drive(DiskDrive(tmp_path), routes=[ROUTE], state=state, now=now, sink=MemorySink())
    progress = state.to_progress()
    assert isinstance(progress, CheckerProgress)
    assert progress.first_search_done == ("g1",) and progress.seen_message_ids == ("001",)
    assert [v.drive_file_id for v in progress.drive_versions] == ["grant-g1/quote.pdf"]
    again = CheckState.from_progress(progress)
    assert again.to_progress() == progress


def test_a_first_search_cut_off_partway_is_redone_in_full_after_a_restart(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "mail"
    folder.mkdir()
    write_mail(folder, "001", email(subject="One"))
    write_mail(folder, "002", email(subject="Two"))
    source, state = DiskMailbox(folder), CheckState()

    class CutOff(MemorySink):
        """Stores the first message, then the process stops."""

        def store(self, files, skipped=()):
            if self.stored:
                raise RuntimeError("restart")
            super().store(files, skipped)

    first = CutOff()
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=first)
    progress = state.to_progress()  # saved as the process stops
    assert progress.first_search_done == ()  # the search didn't finish
    restarted = CheckState.from_progress(progress)
    second = MemorySink()
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=restarted, now=now, sink=second)
    assert [f.name for f in first.stored + second.stored] == ["One.eml", "Two.eml"]
    assert restarted.to_progress().first_search_done == ("g1",)


def test_a_message_is_stored_once_with_its_skips_even_if_saving_them_fails(
    mailbox, monkeypatch
) -> None:
    monkeypatch.setattr(email_files, "MAX_FILE_BYTES", 10)
    source, folder, state = mailbox
    write_mail(folder, "001", with_attachments(email()))

    class SkipsFailOnce(MemorySink):
        failed = False

        def store(self, files, skipped=()):
            # One write: if the skips can't be saved, nothing of the message is.
            if skipped and not self.failed:
                self.failed = True
                raise RuntimeError("could not save the skips")
            super().store(files, skipped)

    sink = SkipsFailOnce()
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=sink)
    assert sink.stored == [] and sink.skipped == []
    check_mail(source, mailbox=MAILBOX, routes=[ROUTE], state=state, now=now, sink=sink)
    assert [f.name for f in sink.stored] == ["Approval for sequencing, award SYN-2401.eml"]
    assert [s.name for s in sink.skipped] == ["invoice_1001.pdf"]


def test_disk_drive_refuses_paths_outside_its_root(tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("x")
    (tmp_path / "root").mkdir()
    drive = DiskDrive(tmp_path / "root")
    with pytest.raises(ValueError):
        drive.download("../secret.txt")
    with pytest.raises(ValueError):
        drive.list_tree("../")


def test_mail_that_arrives_before_its_grants_route_is_known_isnt_lost(mailbox) -> None:
    source, folder, state = mailbox
    write_mail(folder, "001", email(to="fundtrail-demo+g2tag234@mail.example", subject="Early"))
    assert check(source, state).stored == []  # no route for g2 yet: ignored, not seen
    sink = check(source, state, routes=(ROUTE, ROUTE_2))  # g2's first read finds it
    assert [(f.grant_id, f.name) for f in sink.stored] == [("g2", "Early.eml")]
    assert check(source, state, routes=(ROUTE, ROUTE_2)).stored == []


# One clock per grant


G2_NOW = datetime(2026, 9, 15, 17, 30, tzinfo=UTC)


def grant_now(grant_id: str) -> datetime:
    """Two grants in the same workspace whose clocks stand at different times."""
    return {"g1": G1_NOW, "g2": G2_NOW}[grant_id]


def test_mail_takes_each_grants_own_now_and_keeps_its_original(tmp_path: Path) -> None:
    folder = tmp_path / "mail"
    folder.mkdir()
    to_g1 = email(subject="For one")
    to_g2 = email(to="fundtrail-demo+g2tag234@mail.example", subject="For two")
    held = email(to="fundtrail-demo+g2tag234@mail.example", sender=STRANGER)
    write_mail(folder, "001", to_g1)
    write_mail(folder, "002", to_g2)
    write_mail(folder, "003", held)
    g2 = GrantRoute("w1", "g2", "g2tag234", known_senders=frozenset({PI}))
    sink = MemorySink()
    check_mail(
        DiskMailbox(folder),
        mailbox=MAILBOX,
        routes=[ROUTE, g2],
        state=CheckState(),
        now=grant_now,
        sink=sink,
    )
    by_name = {f.name: f for f in sink.stored}
    assert by_name["For one.eml"].arrived_at == G1_NOW
    assert by_name["For two.eml"].arrived_at == G2_NOW
    # The stored original is the message as it arrived, whatever the grant's clock says.
    assert by_name["For one.eml"].data == to_g1.as_bytes()
    assert by_name["For two.eml"].data == to_g2.as_bytes()
    (on_hold,) = sink.held
    assert on_hold.grant_id == "g2" and on_hold.held_at == G2_NOW


def test_drive_files_and_skips_take_each_grants_own_now(tmp_path: Path) -> None:
    touch(tmp_path / "grant-g1" / "quote.pdf", b"%PDF one", OLD)
    touch(tmp_path / "grant-g2" / "quote.pdf", b"%PDF two", OLD)
    touch(tmp_path / "grant-g2" / "Survey.gform", b"", OLD)
    g2 = GrantRoute("w1", "g2", "g2tag234", drive_folder_id="grant-g2")
    sink = MemorySink()
    check_drive(
        DiskDrive(tmp_path), routes=[ROUTE, g2], state=CheckState(), now=grant_now, sink=sink
    )
    assert {(f.grant_id, f.arrived_at, f.data) for f in sink.stored} == {
        ("g1", G1_NOW, b"%PDF one"),
        ("g2", G2_NOW, b"%PDF two"),
    }
    assert [(s.grant_id, s.skipped_at) for s in sink.skipped] == [("g2", G2_NOW)]
