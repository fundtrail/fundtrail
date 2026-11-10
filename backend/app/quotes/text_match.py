"""Text clean-up and matching for cited passages. Pure Python, with no PDF library.

The matching rule is provisional (set by the build coordinator, pending Alex):

- **Exact** means equal after cleaning up both texts the same way: runs of whitespace become one
  space, curly quotes become straight ones, the Unicode hyphen characters become "-", typographic
  ligatures such as "fi" are spelled out, invisible zero-width characters are dropped, and a
  hyphen that ends a line is optional. Dashes (en and em) are left alone.
- **Close** is anything looser. Two steps, tried in order: the letters and digits alone match,
  ignoring case, spaces and punctuation; or they match within a small number of edits.
- A value counts as found only when it appears exactly (same clean-up) in the matched text.

Every cleaned-up text keeps a map from each of its characters back to the character it came
from, so a match can be turned back into a span of the original page text.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

LINE_HYPHEN = "\x02"
"""Stands for a hyphen at the end of a line. pdfium itself reports such a hyphen as U+0002."""

CLOSE_MIN_CHARS = 12
"""A passage needs at least this many letters and digits before a close match is tried.

A short passage like "$40.00" loosely matches too many places on a page. Provisional.
"""

CLOSE_MAX_EDIT_RATIO = 0.1
"""The most edits a close match may need, as a share of the passage's letters and digits.

Provisional, pending the eval.
"""

_SOFT_HYPHENS = frozenset({LINE_HYPHEN, "­", "￾"})
_LINE_BREAKS = frozenset("\r\n\v\f\x85  ")
_ZERO_WIDTH = frozenset({"​", "‌", "‍", "⁠", "﻿"})
_REPLACEMENTS = {
    "‐": "-",
    "‑": "-",
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "′": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "‟": '"',
    "″": '"',
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}


@dataclass(frozen=True)
class CleanText:
    """A cleaned-up text and, for each of its characters, the index it came from."""

    text: str
    origin: tuple[int, ...]


def clean(chars: Sequence[str]) -> CleanText:
    """Clean up a text, one source character at a time, keeping where each character came from.

    `chars` is a string or a sequence of one-character strings (one per pdfium character index).
    A hyphen followed by a line break becomes LINE_HYPHEN and the break is dropped. Other runs of
    whitespace become one space, and leading and trailing whitespace is dropped.
    """
    out: list[str] = []
    origin: list[int] = []
    space_at: int | None = None
    space_has_break = False

    for i, ch in enumerate(chars):
        if ch in _ZERO_WIDTH:
            continue
        if ch.isspace():
            if space_at is None:
                space_at = i
            space_has_break = space_has_break or ch in _LINE_BREAKS
            continue
        if space_at is not None and out:
            if out[-1] == "-" and space_has_break:
                out[-1] = LINE_HYPHEN
            elif out[-1] != LINE_HYPHEN:
                out.append(" ")
                origin.append(space_at)
        space_at = None
        space_has_break = False

        if ch in _SOFT_HYPHENS:
            if not out or out[-1] != LINE_HYPHEN:
                out.append(LINE_HYPHEN)
                origin.append(i)
            continue
        for piece in _REPLACEMENTS.get(ch, ch):
            out.append(piece)
            origin.append(i)

    return CleanText("".join(out), tuple(origin))


def exact_pattern(passage: str) -> re.Pattern[str] | None:
    """Build the pattern that finds `passage` exactly in a cleaned-up page text.

    A hyphen that ends a line on the page may be missing from the passage ("recently" for
    "re-" then "cently"), kept ("cost-sharing"), or kept with a space where the line broke
    ("re- cently"). Returns None for a passage that is empty after clean-up.
    """
    q = clean(passage).text
    if not q:
        return None
    hy = re.escape(LINE_HYPHEN)
    parts: list[str] = []
    i = 0
    while i < len(q):
        ch = q[i]
        if i > 0 and _plain(q[i - 1]) and _plain(ch):
            parts.append(f"{hy}?")
        if ch == LINE_HYPHEN:
            parts.append(f"(?:{hy}|-)?")
        elif ch == "-" and i + 1 < len(q) and q[i + 1] == " ":
            parts.append(f"(?:- |{hy})")
            i += 1
        elif ch == "-":
            parts.append(f"(?:-|{hy})")
        else:
            parts.append(re.escape(ch))
        i += 1
    return re.compile("".join(parts))


def _plain(ch: str) -> bool:
    return ch not in (" ", "-", LINE_HYPHEN)


def find_exact(passage: str, page: CleanText) -> tuple[int, int] | None:
    """Find `passage` exactly in a cleaned-up page text. Returns the span in `page.text`."""
    pattern = exact_pattern(passage)
    if pattern is None:
        return None
    found = pattern.search(page.text)
    if found is None or found.end() == found.start():
        return None
    return found.start(), found.end()


def contains_exactly(value_text: str, text: str) -> bool:
    """Whether a value appears exactly in a cleaned-up text, under the same clean-up."""
    pattern = exact_pattern(value_text)
    return pattern is not None and pattern.search(text) is not None


def letters_and_digits(text: str) -> CleanText:
    """Keep only letters and digits, case-folded, mapping each back to its index in `text`."""
    out: list[str] = []
    origin: list[int] = []
    for i, ch in enumerate(text):
        if ch.isalnum():
            for piece in ch.casefold():
                out.append(piece)
                origin.append(i)
    return CleanText("".join(out), tuple(origin))


def find_letters_and_digits(passage: str, page: CleanText) -> tuple[int, int] | None:
    """Find the passage's letters and digits, in order, among the page's. Span in `page.text`."""
    q = letters_and_digits(clean(passage).text).text
    if len(q) < CLOSE_MIN_CHARS:
        return None
    p = letters_and_digits(page.text)
    at = p.text.find(q)
    if at < 0:
        return None
    return _widen(page.text, p.origin[at], p.origin[at + len(q) - 1] + 1)


def find_within_edits(passage: str, page: CleanText) -> tuple[tuple[int, int], int] | None:
    """Find the passage's letters and digits among the page's, allowing a few edits.

    Returns the span in `page.text` and the number of edits, or None when the best match needs
    more than CLOSE_MAX_EDIT_RATIO of the passage's length.
    """
    q = letters_and_digits(clean(passage).text).text
    if len(q) < CLOSE_MIN_CHARS:
        return None
    p = letters_and_digits(page.text)
    if not p.text:
        return None
    best = best_substring_match(q, p.text)
    if best is None:
        return None
    start, end, edits = best
    if edits > int(len(q) * CLOSE_MAX_EDIT_RATIO):
        return None
    return _widen(page.text, p.origin[start], p.origin[end - 1] + 1), edits


def _widen(text: str, start: int, end: int) -> tuple[int, int]:
    """Stretch a span over the punctuation touching it, such as a "$" or a closing period.

    A close match is found on letters and digits only, so without this the value "$40" would
    fall outside the span that matched "40".
    """
    while start > 0 and text[start - 1] != " " and not text[start - 1].isalnum():
        start -= 1
    while end < len(text) and text[end] != " " and not text[end].isalnum():
        end += 1
    return start, end


def best_substring_match(pattern: str, text: str) -> tuple[int, int, int] | None:
    """Find the substring of `text` closest to `pattern` by edit distance.

    Uses Myers' bit-parallel algorithm (Hyyrö's formulation for searching), so it runs in time
    proportional to the text's length for any passage length. Returns (start, end, edits), with
    the leftmost best end, or None for an empty pattern.
    """
    if not pattern:
        return None
    scores = _end_scores(pattern, text)
    edits = min(scores)
    end = scores.index(edits) + 1
    # Search backwards from that end for where the alignment starts.
    back = _end_scores(pattern[::-1], text[:end][::-1])
    reach = back.index(min(back)) + 1
    return end - reach, end, edits


def _end_scores(pattern: str, text: str) -> list[int]:
    """For each end position in `text`, the fewest edits to match `pattern` ending there."""
    m = len(pattern)
    full = (1 << m) - 1
    top = 1 << (m - 1)
    peq: dict[str, int] = {}
    for i, ch in enumerate(pattern):
        peq[ch] = peq.get(ch, 0) | (1 << i)
    pv, mv, score = full, 0, m
    scores: list[int] = []
    for ch in text:
        eq = peq.get(ch, 0)
        xv = eq | mv
        xh = ((((eq & pv) + pv) & full) ^ pv) | eq
        ph = (mv | ~(xh | pv)) & full
        mh = pv & xh
        if ph & top:
            score += 1
        elif mh & top:
            score -= 1
        ph = (ph << 1) & full
        mh = (mh << 1) & full
        pv = (mh | ~(xv | ph)) & full
        mv = ph & xv
        scores.append(score)
    if not scores:
        scores.append(m)
    return scores
