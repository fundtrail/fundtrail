from datetime import UTC, date, datetime

import pytest

from app.ingest.email_files import email_to_files, is_small_image
from app.ingest.incoming import evidence_file_fields

from .mail_factory import PDF, PI, email, forwarding, png, with_attachments, with_pasted_photo


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


def test_adapter_gives_the_contract_fields() -> None:
    files = files_of(with_attachments(email()))
    with pytest.raises(ValueError):
        evidence_file_fields(files[1], file_id="f2", parent_id="f1")
    now = datetime(2026, 3, 4, tzinfo=UTC)
    fields = evidence_file_fields(files[1].arriving(now), file_id="f2", parent_id="f1")
    assert fields["storage_path"] == "w1/g1/f2/invoice_1001.pdf"
    assert fields["parent_id"] == "f1" and fields["arrived_at"] == now
    assert set(fields) == {
        "id", "workspace_id", "grant_id", "source", "name", "media_type", "storage_path",
        "sha256", "document_date", "arrived_at", "sender", "source_ref", "parent_id",
    }  # fmt: skip
