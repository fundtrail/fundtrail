"""The second look on photos and scanned pages (decision 0012, ruling 78). No real model.

The agent boxes each value on the image we sent. When the run ends, each photo or scanned page
gets one call that sees only the boxed areas, as numbered crops with no hint of the values. A
value read the same is confirmed; read differently, unreadable, or boxed off the image, it stays
unconfirmed. A PDF page with no text layer goes as an image, so its values can be boxed.
"""

import io
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Any

import pypdfium2 as pdfium
from anthropic.types import Message
from PIL import Image

from app.agent import RunSaved, run_once
from app.agent.files import open_file
from app.agent.model import ModelRequest
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import Bill, ImageBox
from app.contracts.runs import Trigger, TriggerKind
from app.quotes.pdf import PDFIUM_LOCK

from .fakes import FakeModel, calls, message, sample_inputs, text, tool

SAMPLE = load_sample_grant()
NOW = datetime.fromisoformat("2025-11-14T00:00:00+00:00")
TEXT_PDF = "tests/quotes/fixtures/invoice_reportlab.pdf"

PixelBox = tuple[float, float, float, float]
Boxes = dict[str, PixelBox]

# Boxes in pixels on a 1200 by 800 photo, which is sent at that size.
BOXES: Boxes = {
    "vendor": (100, 50, 500, 110),
    "dated": (100, 150, 400, 200),
    "total": (800, 650, 1100, 720),
}
VALUES = {"vendor": "Example Taxi Co.", "dated": "March 3, 2026", "total": "$45.00"}
NORMALIZED = {"dated": "2026-03-03", "total": 4500}


def photo_bytes(size: tuple[int, int] = (1200, 800)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, format="PNG")
    return out.getvalue()


def scan_pdf(pages: int = 1) -> bytes:
    """A PDF whose pages are images only, with no text layer, like a scanner makes."""
    images = [Image.new("RGB", (850, 1100), "white") for _ in range(pages)]
    out = io.BytesIO()
    images[0].save(out, format="PDF", save_all=True, append_images=images[1:], resolution=100)
    return out.getvalue()


def mixed_pdf() -> bytes:
    """A page with real text, then a scanned page."""
    with PDFIUM_LOCK:
        doc = pdfium.PdfDocument(TEXT_PDF)
        scan = pdfium.PdfDocument(scan_pdf())
        try:
            doc.import_pages(scan)
            out = io.BytesIO()
            doc.save(out)
            return out.getvalue()
        finally:
            scan.close()
            doc.close()


def evidence(file_id: str, name: str, media_type: str):
    return SAMPLE.files[1].model_copy(
        update={
            "id": file_id,
            "name": name,
            "media_type": media_type,
            "storage_path": f"ws-sample/grant-sample/{file_id}/{name}",
            "arrived_at": NOW,
        }
    )


def inputs_for(files: dict[str, tuple[Any, bytes]], trigger_id: str):
    base = sample_inputs(now=NOW, trigger=Trigger(kind=TriggerKind.FILE, id=trigger_id), records=[])
    data = {f.id: content for f, content in files.values()}
    read = base.read_file
    return replace(
        base,
        files=[*base.files, *(f for f, _ in files.values())],
        read_file=lambda f: data[f.id] if f.id in data else read(f),
    )


def boxed(field: str, file_id: str, box: PixelBox, page: int = 1):
    left, top, right, bottom = box
    out: dict[str, Any] = {
        "field": field,
        "box": {
            "file_id": file_id,
            "page": page,
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
        },
        "text": VALUES[field],
    }
    if field in NORMALIZED:
        out["value"] = NORMALIZED[field]
    return out


def write_bill(file_id: str, boxes: Boxes, page: int = 1):
    values = [boxed(f, file_id, b, page) for f, b in boxes.items()]
    return lambda r: calls(tool("write_fact", kind="bill", values=values))


def second_look_reply(readings: list[str], seen: list[ModelRequest]) -> Callable[..., Message]:
    """The fake second look: checks it was sent only crops, then replies with `readings`.

    The crops come in the record's field order: a bill's total, then vendor, then date.
    """

    def step(request: ModelRequest) -> Message:
        assert request.tools == []  # the second look, not the agent
        seen.append(request)
        return message(text("\n".join(f"{n}: {r}" for n, r in enumerate(readings, start=1))))

    return step


def crops_in(request: ModelRequest) -> int:
    return sum(1 for b in request.messages[0]["content"] if b["type"] == "image")


def words_in(request: ModelRequest) -> str:
    return " ".join(b.get("text", "") for b in request.messages[0]["content"]) + " ".join(
        b["text"] for b in request.system
    )


def run_bill(
    readings: list[str],
    boxes: Boxes | None = None,
    file: tuple[Any, bytes] | None = None,
    page: int = 1,
) -> tuple[Bill, list[ModelRequest], RunSaved]:
    f, content = file or (evidence("file-photo", "receipt.png", "image/png"), photo_bytes())
    seen: list[ModelRequest] = []
    model = FakeModel(
        [
            write_bill(f.id, boxes or BOXES, page),
            lambda r: message(text("Done.")),
            second_look_reply(readings, seen),
        ]
    )
    result = run_once(inputs_for({f.id: (f, content)}, f.id), model)
    assert isinstance(result, RunSaved), result
    [bill] = [r.data for r in result.records if isinstance(r.data, Bill)]
    assert isinstance(bill, Bill)
    return bill, seen, result


def match_of(bill: Bill, field: str) -> str | None:
    value = getattr(bill, field)
    if value.citation is None:
        return None
    return value.citation.match.value if value.citation.match else None


def test_values_the_second_look_reads_the_same_are_confirmed():
    bill, seen, _ = run_bill(["45.00 USD $45.00", "Example Taxi Co.", "Mar 3, 2026"])
    assert [match_of(bill, f) for f in ("vendor", "dated", "total")] == ["exact"] * 3
    [look] = seen  # one call for the photo, with all three boxes
    assert crops_in(look) == 3
    sent = words_in(look)
    assert all(v not in sent for v in VALUES.values())  # no hint of the values expected
    assert "45.00" not in sent and "Taxi" not in sent
    box = bill.total.citation.location if bill.total.citation else None
    assert isinstance(box, ImageBox) and abs(box.left - 800 / 1200) < 1e-9


def test_a_value_read_differently_or_unreadable_stays_unconfirmed():
    bill, _, _ = run_bill(["$46.00", "Example Taxi Co.", "UNREADABLE"])
    assert match_of(bill, "vendor") == "exact"
    assert match_of(bill, "dated") == "not_found"
    assert match_of(bill, "total") == "not_found"


def test_a_box_off_the_image_is_unconfirmed_and_an_empty_one_reads_nothing():
    boxes: Boxes = {**BOXES, "total": (1300, 650, 1500, 720), "dated": (100, 150, 100, 200)}
    bill, seen, _ = run_bill(["Example Taxi Co."], boxes=boxes)
    assert bill.total.uncited and bill.total.citation is None  # nothing of the box on the image
    assert bill.dated is not None and bill.dated.uncited  # a box with no area
    assert match_of(bill, "vendor") == "exact"
    [look] = seen
    assert crops_in(look) == 1  # only the box on the image is read

    blank: Boxes = dict(BOXES)  # a box over blank paper: the second look reads nothing there
    bill, _, _ = run_bill(["UNREADABLE", "Example Taxi Co.", "Mar 3, 2026"], boxes=blank)
    assert match_of(bill, "total") == "not_found"


def test_a_box_running_off_the_edge_is_cut_to_the_image():
    boxes: Boxes = {**BOXES, "total": (800, 650, 1300, 720)}
    bill, seen, _ = run_bill(["$45.00", "Example Taxi Co.", "Mar 3, 2026"], boxes=boxes)
    box = bill.total.citation.location if bill.total.citation else None
    assert isinstance(box, ImageBox) and abs(box.left + box.width - 1) < 1e-9
    assert match_of(bill, "total") == "exact"
    assert crops_in(seen[0]) == 3


def test_one_call_per_photo_and_the_calls_are_counted_in_the_log():
    a = evidence("file-photo-a", "a.png", "image/png")
    b = evidence("file-photo-b", "b.png", "image/png")
    seen: list[ModelRequest] = []
    model = FakeModel(
        [
            lambda r: calls(tool("open_file", file_id=b.id)),
            write_bill(a.id, BOXES),
            write_bill(b.id, {"total": BOXES["total"], "vendor": BOXES["vendor"]}),
            lambda r: message(text("Done.")),
            second_look_reply(["$45.00", "Example Taxi Co.", "March 3, 2026"], seen),
            second_look_reply(["$45.00", "Example Taxi Co."], seen),
        ]
    )
    files = {a.id: (a, photo_bytes()), b.id: (b, photo_bytes())}
    result = run_once(inputs_for(files, a.id), model)
    assert isinstance(result, RunSaved), result
    assert [crops_in(r) for r in seen] == [3, 2]  # one call per photo, with all its boxes
    bills = [r.data for r in result.records if isinstance(r.data, Bill)]
    assert all(match_of(x, "total") == "exact" for x in bills)
    log = result.log
    assert log["second_look"]["calls"] == 2
    assert sum(1 for e in log["events"] if e["event"] == "second_look") == 2


def test_a_scanned_pdf_page_goes_as_an_image_and_its_boxes_get_the_second_look():
    scan = evidence("file-scan", "scan.pdf", "application/pdf")
    opened = open_file(scan, scan_pdf())
    assert opened.document is None  # nothing to cite on a scan
    assert opened.images is not None and [i.page for i in opened.images] == [1]
    image = opened.images[0]  # within the model's limits: 2,576 on a side, 1920 x 1920 in all
    assert max(image.width, image.height) <= 2576 and image.width * image.height <= 1920 * 1920
    assert image.width * image.height > 0.99 * 1920 * 1920  # as large as allowed
    assert any(b["type"] == "image" for b in opened.blocks)

    boxes: Boxes = {"total": (1300, 1900, 1600, 2000), "vendor": (200, 100, 900, 200)}
    bill, seen, _ = run_bill(
        ["$45.00", "Example Taxi Co."], boxes=boxes, file=(scan, scan_pdf()), page=1
    )
    assert match_of(bill, "total") == "exact" and match_of(bill, "vendor") == "exact"
    assert crops_in(seen[0]) == 2


def test_a_pdf_keeps_citations_on_its_text_pages_and_sends_only_scanned_pages_as_images():
    mixed = evidence("file-mixed", "mixed.pdf", "application/pdf")
    opened = open_file(mixed, mixed_pdf())
    assert opened.document is not None and opened.document.kind == "pdf"
    assert opened.images is not None and [i.page for i in opened.images] == [2]
    with open(TEXT_PDF, "rb") as f:
        text_only = open_file(mixed, f.read())
    assert text_only.images is None and text_only.document is not None


def test_a_large_photo_is_sent_within_the_pixel_limit():
    big = evidence("file-big", "big.png", "image/png")
    opened = open_file(big, photo_bytes((3000, 4000)))
    assert opened.images is not None
    [image] = opened.images
    assert image.width * image.height <= 1920 * 1920 and max(image.width, image.height) <= 2576
