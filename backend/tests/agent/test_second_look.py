"""The second look on photos and scanned pages (decision 0012, ruling 78). No real model.

The agent boxes each value on the image we sent. When the run ends, each photo or scanned page
gets one call that sees only the boxed areas, as numbered crops with no hint of the values. A
value read the same, as a whole and by its field's kind, is confirmed; read differently,
unreadable, or boxed off the image, it stays unconfirmed. A PDF page with no text layer goes as
an image, so its values can be boxed.
"""

import base64
import io
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Any

import anthropic
import httpx
import pypdfium2 as pdfium
import pytest
from anthropic.types import Message
from PIL import Image

from app.agent import RunFailed, RunSaved, run_once
from app.agent import second_look as second_look_module
from app.agent.context import RunContext
from app.agent.files import open_file
from app.agent.model import ModelRequest
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import Bill, ImageBox, Rate
from app.contracts.runs import Trigger, TriggerKind
from app.quotes.page_images import crop_box
from app.quotes.pdf import PDFIUM_LOCK

from .fakes import FakeModel, calls, message, results_of, sample_inputs, text, tool

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
VALUES = {
    "vendor": "Example Taxi Co.",
    "dated": "March 3, 2026",
    "total": "$45.00",
    "document_number": "004417",
}
NORMALIZED: dict[str, Any] = {"dated": "2026-03-03", "total": 4500}
# The order the crops come in: the record's field order, a bill's total, vendor, then date.
ORDER = ["total", "vendor", "dated", "document_number"]


def gradient(size: tuple[int, int]) -> Image.Image:
    """A photo in which every pixel says where it is, so a crop can be checked to the pixel."""
    w, h = size
    data = bytes(
        v
        for y in range(h)
        for x in range(w)
        for v in (x % 256, y % 256, (x // 256 + 16 * (y // 256)) % 256)
    )
    return Image.frombytes("RGB", size, data)


def photo_bytes(size: tuple[int, int] = (1200, 800)) -> bytes:
    out = io.BytesIO()
    gradient(size).save(out, format="PNG")
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


def boxed(field: str, file_id: str, box: PixelBox, page: int = 1, said: str | None = None):
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
        "text": said or VALUES[field],
    }
    if field in NORMALIZED:
        out["value"] = NORMALIZED[field]
    return out


def write_bill(file_id: str, boxes: Boxes, page: int = 1):
    values = [boxed(f, file_id, b, page) for f, b in boxes.items()]
    return lambda r: calls(tool("write_fact", kind="bill", values=values))


def second_look_reply(readings: list[str], seen: list[ModelRequest]) -> Callable[..., Message]:
    """The fake second look: replies with `readings`, one per crop in the record's field order."""

    def step(request: ModelRequest) -> Message:
        assert request.tools == []  # the second look, not the agent
        seen.append(request)
        return message(text("\n".join(f"{n}: {r}" for n, r in enumerate(readings, start=1))))

    return step


def images_in(request: ModelRequest) -> list[Image.Image]:
    return [
        Image.open(io.BytesIO(base64.b64decode(b["source"]["data"])))
        for b in request.messages[0]["content"]
        if b["type"] == "image"
    ]


def crops_in(request: ModelRequest) -> int:
    return len(images_in(request))


def words_in(request: ModelRequest) -> str:
    return " ".join(b.get("text", "") for b in request.messages[0]["content"]) + " ".join(
        b["text"] for b in request.system
    )


def run_bill(
    readings: list[str],
    boxes: Boxes | None = None,
    file: tuple[Any, bytes] | None = None,
    page: int = 1,
    look: Callable[..., Message] | None = None,
) -> tuple[Bill, list[ModelRequest], RunSaved]:
    f, content = file or (evidence("file-photo", "receipt.png", "image/png"), photo_bytes())
    seen: list[ModelRequest] = []
    model = FakeModel(
        [
            write_bill(f.id, boxes or BOXES, page),
            lambda r: message(text("Done.")),
            look or second_look_reply(readings, seen),
        ]
    )
    result = run_once(inputs_for({f.id: (f, content)}, f.id), model)
    assert isinstance(result, RunSaved), result
    [bill] = [r.data for r in result.records if isinstance(r.data, Bill)]
    assert isinstance(bill, Bill)
    return bill, seen, result


def match_of(record: Any, field: str) -> str | None:
    value = getattr(record, field)
    if value.citation is None:
        return None
    return value.citation.match.value if value.citation.match else None


def test_values_the_second_look_reads_the_same_are_confirmed():
    bill, seen, _ = run_bill(["$45.00", "Example Taxi Co.", "Mar 3, 2026"])
    assert [match_of(bill, f) for f in ("vendor", "dated", "total")] == ["exact"] * 3
    [look] = seen  # one call for the photo, with all three boxes
    assert crops_in(look) == 3
    box = bill.total.citation.location if bill.total.citation else None
    assert isinstance(box, ImageBox) and abs(box.left - 800 / 1200) < 1e-9


def test_the_call_holds_only_the_crops_cut_from_the_boxes_and_no_hint_of_the_values():
    """Each image sent is exactly its box's crop of the original, and nothing else is sent: no
    page, no field names, no values."""
    original = gradient((1200, 800))
    bill, seen, _ = run_bill(["$45.00", "Example Taxi Co.", "Mar 3, 2026"])
    [look] = seen
    sent = images_in(look)
    expected = []
    for field in ("total", "vendor", "dated"):
        c = getattr(bill, field).citation
        assert c is not None and isinstance(c.location, ImageBox)
        b = c.location
        expected.append(crop_box(original, b.left, b.top, b.width, b.height))
    assert [i.size for i in sent] == [e.size for e in expected if e is not None]
    for got, want in zip(sent, expected, strict=True):
        assert want is not None and got.convert("RGB").tobytes() == want.tobytes()
        assert got.width < 1200 and got.height < 800  # never the whole photo
    words = words_in(look).casefold()
    for hint in [*VALUES.values(), *ORDER, "45", "taxi", "march", "vendor", "amount", "bill"]:
        assert hint.casefold() not in words, hint


def test_a_value_read_differently_or_unreadable_stays_unconfirmed():
    bill, _, _ = run_bill(["$46.00", "Example Taxi Co.", "UNREADABLE"])
    assert match_of(bill, "vendor") == "exact"
    assert match_of(bill, "dated") == "not_found"
    assert match_of(bill, "total") == "not_found"


def test_a_reading_that_holds_more_than_the_value_isnt_confirmed():
    """A box over more than the value: "$45.00" isn't confirmed by "$52.00 FEE $45.00"."""
    bill, _, _ = run_bill(["TOTAL $52.00 FEE $45.00", "Example Taxi Co. Denver", "Mar 3, 2026"])
    assert match_of(bill, "total") == "not_found"
    assert match_of(bill, "vendor") == "not_found"
    assert match_of(bill, "dated") == "exact"


def test_text_is_compared_as_written_ignoring_only_case_and_spacing():
    boxes: Boxes = {**BOXES, "document_number": (600, 50, 800, 110)}
    readings = ["$45.00", "EXAMPLE  TAXI CO.", "March 3, 2026", "4417"]
    bill, _, _ = run_bill(readings, boxes=boxes)
    assert match_of(bill, "vendor") == "exact"  # case and spacing
    assert match_of(bill, "document_number") == "not_found"  # "4417" isn't "004417"
    bill, _, _ = run_bill(["$45.00", "Example Taxi Co.", "March 3, 2026", "004417"], boxes=boxes)
    assert match_of(bill, "document_number") == "exact"


def test_a_leading_colon_from_the_label_is_dropped_and_nothing_else():
    """A crop's margin can take in the label's colon: ": March 3, 2026" reads the same as the
    date, ": 004417" as the number, ": Example Taxi Co." as the vendor. Only the colon and the
    spaces around it go; a minus sign stays, so ": -$45.00" isn't $45.00."""
    boxes: Boxes = {**BOXES, "document_number": (600, 50, 800, 110)}
    readings = [":$45.00", " : Example Taxi Co.", ": March 3, 2026", ":  004417"]
    bill, _, _ = run_bill(readings, boxes=boxes)
    fields = ("total", "vendor", "dated", "document_number")
    assert [match_of(bill, f) for f in fields] == ["exact"] * 4
    bill, _, _ = run_bill(
        [": -$45.00", ":: Example Taxi Co.", "March 3, 2026:", "(004417)"], boxes=boxes
    )
    assert [match_of(bill, f) for f in fields] == [
        "not_found",
        "not_found",
        "not_found",
        "not_found",
    ]


def test_only_a_leading_colon_is_dropped_from_a_reading():
    drop = second_look_module.without_label_colon
    assert drop(": March 12, 2024") == "March 12, 2024"
    assert drop(": INV-12655") == "INV-12655"
    assert (
        drop(": SYN-2401835, salt marsh carbon burial") == "SYN-2401835, salt marsh carbon burial"
    )
    for kept in ("-12.00", "$12.00", "(12.00)", "12.00:", "INV-12655"):
        assert drop(kept) == kept
    assert drop(": -12.00") == "-12.00"


def test_a_number_field_is_compared_by_value():
    """A rate term's rate is a number: "15%" reads the same as "15.00%"; its name is text."""
    f = evidence("file-rates", "rates.png", "image/png")
    values: list[dict[str, Any]] = [
        {"field": "dated", "text": "July 1, 2025", "value": "2025-07-01"},
        {"field": "name", "text": "Staff"},
        {"field": "rate", "text": "15.00%", "value": "0.15"},
    ]
    pixel_boxes = [(100, 50, 400, 100), (100, 150, 300, 200), (500, 150, 700, 200)]
    for v, (left, top, right, bottom) in zip(values, pixel_boxes, strict=True):
        v["box"] = {"file_id": f.id, "left": left, "top": top, "right": right, "bottom": bottom}
    seen: list[ModelRequest] = []
    model = FakeModel(
        [
            lambda r: calls(tool("write_term", kind="rate", values=values)),
            lambda r: message(text("Done.")),
            second_look_reply(["7/1/2025", "STAFF", "15%"], seen),
        ]
    )
    result = run_once(inputs_for({f.id: (f, photo_bytes())}, f.id), model)
    assert isinstance(result, RunSaved), result
    [rate] = [r.data for r in result.records if isinstance(r.data, Rate)]
    assert [match_of(rate, x) for x in ("dated", "name", "rate")] == ["exact"] * 3


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


def test_a_box_running_off_the_edge_is_cut_to_the_image_and_the_agent_is_told():
    boxes: Boxes = {**BOXES, "total": (800, 650, 1300, 720)}
    seen: list[ModelRequest] = []
    f = evidence("file-photo", "receipt.png", "image/png")
    model = FakeModel(
        [
            write_bill(f.id, boxes),
            lambda r: message(text("Done.")),
            second_look_reply(["$45.00", "Example Taxi Co.", "Mar 3, 2026"], seen),
        ]
    )
    result = run_once(inputs_for({f.id: (f, photo_bytes())}, f.id), model)
    assert isinstance(result, RunSaved), result
    told = str(results_of(model.requests[1])[0]["content"])
    assert "The box for total ran off the 1200 by 800 image and was cut to it" in told
    [bill] = [r.data for r in result.records if isinstance(r.data, Bill)]
    box = bill.total.citation.location if bill.total.citation else None
    assert isinstance(box, ImageBox) and abs(box.left + box.width - 1) < 1e-9
    assert match_of(bill, "total") == "exact"
    assert crops_in(seen[0]) == 3


def test_a_box_over_much_of_the_image_is_refused():
    """A box around the whole receipt would hold every amount on it: the agent boxes the value."""
    f = evidence("file-photo", "receipt.png", "image/png")
    inputs = inputs_for({f.id: (f, photo_bytes())}, f.id)
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook())
    run_tool(ctx, "open_file", {"file_id": f.id})
    whole = boxed("total", f.id, (0, 0, 1200, 800))
    result, error = run_tool(ctx, "write_fact", {"kind": "bill", "values": [whole]})
    assert error and "covers 100% of the image" in result and "Box the value itself" in result
    assert not ctx.staged


def test_a_refusal_or_a_rejected_call_confirms_nothing_and_the_run_stands():
    refused = message(text(""), stop="refusal")
    bill, _, result = run_bill([], look=lambda r: refused)
    assert [match_of(bill, f) for f in ("vendor", "dated", "total")] == ["not_found"] * 3

    def rejected(request: ModelRequest) -> Message:
        raise ValueError("400: the request was rejected")

    bill, _, result = run_bill([], look=rejected)
    assert [match_of(bill, f) for f in ("vendor", "dated", "total")] == ["not_found"] * 3
    assert any(e["event"] == "second_look_failed" for e in result.log["events"])


def test_a_call_that_could_work_later_fails_the_run_to_be_tried_again():
    def down(request: ModelRequest) -> Message:
        sent = httpx.Request("POST", "http://127.0.0.1")
        raise anthropic.APIConnectionError(request=sent)  # pyright: ignore[reportArgumentType]

    f = evidence("file-photo", "receipt.png", "image/png")
    model = FakeModel([write_bill(f.id, BOXES), lambda r: message(text("Done.")), down])
    result = run_once(inputs_for({f.id: (f, photo_bytes())}, f.id), model)
    assert isinstance(result, RunFailed) and result.retryable


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


def test_a_page_with_more_crops_than_one_call_holds_is_split(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(second_look_module, "MAX_CROPS_PER_CALL", 2)
    seen: list[ModelRequest] = []
    f = evidence("file-photo", "receipt.png", "image/png")
    model = FakeModel(
        [
            write_bill(f.id, BOXES),
            lambda r: message(text("Done.")),
            second_look_reply(["$45.00", "Example Taxi Co."], seen),
            second_look_reply(["Mar 3, 2026"], seen),
        ]
    )
    result = run_once(inputs_for({f.id: (f, photo_bytes())}, f.id), model)
    assert isinstance(result, RunSaved), result
    assert [crops_in(r) for r in seen] == [2, 1]
    [bill] = [r.data for r in result.records if isinstance(r.data, Bill)]
    assert [match_of(bill, x) for x in ("total", "vendor", "dated")] == ["exact"] * 3


def test_a_crop_is_never_larger_than_a_many_image_call_allows():
    """A wide box on a large photo crops wider than 2,000 pixels at full size: it's shrunk."""
    size = (6000, 4000)
    f = evidence("file-big", "big.png", "image/png")
    sent = open_file(f, photo_bytes(size)).images
    assert sent is not None
    w, h = sent[0].width, sent[0].height
    wide: Boxes = {"total": (0.1 * w, 0.5 * h, 0.7 * w, 0.55 * h)}
    bill, seen, _ = run_bill(["$45.00"], boxes=wide, file=(f, photo_bytes(size)))
    [crop] = images_in(seen[0])
    assert max(crop.size) <= 2000
    assert match_of(bill, "total") == "exact"


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
