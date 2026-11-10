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
  - a soft hyphen (U+00AD) is an invisible hyphenation point and may be dropped, also between
    digits;
  - en and em dashes are left alone.
- **Any match** has to stand on its own on the page: a span whose first or last letter or digit
  continues a word or number there ("450.00 was paid" cut out of "$12,450.00 was paid") isn't a
  match (`span_stands_alone`).
- **Close** is anything looser, in two steps tried in order: the letters and digits alone match,
  ignoring case, spaces and punctuation; or they match within CLOSE_MAX_EDIT_RATIO edits, at every
  place on the page. A passage needs CLOSE_MIN_CHARS letters and digits before either is tried. A
  close match still confirms a value, so it has to be unable to hide a wrong number. Two guards
  (`close_span_ok`): the matched text's numbers are exactly the passage's, the same runs of
  digits in the same order with none added or dropped (edits only touch letters), where any
  numeric character counts (fractions, superscripts) and a minus sign or accounting parentheses
  belong to the number; and the value appears exactly in the matched text. A space that splits a
  number ("12 345" for "12345") therefore makes a different number. A changed separator ("$12.450"
  for "$12,450") passes the first guard, so with no value given it's close.
- **A value is found** only when it appears exactly in the matched text and stands on its own on
  the whole page: not part of a longer number or word ("450.00" isn't in "$12,450.00"), and
  without a minus sign or accounting parentheses the value lacks ("$450.00" isn't in "-$450.00").
  A minus is a hyphen, an en dash or U+2212, before the number (also with a space between) or
  after it ("$450.00-"); see `_sign_of`. On the safe side, prose parentheses count too ("The
  airfare ($450.00)" doesn't confirm "$450.00"), and a line-end hyphen between two letters or
  digits isn't a word edge ("Smith" isn't found in "Smith-" then "son").

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
_SIGNS = frozenset("-\u2013\u2212")
"""Read as a minus next to a number: hyphen, en dash, minus sign. Not the em dash."""
_CURRENCY = frozenset("$\u20ac\u00a3\u00a5")


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
    soft_at = -1  # where in `out` the last LINE_HYPHEN from a soft hyphen (U+00AD) sits

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
            if soft_at == len(out) - 1:
                # A soft hyphen is only a place a word may break, so between digits it goes.
                out.pop()
                origin.pop()
            else:
                out[-1] = "-"

        if ch in _SOFT_HYPHENS:
            if not out or out[-1] != LINE_HYPHEN:
                out.append(LINE_HYPHEN)
                origin.append(i)
                if ch == "\u00ad":
                    soft_at = len(out) - 1
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
    """Whether a value appears exactly in a cleaned-up text, standing on its own."""
    return value_in_span(value_text, text, 0, len(text))


def value_in_span(value_text: str, text: str, start: int, end: int) -> bool:
    """Whether a value appears exactly inside text[start:end], standing on its own in `text`.

    `text` is the whole cleaned-up page, so the value's neighbours are checked on the page, not
    just inside the span: a value at the edge of a span can't be part of a longer number there.
    Standing on its own means: where its first or last character is a letter or digit, the text
    beside it isn't a letter or digit, and a number doesn't go on through a separator ("450.00"
    isn't in "$12,450.00", "$12,450" isn't either). A number doesn't carry a minus sign or
    accounting parentheses on the page that the value lacks ("$450.00" isn't in "-$450.00").
    """
    pattern = exact_pattern(value_text)
    if pattern is None:
        return False
    pos = start
    while (found := pattern.search(text, pos)) is not None and found.start() < end:
        s, e = found.start(), found.end()
        if s < e <= end and _stands_alone(text, s, e) and not _signed(text, s, e):
            return True
        pos = s + 1
    return False


def span_stands_alone(text: str, start: int, end: int) -> bool:
    """Whether a matched span's first and last letter or digit don't continue a word or number.

    A passage cut out of the middle of "$12,450.00" ("450.00 was paid") isn't a match.
    """
    alnum = [i for i in range(start, end) if text[i].isalnum()]
    return not alnum or _stands_alone(text, alnum[0], alnum[-1] + 1)


def _stands_alone(text: str, start: int, end: int) -> bool:
    """Whether text[start:end] doesn't continue a word or number on either side.

    A line-end hyphen between two letters or digits isn't an edge, on the safe side: it may be a
    hyphen that only broke the word ("Smith-" then "son" may be "Smithson"), so "Smith" isn't
    found there.
    """
    first, last = text[start], text[end - 1]
    if first.isalnum() and start > 1 and text[start - 1] == LINE_HYPHEN:
        if text[start - 2].isalnum():
            return False
    if last.isalnum() and end + 1 < len(text) and text[end] == LINE_HYPHEN:
        if text[end + 1].isalnum():
            return False
    if first.isalnum() and start > 0:
        before = text[start - 1]
        if before.isalnum():
            return False
        if (
            first.isnumeric()
            and before in _NUMBER_SEPARATORS
            and start > 1
            and text[start - 2].isnumeric()
        ):
            return False
    if last.isalnum() and end < len(text):
        after = text[end]
        if after.isalnum():
            return False
        if (
            last.isnumeric()
            and after in _NUMBER_SEPARATORS
            and end + 1 < len(text)
            and text[end + 1].isnumeric()
        ):
            return False
    return True


def _signed(text: str, start: int, end: int) -> bool:
    """Whether the number in text[start:end] has a minus sign or parentheses outside it."""
    return _sign_of(text, start, end) != ""


def _sign_of(text: str, start: int, end: int) -> str:
    """The sign the page puts on the number in text[start:end]: "-", "(" or "" for none.

    A minus is a hyphen, an en dash or the minus sign U+2212, and it counts:
    - before the number, with currency symbols and one space allowed between ("-$450.00",
      "\u2013$450.00", "- $450.00"), unless a letter or digit sits right before it, where it's
      a hyphen ("10-20", "SYN-2026");
    - after the number, as some ledger reports print it ("$450.00-"), unless a letter or digit
      follows, where it's a hyphen.
    Parentheses around the number, outside any currency symbol, count as accounting parentheses
    ("($450.00)"), also in prose, on the safe side: "The airfare ($450.00) was booked" doesn't
    confirm "$450.00". A dash with spaces on both sides ("10 - 20") reads as a minus too, so a
    range written that way doesn't confirm its second number.
    """
    if not any(ch.isnumeric() for ch in text[start:end]):
        return ""
    k = start
    while k > 0 and text[k - 1] in _CURRENCY:
        k -= 1
    m = k - 1 if k > 0 and text[k - 1] == " " else k
    if m > 0 and text[m - 1] in _SIGNS and (m < 2 or not text[m - 2].isalnum()):
        return "-"
    if end < len(text) and text[end] in _SIGNS:
        if end + 1 == len(text) or not text[end + 1].isalnum():
            return "-"
    if k > 0 and text[k - 1] == "(" and end < len(text) and text[end] == ")":
        return "("
    return ""


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


def find_within_edits(passage: str, page: CleanText) -> list[tuple[tuple[int, int], int]]:
    """Every place the passage's letters and digits appear among the page's within a few edits.

    Returns each span in `page.text` with its number of edits, not overlapping, in page order.
    Each is the best alignment in its stretch of the page, and none needs more than
    CLOSE_MAX_EDIT_RATIO of the passage's length. Empty for a passage shorter than
    CLOSE_MIN_CHARS.
    """
    q = letters_and_digits(clean(passage).text).text
    if len(q) < CLOSE_MIN_CHARS:
        return []
    p = letters_and_digits(page.text)
    if not p.text:
        return []
    limit = int(len(q) * CLOSE_MAX_EDIT_RATIO)
    scores = _end_scores(q, p.text)
    found: list[tuple[tuple[int, int], int]] = []
    last_end = 0
    j = 0
    while j < len(scores):
        if scores[j] > limit:
            j += 1
            continue
        # A run of end positions within the limit is one place; take its best end.
        best = j
        while j < len(scores) and scores[j] <= limit:
            if scores[j] < scores[best]:
                best = j
            j += 1
        end = best + 1
        start = end - _best_reach(q, p.text[:end])
        if start < last_end:
            continue
        span = _to_word_edges(page.text, p.origin[start], p.origin[end - 1] + 1)
        found.append((_widen(page.text, *span), scores[best]))
        last_end = end
    return found


def close_span_ok(passage: str, value_text: str | None, text: str, start: int, end: int) -> bool:
    """The guards on a close match at text[start:end], so it can't hide a wrong number.

    The numbers in the matched text are the passage's numbers, the same runs of digits in the
    same order with nothing added or dropped (edits only touch letters), each with the same
    minus sign or accounting parentheses; and the value (when there is one) appears exactly in
    the matched text, standing on its own on the page.
    """
    q = clean(passage).text
    if _number_tokens(q, 0, len(q)) != _number_tokens(text, start, end):
        return False
    return value_text is None or value_in_span(value_text, text, start, end)


def _number_tokens(text: str, start: int, end: int) -> list[str]:
    """The runs of numeric characters in text[start:end], each marked with its sign.

    Numeric means any character Unicode counts as a number, so fractions and superscripts
    ("4\u00bd", "10\u00b2") count. A run that starts a number carries "-" when a minus sign
    belongs to it, or "(" for accounting parentheses. Separators split runs but aren't kept, so
    "$12,450" and "$12.450" give the same runs.
    """
    tokens: list[str] = []
    i = start
    while i < end:
        if not text[i].isnumeric():
            i += 1
            continue
        j = i
        while j < end and text[j].isnumeric():
            j += 1
        continues = i >= 2 and text[i - 1] in _NUMBER_SEPARATORS and text[i - 2].isnumeric()
        number_end = j
        while (
            number_end + 1 < len(text)
            and text[number_end] in _NUMBER_SEPARATORS
            and text[number_end + 1].isnumeric()
        ):
            number_end += 2
            while number_end < len(text) and text[number_end].isnumeric():
                number_end += 1
        sign = "" if continues else _sign_of(text, i, number_end)
        tokens.append(sign + text[i:j])
        i = j
    return tokens


def _to_word_edges(text: str, start: int, end: int) -> tuple[int, int]:
    """Stretch an edit-distance span over letters to the edges of the words it cuts.

    The cheapest alignment of a misread "staf" stops inside "staff"; edits only touch letters, so
    the span may take the rest of the word. Never over digits: a span that cuts a number stays cut
    and is refused.
    """
    while start > 0 and text[start - 1].isalpha() and text[start].isalpha():
        start -= 1
    while end < len(text) and text[end].isalpha() and text[end - 1].isalpha():
        end += 1
    return start, end


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
    return end - _best_reach(pattern, text[:end]), end, edits


def _best_reach(pattern: str, text: str) -> int:
    """How far back from the end of `text` the best alignment of `pattern` ending there starts.

    Searches the reversed text with the alignment pinned to its first character (the original's
    last), so it measures alignments that end exactly at the end of `text`. The shortest best one
    wins.
    """
    back = _end_scores(pattern[::-1], text[::-1], anchored=True)
    return back.index(min(back)) + 1


def _end_scores(pattern: str, text: str, *, anchored: bool = False) -> list[int]:
    """For each end position in `text`, the fewest edits to match `pattern` ending there.

    Unanchored, the match may start anywhere in `text`. Anchored, it must start at its first
    character (skipping text costs an edit per character).
    """
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
        ph = ((ph << 1) | (1 if anchored else 0)) & full
        mh = (mh << 1) & full
        pv = (mh | ~(xv | ph)) & full
        mv = ph & xv
        scores.append(score)
    if not scores:
        scores.append(m)
    return scores
