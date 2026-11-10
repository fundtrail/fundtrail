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
    """One highlight box on a page, as fractions of the page from its top left corner.

    The page is the page as a viewer shows it: its crop box, turned by its own rotation. This
    is the same frame docs/contracts.md uses for an `image_box`.
    """

    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class PdfQuoteMatch:
    """Where a cited passage was found in a PDF, and whether the cited value is in it."""

    match: MatchKind
    method: MatchMethod | None
    """The step that found the passage, or None when it wasn't found."""
    page_number: int | None
    """The page it was found on, counted from 1. None when it wasn't found."""
    rects: tuple[HighlightRect, ...]
    """Where the highlight goes, one box per line of text. Empty when it wasn't found."""
    matched_text: str | None
    """The page's own text for the matched span, after clean-up. None when it wasn't found."""
    value_found: bool | None
    """Whether the value appears exactly in the matched text. None when no value was given."""
