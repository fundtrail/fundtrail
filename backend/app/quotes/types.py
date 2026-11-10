"""Internal result types for finding a quote in a PDF.

These stand in for the contract models (issue #14), which aren't merged yet. They follow the
citation shape in docs/contracts.md ("Cited values"): a citation stores how it matched its file
(exact, close or not found) and, for a PDF, where the highlight goes. Keep them in this one module
so they can be swapped for the contract models without touching the matcher.
"""

from dataclasses import dataclass
from typing import Literal

MatchKind = Literal["exact", "close", "not_found"]
"""How a cited passage matched its file, as docs/contracts.md names the three outcomes."""

MatchMethod = Literal["exact", "letters_and_digits", "edit_distance"]
"""Which step found the passage. Both looser steps count as a close match."""


@dataclass(frozen=True)
class HighlightRect:
    """One highlight box, as fractions of its page from the page's top left corner.

    The page is the page as a viewer shows it: its crop box, turned by its own rotation. This
    is the same frame docs/contracts.md uses for an `image_box`.
    """

    page_number: int
    """Counted from 1."""
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class QuoteOccurrence:
    """One place the passage was found. A passage across a page break has boxes on both pages."""

    rects: tuple[HighlightRect, ...]
    """One box per line of text, in reading order."""
    matched_text: str
    """The page's text for the matched span after clean-up, with line-end hyphens shown as "-".

    Lossy: whitespace is collapsed and the clean-up's other changes are applied, so it's for the
    value check and for reading, not a copy of the file's characters.
    """
    value_found: bool | None
    """Whether the value appears exactly in this occurrence. None when no value was given."""


@dataclass(frozen=True)
class PdfQuoteMatch:
    """Where a cited passage was found in a PDF, and whether the cited value is in it."""

    match: MatchKind
    method: MatchMethod | None
    """The step that found the passage, or None when it wasn't found."""
    occurrences: tuple[QuoteOccurrence, ...]
    """Every place it was found, in page order. Empty when it wasn't found."""
    value_found: bool | None
    """Whether the value appears exactly in a matched occurrence. None when no value was given."""

    @property
    def rects(self) -> tuple[HighlightRect, ...]:
        """Every highlight box, across all occurrences."""
        return tuple(rect for occurrence in self.occurrences for rect in occurrence.rects)

    @property
    def page_number(self) -> int | None:
        """The page of the first box, or None when it wasn't found."""
        rects = self.rects
        return rects[0].page_number if rects else None
