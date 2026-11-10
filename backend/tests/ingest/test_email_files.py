from datetime import UTC, date, datetime

import pytest

from app.contracts.evidence import Source
from app.ingest import email_files
from app.ingest.email_files import email_to_files, is_small_image, parse_headers
from app.ingest.incoming import safe_name, to_evidence_file

from .mail_factory import (
    PDF,
    PI,
    email,
    forwarding,
    png,
    with_attachments,
    with_from_lines,
    with_pasted_photo,
)


def files_of(msg, message_id="m1"):
    return email_to_files(msg.as_bytes(), message_id=message_id, grant_id="g1", workspace_id="w1")


def test_the_message_is_one_file_kept_as_it_arrived() -> None:
    msg = email()
    files = files_of(msg)
    assert len(files) == 1
    message = files[0]
    assert message.data == msg.as_bytes()
    assert message.media_type == "message/rfc822"
    assert message.name == "Approval for sequencing, award SYN-2401.eml"
    assert message.sender == PI
    assert message.document_date == date(2026, 3, 3)
    assert message.source == "gmail" and message.source_ref == "m1"


def test_each_attached_document_points_back_and_small_images_are_skipped() -> None:
    files = files_of(with_attachments(email()))
    names = [f.name for f in files]
    assert names[1:] == ["invoice_1001.pdf"]  # logo.png (40 by 40) skipped
    invoice = files[1]
    assert invoice.data == PDF
    assert invoice.parent_key == files[0].key
    assert invoice.media_type == "application/pdf"


def test_a_photo_pasted_in_the_body_is_kept() -> None:
    files = files_of(with_pasted_photo(email()))
    assert [f.media_type for f in files] == ["message/rfc822", "image/png"]
    assert files[1].parent_key == files[0].key


def test_attachments_of_a_message_forwarded_as_an_attachment_are_kept() -> None:
    inner = with_attachments(email(sender="vendor@vendor.example", subject="Invoice 1001"))
    files = files_of(forwarding(inner))
    assert [f.name for f in files][1:] == ["invoice_1001.pdf"]
    assert files[1].parent_key == files[0].key
    # The same invoice attached here or uploaded is the exact same file.
    assert files[1].sha256 == files_of(with_attachments(email()))[1].sha256


def test_small_image_rule() -> None:
    assert is_small_image(png(120, 60))
    assert not is_small_image(png(400, 300))
    assert not is_small_image(b"not an image")  # unreadable images are kept


def test_adapter_builds_the_contract_evidence_file() -> None:
    files = files_of(with_attachments(email()))
    with pytest.raises(ValueError):
        to_evidence_file(files[1], file_id="f2", parent_id="f1")
    now = datetime(2026, 3, 4, tzinfo=UTC)
    evidence = to_evidence_file(files[1].arriving(now), file_id="f2", parent_id="f1")
    assert evidence.storage_path == "w1/g1/f2/invoice_1001.pdf"
    assert evidence.parent_id == "f1" and evidence.arrived_at == now
    assert evidence.source == Source.GMAIL and evidence.sha256 == files[1].sha256


@pytest.mark.parametrize(
    "from_lines",
    [
        [f"{PI} <evil@bad.example>"],  # an address used as the display name, repaired
        [f"Pat <{PI}>, evil@bad.example"],  # two addresses
        [f"Pat <{PI}>", "evil@bad.example"],  # two From headers
        [f"<{PI}"],  # malformed
        [],  # no From at all
    ],
)
def test_a_from_line_that_isnt_exactly_one_clean_address_gives_no_sender(from_lines) -> None:
    raw = with_from_lines(email(), from_lines)
    assert parse_headers(raw).sender is None


def test_one_clean_address_is_the_sender() -> None:
    assert parse_headers(with_from_lines(email(), [f"Pat <{PI}>"])).sender == PI
    # A display name that looks like an address doesn't matter: the address does.
    raw = with_from_lines(email(), [f'"{PI}" <evil@bad.example>'])
    assert parse_headers(raw).sender == "evil@bad.example"


def test_attachments_over_the_size_limit_are_skipped(monkeypatch) -> None:
    monkeypatch.setattr(email_files, "MAX_FILE_BYTES", len(PDF) - 1)
    assert [f.name for f in files_of(with_attachments(email()))] == [
        "Approval for sequencing, award SYN-2401.eml"
    ]


def test_safe_name_is_ascii_and_keeps_the_extension() -> None:
    assert safe_name("Fa\u00e7ture n\u00b01/2.pdf", "x") == "Facture n1_2.pdf"
    long = safe_name("a" * 300 + ".pdf", "x")
    assert len(long) == 120 and long.endswith(".pdf")
    assert safe_name("\u62a5\u544a", "fallback") == "fallback"
    assert safe_name("../../etc", "x") == "etc"
