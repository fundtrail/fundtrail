"""Channel times on a sample grant (issue 165, point 4).

On a sample grant everything runs on the grant's simulated time. A time a channel
supplies, such as a live email's `Date` header, would be months or years away from
it, so wherever the app stores or shows such a time it uses the grant's "now"
instead. The stored original (the .eml bytes, a Drive file's bytes) is never changed.

- `sample_sent_date`: the sent date stored on the message's evidence file
  (`document_date`), which the screens, the evidence report and the agent's file
  list show.
- `reading_text`: the text of an email for the agent to read, with its top-level
  `Date` header replaced by the grant's "now". Every other character is the stored
  file's, and `ReadingText.stored_index` maps a position in the text back to the
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

# A top-level Date header line, with any folded continuation lines.
_DATE_HEADER = re.compile(r"^Date:[^\r\n]*(?:\r?\n[ \t][^\r\n]*)*", re.IGNORECASE | re.MULTILINE)
_HEADER_END = re.compile(r"\r?\n\r?\n")


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
    sample grant, each top-level `Date` header becomes the grant's "now". Dates inside the
    body, including a forwarded message's own headers, are what the sender wrote and stay.
    """
    if grant_now is None:
        return ReadingText(stored)
    end = _HEADER_END.search(stored)
    header_end = end.start() if end else len(stored)
    new_line = f"Date: {format_datetime(_utc(grant_now))}"
    parts: list[str] = []
    replaced: list[tuple[int, int, int, int]] = []
    last = 0
    out_length = 0
    for match in _DATE_HEADER.finditer(stored, 0, header_end):
        kept = stored[last : match.start()]
        parts.append(kept)
        out_length += len(kept)
        parts.append(new_line)
        replaced.append((out_length, out_length + len(new_line), match.start(), match.end()))
        out_length += len(new_line)
        last = match.end()
    parts.append(stored[last:])
    return ReadingText("".join(parts), tuple(replaced))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("a grant's now must be timezone-aware")
    return value.astimezone(UTC)
