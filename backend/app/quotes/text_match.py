"""Text clean-up and matching for cited passages. Pure Python, with no PDF library.

The rules are provisional. The build coordinator set the starting rule (exact after normalizing
whitespace and line-end hyphens, anything looser is close, a value counts only if it appears
exactly), and the main coordinator ruled on the details below. They're pending Alex and the eval.

- **Exact** means equal after cleaning up both texts the same way:
  - runs of whitespace become one space;
  - a hyphen that ends a line is optional, unless it sits between two digits ("10-" then "20"),
    where it's a real hyphen and is kept;
  - curly quotes become straight ones, and two single quotes in a row become one double quote
    (the Government Publishing Office prints a double quote that way);
  - the Unicode hyphens U+2010 and U+2011 become "-", typographic ligatures such as "fi" are
    spelled out, and zero-width characters are dropped;
  - a soft hyphen (U+00AD) is an invisible hyphenation point and may be dropped;
  - en and em dashes are left alone.
- **Close** is anything looser, in two steps tried in order: the letters and digits alone match,
  ignoring case, spaces and punctuation; or they match within CLOSE_MAX_EDIT_RATIO edits. A
  passage needs CLOSE_MIN_CHARS letters and digits before either is tried. A close match still
  confirms a value, so it has to be unable to hide a wrong number. Two guards (`close_span_ok`):
  every run of digits in the passage appears in the matched text, in order, so edits only touch
  letters; and the value itself appears exactly in the matched text.
- **A value is found** only when it appears exactly in the matched text, and not as part of a
  longer number or word: "450.00" isn't found in "$12,450.00".

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

_SOFT_HYPHENS = frozenset({LINE_HYPHEN, "\u00ad", "\ufffe"})
_LINE_BREAKS = frozenset("\r\n\v\f\x85\u2028\u2029")
_ZERO_WIDTH = frozenset({"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"})
_REPLACEMENTS = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u2032": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u201f": '"',
    "\u2033": '"',
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}
_NUMBER_SEPARATORS = frozenset(".,")


@dataclass(frozen=True)
class CleanText:
    """A cleaned-up text and, for each of its characters, the index it came from."""

    text: str
    origin: tuple[int, ...]


def clean(chars: Sequence[str]) -> CleanText:
    """Clean up a text, one source character at a time, keeping where each character came from.

    `chars` is a string or a sequence of one-character strings (one per pdfium character index).
    A hyphen followed by a line break becomes LINE_HYPHEN and the break is dropped, except between
    two digits, where the hyphen stays "-". Other runs of whitespace become one space, and leading
    and trailing whitespace is dropped.
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
        after_digit = len(out) >= 2 and out[-2].isdigit()
        if space_at is not None and out:
            if out[-1] == "-" and space_has_break:
                if not (after_digit and ch.isdigit()):
                    out[-1] = LINE_HYPHEN
            elif out[-1] != LINE_HYPHEN:
                out.append(" ")
                origin.append(space_at)
        space_at = None
        space_has_break = False
        if out and out[-1] == LINE_HYPHEN and after_digit and ch.isdigit():
            out[-1] = "-"

        if ch in _SOFT_HYPHENS:
            if not out or out[-1] != LINE_HYPHEN:
                out.append(LINE_HYPHEN)
                origin.append(i)
            continue
        for piece in _REPLACEMENTS.get(ch, ch):
            if piece == "'" and out and out[-1] == "'" and origin[-1] == i - 1:
                out[-1] = '"'
                continue
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


def find_exact(passage: str, page: CleanText) -> list[tuple[int, int]]:
    """Every place `passage` appears exactly in a cleaned-up page text, as spans of `page.text`."""
    pattern = exact_pattern(passage)
    if pattern is None:
        return []
    return [(m.start(), m.end()) for m in pattern.finditer(page.text) if m.end() > m.start()]


def contains_exactly(value_text: str, text: str) -> bool:
    """Whether a value appears exactly in a cleaned-up text, under the same clean-up.

    The value has to stand on its own: where its first or last character is a letter or digit,
    the text beside it can't be a letter or digit, and a number can't go on through a separator
    (so "450.00" isn't in "$12,450.00", and "$12,450" isn't in "$12,450.00").
    """
    pattern = exact_pattern(value_text)
    if pattern is None:
        return False
    pos = 0
    while (found := pattern.search(text, pos)) is not None:
        if found.end() > found.start() and _stands_alone(text, found.start(), found.end()):
            return True
        pos = found.start() + 1
    return False


def _stands_alone(text: str, start: int, end: int) -> bool:
    first, last = text[start], text[end - 1]
    if first.isalnum() and start > 0:
        before = text[start - 1]
        if before.isalnum():
            return False
        if (
            first.isdigit()
            and before in _NUMBER_SEPARATORS
            and start > 1
            and text[start - 2].isdigit()
        ):
            return False
    if last.isalnum() and end < len(text):
        after = text[end]
        if after.isalnum():
            return False
        if (
            last.isdigit()
            and after in _NUMBER_SEPARATORS
            and end + 1 < len(text)
            and text[end + 1].isdigit()
        ):
            return False
    return True


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


def find_letters_and_digits(passage: str, page: CleanText) -> list[tuple[int, int]]:
    """Every place the passage's letters and digits appear, in order, among the page's.

    Spans of `page.text`, not overlapping. Empty for a passage shorter than CLOSE_MIN_CHARS.
    """
    q = letters_and_digits(clean(passage).text).text
    if len(q) < CLOSE_MIN_CHARS:
        return []
    p = letters_and_digits(page.text)
    spans: list[tuple[int, int]] = []
    at = p.text.find(q)
    while at >= 0:
        spans.append(_widen(page.text, p.origin[at], p.origin[at + len(q) - 1] + 1))
        at = p.text.find(q, at + len(q))
    return spans


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


def close_span_ok(passage: str, value_text: str | None, span_text: str) -> bool:
    """The guards on a close match, so it can't hide a wrong number.

    Every run of digits in the passage appears in the matched text, in order, and the value (when
    there is one) appears exactly in the matched text.
    """
    if not _digits_in_order(clean(passage).text, span_text):
        return False
    return value_text is None or contains_exactly(value_text, span_text)


def _digits_in_order(passage: str, span_text: str) -> bool:
    wanted = re.findall(r"\d+", passage)
    found = iter(re.findall(r"\d+", span_text.replace(LINE_HYPHEN, "")))
    return all(any(run == have for have in found) for run in wanted)


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
