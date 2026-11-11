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
from .citations import value_in
from .context import RunContext, Staged
from .files import MAX_IMAGE_EDGE
from .model import ModelClient, ModelRequest, is_retryable

# Reading a few crops needs little thinking; the agent's own calls use more.
EFFORT = "low"
MAX_TOKENS = 16000
# Pages of a scan are drawn at this long edge for cropping: sharper than the image sent.
RENDER_EDGE = 2 * MAX_IMAGE_EDGE


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

    Updates each staged record in place, confirming the values read the same. Raises
    SecondLookFailed when a call fails, so the run fails like any other model call.
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
            crop_box(image, i.box.left, i.box.top, i.box.width, i.box.height) if image else None
            for i in items
        ]
        sent = [c for c in crops if c is not None]
        readings: list[str | None] = []
        if sent:
            readings = _read(ctx, model, file_id, page, sent)
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
        raise SecondLookFailed(
            f"the second look's call failed: {type(error).__name__}: {error}",
            is_retryable(error),
        ) from error
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


def reads_the_same(staged: Staged, item: _Boxed, reading: str) -> bool:
    """Whether what the second look read is the agent's value.

    The agent's text standing on its own in the reading counts, as in the text check. Otherwise
    the reading is normalized as the agent's text was (money in cents, dates, numbers) and
    compared by value; text is compared ignoring case and spacing.
    """
    from .tools import WriteProblem, normalize_value

    if value_in(item.text, reading):
        return True
    record = staged.record
    kind = record.kind.value
    group = getattr(record.data, "applies_to", None)
    percent = record.kind == RecordKind.RATE and group is not None
    try:
        read = normalize_value(item.path, reading, kind, percent)
    except WriteProblem:
        return False
    if isinstance(read, int) and not isinstance(read, bool):
        return read == item.value
    if isinstance(item.value, str) and isinstance(read, str):
        try:
            return Decimal(read) == Decimal(item.value)
        except InvalidOperation:
            pass
        return " ".join(read.split()).casefold() == " ".join(item.value.split()).casefold()
    return False


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
