"""The second look on photos and scanned pages, when the run ends (decision 0012, ruling 78).

A value the agent boxed on a photo or a scanned page has no passage to check, so it's staged
unconfirmed. When the run ends, each photo or page with boxed values gets one model call that
sees only the boxed areas, as numbered crops cut from the original at full size, with no hint
of the values expected. A value it reads the same, compared the way the text check compares
(money, dates and numbers by what they're worth, text as written), is confirmed. One read
differently or not at all stays unconfirmed, so whatever rests on it goes to Needs a human.

The calls are counted, with their tokens, in the run's log beside the agent's own.
"""

import io
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from PIL import Image

from app.quotes.page_images import crop_box, render_pdf_page
from app.quotes.second_look import SYSTEM, parse_readings, request_content

from .adapter import EvidenceFile, ImageBox, Record, RecordKind, cited_values
from .context import RunContext, Staged
from .files import MAX_IMAGE_EDGE
from .model import ModelClient, ModelRequest, is_retryable

# Reading a few crops needs little thinking; the agent's own calls use more.
EFFORT = "low"
MAX_TOKENS = 16000
# Pages of a scan are drawn at this long edge for cropping: sharper than the image sent.
RENDER_EDGE = 2 * MAX_IMAGE_EDGE
# Anthropic's vision limits (platform.claude.com/docs/en/build-with-claude/vision, read
# 2026-11-10): at most 100 images in a request (on a model with a 200k-token context; 600
# otherwise), and when a request holds more than 20, none may exceed 3,000 pixels on a side.
# Each crop is shrunk to at most MAX_CROP_EDGE on a side, so one call per page fits however
# many boxes it has; only past MAX_CROPS_PER_CALL does a page take more than one call.
MAX_CROP_EDGE = 2000
MAX_CROPS_PER_CALL = 100


class SecondLookFailed(Exception):
    """The second look's call failed. `retryable` says whether trying the run again could work."""

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class _Boxed:
    staged: int  # the index in ctx.staged
    path: str
    box: ImageBox
    value: Any  # the value as the record holds it, in JSON form
    text: str


def boxed_paths(record: Record) -> list[str]:
    """The values in a record boxed on a photo or scan and still waiting for the second look."""
    return [
        path
        for path, v in cited_values(record.data)
        if v.citation is not None
        and isinstance(v.citation.location, ImageBox)
        and v.citation.match is not None
        and v.citation.match.value == "not_found"
    ]


def run_second_look(ctx: RunContext, model: ModelClient) -> None:
    """Read every boxed value staged in this run: one call per photo or scanned page.

    Updates each staged record in place, confirming the values read the same. A call the API
    rejects (a 400) confirms nothing on its page and the run goes on. Raises SecondLookFailed
    when a call fails in a way trying again could fix, so the run is retried like any other.
    """
    groups: dict[tuple[str, int], list[_Boxed]] = defaultdict(list)
    for index, s in enumerate(ctx.staged):
        dumped = s.record.data.model_dump(mode="json")
        for path in boxed_paths(s.record):
            v = _at(dumped, path)
            box = ImageBox.model_validate(v["citation"]["location"])
            item = _Boxed(index, path, box, v["value"], v.get("text") or "")
            groups[(v["citation"]["file_id"], box.page)].append(item)
    if not groups:
        return
    files = {f.id: f for f in ctx.inputs.files}
    confirmed: dict[int, list[str]] = defaultdict(list)
    for (file_id, page), items in groups.items():
        f = files.get(file_id)
        image = _page_image(ctx, f, page) if f is not None else None
        crops = [
            shrink(crop_box(image, i.box.left, i.box.top, i.box.width, i.box.height))
            if image
            else None
            for i in items
        ]
        sent = [c for c in crops if c is not None]
        readings: list[str | None] = []
        for start in range(0, len(sent), MAX_CROPS_PER_CALL):
            readings += _read(ctx, model, file_id, page, sent[start : start + MAX_CROPS_PER_CALL])
        it = iter(readings)
        results: list[dict[str, Any]] = []
        for item, crop in zip(items, crops, strict=True):
            reading = next(it) if crop is not None else None
            same = reading is not None and reads_the_same(ctx.staged[item.staged], item, reading)
            if same:
                confirmed[item.staged].append(item.path)
            results.append(
                {"path": item.path, "text": item.text, "read": reading, "confirmed": same}
            )
        ctx.log_event(
            "second_look_result", file_id=file_id, page=page, crops=len(sent), results=results
        )
    for index, paths in confirmed.items():
        ctx.staged[index] = _confirm(ctx.staged[index], paths)


def _read(
    ctx: RunContext, model: ModelClient, file_id: str, page: int, crops: list[Image.Image]
) -> list[str | None]:
    request = ModelRequest(
        system=[{"type": "text", "text": SYSTEM}],
        tools=[],
        messages=[{"role": "user", "content": request_content(crops)}],
        max_tokens=MAX_TOKENS,
        effort=EFFORT,
    )
    try:
        message = model(request)
    except Exception as error:  # the SDK's typed errors, and anything unexpected
        if is_retryable(error):
            raise SecondLookFailed(
                f"the second look's call failed: {type(error).__name__}: {error}", True
            ) from error
        # Trying again won't help (a request the API rejects): nothing on this page is
        # confirmed, and the rest of the run stands.
        ctx.log_event(
            "second_look_failed", file_id=file_id, page=page, crops=len(crops), error=str(error)
        )
        return [None] * len(crops)
    ctx.add_usage(message.usage)
    looks = ctx.log.setdefault("second_look", {"calls": 0})
    looks["calls"] += 1
    ctx.log_event("second_look", file_id=file_id, page=page, crops=len(crops), message=message)
    if message.stop_reason == "refusal":
        return [None] * len(crops)  # nothing read: every value stays unconfirmed
    reply = "".join(getattr(b, "text", "") for b in message.content if b.type == "text")
    return parse_readings(reply, len(crops))


def _page_image(ctx: RunContext, f: EvidenceFile, page: int) -> Image.Image | None:
    """The original photo, or the scanned page drawn large, or None when it can't be read."""
    data = ctx.inputs.read_file(f)
    try:
        if f.media_type.lower() == "application/pdf":
            return render_pdf_page(data, page, RENDER_EDGE)
        image = Image.open(io.BytesIO(data))
        image.load()
        return image.convert("RGB")
    except Exception:  # a file that can't be drawn: nothing to read, so nothing is confirmed
        return None


def shrink(crop: Image.Image | None) -> Image.Image | None:
    """The crop at most MAX_CROP_EDGE on a side, so a call with many crops stays within limits."""
    if crop is None or max(crop.size) <= MAX_CROP_EDGE:
        return crop
    scale = MAX_CROP_EDGE / max(crop.size)
    size = (max(1, int(crop.width * scale)), max(1, int(crop.height * scale)))
    return crop.resize(size, Image.Resampling.LANCZOS)


def reads_the_same(staged: Staged, item: _Boxed, reading: str) -> bool:
    """Whether what the second look read is the agent's value: the whole reading, not a part.

    The reading is normalized as the agent's text was, by the field's kind: money to cents,
    a date to the day, a number (a rate or a quantity) to its value. Any other field is text,
    compared as written, ignoring only case and spacing: "4417" isn't "004417". A box that
    holds more than the value ("TOTAL $52.00 FEE $4.50" for "$4.50") doesn't read the same.
    """
    from .tools import DATE_FIELDS, DECIMAL_FIELDS, MONEY_FIELDS, WriteProblem, normalize_value

    leaf = item.path.split(".")[-1].split("[")[0]
    if leaf not in MONEY_FIELDS | DATE_FIELDS | DECIMAL_FIELDS:
        return " ".join(reading.split()).casefold() == " ".join(item.text.split()).casefold()
    record = staged.record
    kind = record.kind.value
    group = getattr(record.data, "applies_to", None)
    percent = record.kind == RecordKind.RATE and group is not None
    try:
        read = normalize_value(item.path, reading, kind, percent)
    except WriteProblem:
        return False  # the reading isn't a value of this kind, or holds more than one
    if leaf in DECIMAL_FIELDS:
        try:
            return Decimal(str(read)) == Decimal(str(item.value))
        except InvalidOperation:
            return False
    return read == item.value  # cents, or the day as YYYY-MM-DD


def _at(data: dict[str, Any], path: str) -> dict[str, Any]:
    from .tools import get_path

    return get_path(data, path)


def _confirm(staged: Staged, paths: list[str]) -> Staged:
    """The staged record with these boxed values marked as matched by the second look."""
    record = staged.record
    dumped = record.model_dump(mode="json")
    for path in paths:
        _at(dumped["data"], path)["citation"]["match"] = "exact"
    return Staged(record=Record.model_validate(dumped), waits=staged.waits)
