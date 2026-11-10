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
  the whole page: not part of a longer number or word ("450.00" isn't in "$12,450.00"), and with
  a sign that agrees with the page's. Signs follow provisional call 31 (`_sign_of`): where the
  page signs the amount one way only, the value's sign must match it ("$450.00" isn't confirmed
  in "-$450.00", nor "-$450" in "$300-$450"); where it could be read either way ("Airfare -
  $450.00"), the value's sign stands. Brackets around an amount still read as negative, also in
  prose, until brackets in a sentence are told apart (follow-up issue). On the safe side, a
  line-end hyphen between two letters or digits isn't a word edge ("Smith" isn't found in
  "Smith-" then "son").

Every cleaned-up text keeps a map from each of its characters back to the character it came
from, so a match can be turned back into a span of the original page text.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

LINE_DASH = "\x03"
"""Stands for a dash that ended a line right after a digit, whatever starts the next line.

It's kept, not dropped ("10-" then "20" is "10-20", not "1020"), and remembered as a line end:
after a number it reads as a trailing minus ("450.00-" then "2026-03-04", or then "$300.00"),
on the safe side. Two exceptions: inside a numeric date ("2026-" then "03-04"), and where the
value or passage being checked runs on through the dash into the next number ("10-20"), it's
the hyphen the reader took it for.
"""

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
NEGATIVE = "-"
POSITIVE = "+"
EITHER = "?"
"""How the text signs a number (see `_sign_of`). EITHER: it could be read either way."""

_MINUS = "\u2212"
_DASHES = frozenset("-\u2013")
"""A hyphen or en dash: a minus only where it's attached to the amount."""
_DATE = re.compile(
    r"\d{1,2}/\d{1,2}/\d{2,4}|\d{4}[-\x03]\d{1,2}[-\x03]\d{1,2}|\d{1,2}[-\x03]\d{1,2}[-\x03]\d{2,4}"
)
"""A numeric date. A date has no sign, so no dash before it is a minus."""
_BEFORE_ATTACHED_MINUS = frozenset({"", " ", "(", "[", "{", ":"})
"""What may come before an attached hyphen or en dash for it to be a minus (call 31, plus ":").

The empty string is the start of the text. A currency symbol counts too ("$-450.00").
"""
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
                out[-1] = LINE_DASH if after_digit else LINE_HYPHEN
            elif out[-1] != LINE_HYPHEN:
                out.append(" ")
                origin.append(space_at)
        space_at = None
        space_has_break = False
        if out and out[-1] == LINE_HYPHEN and after_digit:
            if soft_at != len(out) - 1:
                out[-1] = LINE_DASH
            elif ch.isdigit():
                # A soft hyphen is only a place a word may break, so between digits it goes.
                out.pop()
                origin.pop()

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
    ld = re.escape(LINE_DASH)
    parts: list[str] = []
    i = 0
    while i < len(q):
        ch = q[i]
        if i > 0 and _plain(q[i - 1]) and _plain(ch):
            parts.append(f"{hy}?")
        if ch == LINE_HYPHEN:
            parts.append(f"(?:{hy}|-)?")
        elif ch == "-" and i + 1 < len(q) and q[i + 1] == " ":
            parts.append(f"(?:- |{hy}|{ld})")
            i += 1
        elif ch in ("-", LINE_DASH):
            parts.append(f"(?:-|{hy}|{ld})")
        else:
            parts.append(re.escape(ch))
        i += 1
    return re.compile("".join(parts))


def _plain(ch: str) -> bool:
    return ch not in (" ", "-", LINE_HYPHEN, LINE_DASH)


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
    value = clean(value_text).text
    value_sign = _number_sign(value, 0, len(value))
    pos = start
    while (found := pattern.search(text, pos)) is not None and found.start() < end:
        s, e = found.start(), found.end()
        if (
            s < e <= end
            and _stands_alone(text, s, e)
            and _signs_agree(value_sign, _number_sign(text, s, e))
        ):
            return True
        pos = s + 1
    return False


def _signs_agree(value_sign: str, page_sign: str) -> bool:
    """A value's sign confirms against the page's sign (provisional call 31).

    Where the page can be read either way, the value's sign stands. Otherwise they must match: a
    value stated as positive doesn't confirm a clearly negative amount, and a negative value
    ("-$450") doesn't confirm where the page's dash is a hyphen ("$300-$450").
    """
    if page_sign == EITHER:
        return True
    return (value_sign == NEGATIVE) == (page_sign == NEGATIVE)


def _number_sign(text: str, start: int, end: int) -> str:
    """The sign the text puts on the first number in text[start:end] (POSITIVE with no number).

    Looks outside the slice too, since `text` is the whole page: the slice is a matched value and
    the sign may sit just outside it.
    """
    first = next((i for i in range(start, end) if text[i].isnumeric()), None)
    if first is None:
        return POSITIVE
    return _sign_of(text, first, _number_end(text, first), covered_until=end)


def _number_end(text: str, first: int) -> int:
    """Where the number starting at `first` ends, running through "." and "," between digits."""
    j = first
    while j < len(text) and text[j].isnumeric():
        j += 1
    while j + 1 < len(text) and text[j] in _NUMBER_SEPARATORS and text[j + 1].isnumeric():
        j += 2
        while j < len(text) and text[j].isnumeric():
            j += 1
    return j


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


def _sign_of(text: str, first: int, end: int, *, covered_until: int = -1) -> str:
    """How the text signs the number text[first:end]: NEGATIVE, POSITIVE or EITHER.

    Provisional call 31 (main coordinator, for Alex): code rejects a sign only where the text can
    be read one way.

    `covered_until` is the end of the value or span being checked. A LINE_DASH after the number
    with the next number also inside it ("10-" then "20", checked as "10-20") is the hyphen the
    reader took it for, not a trailing minus.

    - NEGATIVE, clearly:
      - a hyphen or en dash attached to the amount, with a space, the start of the text, an
        opening bracket, a currency symbol or a colon before the dash ("-$450.00", "$-450.00",
        "(-$450.00)", ":-$450.00");
      - the true minus U+2212, attached or with a space;
      - a trailing minus ("$450.00-", or a dash that ended the line right after the number,
        LINE_DASH) or "CR";
      - brackets around the amount ("($450.00)"). For now that includes brackets inside a
        sentence; telling those apart is a follow-up issue.
    - EITHER: a hyphen or en dash with a space between it and the amount ("Airfare \u2013
      $450.00", "Year 2 - $50,000", "$400 \u2013 $500", "- $450.00").
    - Never a sign, so POSITIVE unless something else applies: an em dash; a dash directly after
      a letter or digit ("$400-$500", "Year 2-$50,000", "10-20", "SYN-2026"), or after other
      punctuation than the above ("10%-20%", "(a)-$450"), read as a range; a trailing dash
      followed by a letter, digit or currency-and-digit (a range, "$450-$500"); any dash before
      a date ("09/01/2025 - 08/31/2027"), since a date has no sign.
    """
    if _DATE.match(text, first):
        return POSITIVE
    k = first
    while k > 0 and text[k - 1] in _CURRENCY:
        k -= 1
    leading = POSITIVE
    if k > 0:
        c = text[k - 1]
        before = text[k - 2] if k > 1 else ""
        if c == _MINUS:
            return NEGATIVE
        if c in _DASHES and (before in _BEFORE_ATTACHED_MINUS or before in _CURRENCY):
            return NEGATIVE
        if c == " " and before == _MINUS:
            return NEGATIVE
        if c == " " and before in _DASHES:
            leading = EITHER
    if end < len(text):
        after = text[end]
        nxt = text[end + 1] if end + 1 < len(text) else ""
        if after == LINE_DASH and end + 1 >= covered_until:
            # On the safe side, whatever starts the next line ("450.00-" then "2026-03-04" or
            # "$300.00"), unless the value checked runs on through the dash.
            return NEGATIVE
        if after in _SIGNS:
            range_follows = nxt.isalnum() or (
                nxt in _CURRENCY and end + 2 < len(text) and text[end + 2].isnumeric()
            )
            if not range_follows:
                return NEGATIVE
        rest = text[end : end + 3].lstrip(" ")
        if rest.startswith("CR") and not text[end:].lstrip(" ")[2:3].isalnum():
            return NEGATIVE
        if k > 0 and text[k - 1] == "(" and after == ")":
            return NEGATIVE
    return leading


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
    wanted = _number_tokens(q, 0, len(q))
    found = _number_tokens(text, start, end)
    if len(wanted) != len(found):
        return False
    for (want_sign, want_digits), (have_sign, have_digits) in zip(wanted, found, strict=True):
        if want_digits != have_digits:
            return False
        if EITHER not in (want_sign, have_sign) and want_sign != have_sign:
            return False
    return value_text is None or value_in_span(value_text, text, start, end)


def _number_tokens(text: str, start: int, end: int) -> list[tuple[str, str]]:
    """The runs of numeric characters in text[start:end], each with its number's sign.

    Numeric means any character Unicode counts as a number, so fractions and superscripts
    ("4\u00bd", "10\u00b2") count. A run that starts a number carries its sign (`_sign_of`);
    the later runs of the same number carry POSITIVE. Separators split runs but aren't kept, so
    "$12,450" and "$12.450" give the same runs.
    """
    tokens: list[tuple[str, str]] = []
    i = start
    while i < end:
        if not text[i].isnumeric():
            i += 1
            continue
        j = i
        while j < end and text[j].isnumeric():
            j += 1
        continues = i >= 2 and text[i - 1] in _NUMBER_SEPARATORS and text[i - 2].isnumeric()
        sign = POSITIVE if continues else _sign_of(text, i, _number_end(text, i), covered_until=end)
        tokens.append((sign, text[i:j]))
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
