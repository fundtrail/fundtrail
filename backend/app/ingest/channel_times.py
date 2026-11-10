"""Channel times on a sample grant (issue 165, point 4).

On a sample grant everything runs on the grant's simulated time. A time a channel
supplies, such as a live email's `Date` header, would be months or years away from
it, so wherever the app stores or shows such a time it uses the grant's "now"
instead. The stored original (the .eml bytes, a Drive file's bytes) is never changed.

- `sample_sent_date`: the sent date stored on the message's evidence file
  (`document_date`), which the screens, the evidence report and the agent's file
  list show.
- `reading_text`: the text of an email for the agent to read. Of its top-level
  headers it keeps only From, To, Cc and Subject, and Date with its value replaced by
  the grant's "now". Every other header is dropped, because trace headers are channel
  times too: Received and X-Received carry the real delivery time, and ARC-Seal and
  DKIM-Signature carry Unix timestamps (`t=`). The body is the stored file's, character
  for character, and `ReadingText.stored_index` maps a position in the text back to the
  stored file, so a citation into the text still points into the original.

Drive's modified and created times are not stored or shown anywhere: the checker uses
the modified time only to tell versions apart and to wait for a file to stop
changing, which has to stay on real time. So there is nothing to replace for Drive.

Grants on the real date are untouched.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import format_datetime

# The top-level headers kept as they are in the text the agent reads. Date is kept with
# its value replaced; every other header is dropped.
_KEPT_HEADERS = {"from", "to", "cc", "subject"}
# The blank line that ends the headers: the header block runs to the end of its first
# line ending, so each header field includes its own line ending.
_HEADER_END = re.compile(r"\r?\n(?=\r?\n)")
# One line, with its line ending if it has one.
_LINE = re.compile(r"[^\r\n]*(?:\r?\n|$)")


def sample_sent_date(grant_now: datetime) -> date:
    """The sent date a live email takes on a sample grant: the grant's "now", in UTC."""
    return _utc(grant_now).date()


@dataclass(frozen=True)
class ReadingText:
    """An email's text as the agent reads it on a sample grant."""

    text: str
    # Each replaced span: (start, end) in `text`, and (start, end) in the stored text.
    replaced: tuple[tuple[int, int, int, int], ...] = ()

    def stored_index(self, index: int) -> int:
        """The position in the stored text that `index` in `text` stands for.

        A position inside a replaced header maps to the start of the original header, so
        a citation never points into text the stored file doesn't have.
        """
        shift = 0
        for start, end, stored_start, stored_end in self.replaced:
            if index < start:
                break
            if index < end:
                return stored_start
            shift = stored_end - end
        return index + shift


def reading_text(stored: str, grant_now: datetime | None) -> ReadingText:
    """The text the agent reads for an email whose stored text is `stored`.

    With no grant "now" (a grant on the real date) the text is the stored text. On a
    sample grant, the top-level headers are cut down to From, To, Cc and Subject as
    stored, and Date with the grant's "now" (`Date :` with a space is a Date header
    too). Every other header is dropped as a zero-length span. The body, including a
    forwarded message's own headers, is what the sender wrote and stays.
    """
    if grant_now is None:
        return ReadingText(stored)
    end = _HEADER_END.search(stored)
    header_end = end.end() if end else len(stored)
    date_value = format_datetime(_utc(grant_now))
    parts: list[str] = []
    replaced: list[tuple[int, int, int, int]] = []
    out_length = 0
    for start, stop, name, line_end in _fields(stored, header_end):
        if name in _KEPT_HEADERS:
            parts.append(stored[start:stop])
            out_length += stop - start
            continue
        new = f"Date: {date_value}{line_end}" if name == "date" else ""
        replaced.append((out_length, out_length + len(new), start, stop))
        parts.append(new)
        out_length += len(new)
    parts.append(stored[header_end:])
    return ReadingText("".join(parts), tuple(replaced))


def _fields(stored: str, header_end: int) -> list[tuple[int, int, str | None, str]]:
    """Each top-level header field: (start, end, lower-case name or None, line ending).

    A field runs from its first line through its folded continuation lines, and includes
    its last line ending. A line that isn't a header (no colon) is a field named None.
    """
    fields: list[tuple[int, int, str | None, str]] = []
    position = 0
    while position < header_end:
        line = _LINE.match(stored, position, header_end)
        assert line is not None  # _LINE matches the empty string
        if line.end() == position:
            break
        text = line.group()
        if text[:1] in (" ", "\t") and fields:
            first, _, name, _ = fields[-1]
            fields[-1] = (first, line.end(), name, _line_ending(text))
        else:
            head, colon, _ = text.partition(":")
            name = head.strip().lower() if colon and head.strip() else None
            fields.append((position, line.end(), name, _line_ending(text)))
        position = line.end()
    return fields


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    return "\n" if line.endswith("\n") else ""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("a grant's now must be timezone-aware")
    return value.astimezone(UTC)
