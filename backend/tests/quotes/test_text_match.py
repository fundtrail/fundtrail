"""The clean-up and matching steps, without any PDF."""

import random

import pytest

from app.quotes.text_match import (
    LINE_HYPHEN,
    best_substring_match,
    clean,
    contains_exactly,
    find_exact,
    find_letters_and_digits,
    find_within_edits,
)


def test_clean_collapses_whitespace_and_keeps_origins() -> None:
    result = clean("  a \r\n\t b  ")
    assert result.text == "a b"
    assert result.origin == (2, 3, 8)


def test_clean_marks_line_end_hyphens() -> None:
    assert clean("re-\r\ncently").text == f"re{LINE_HYPHEN}cently"
    assert clean("re\x02cently").text == f"re{LINE_HYPHEN}cently"
    assert clean("re‐\r\ncently").text == f"re{LINE_HYPHEN}cently"
    # A hyphen followed by a plain space is a real hyphen.
    assert clean("pre- and post-award").text == "pre- and post-award"


def test_clean_straightens_quotes_and_spells_out_ligatures() -> None:
    result = clean("“ofﬁce” ‘it’s’")
    assert result.text == "\"office\" 'it's'"
    # Both letters of the ligature map back to the one character they came from.
    assert result.origin[3:5] == (3, 3)


def test_clean_drops_zero_width_characters() -> None:
    assert clean("ab​c﻿").text == "abc"


@pytest.mark.parametrize(
    "passage",
    ["approved by", "ap-proved by", "ap- proved by", "ap-\nproved by", "ap­proved by"],
)
def test_exact_accepts_each_way_of_writing_a_line_hyphen(passage: str) -> None:
    page = clean("rate ap-\r\nproved by the")
    assert find_exact(passage, page) is not None


def test_exact_keeps_a_real_hyphen_at_a_line_end() -> None:
    page = clean("the cost-\r\nsharing quote")
    assert find_exact("cost-sharing quote", page) is not None
    assert find_exact("costsharing quote", page) is not None


def test_exact_does_not_ignore_a_mid_line_hyphen() -> None:
    page = clean("Cost-sharing commitments")
    assert find_exact("Costsharing commitments", page) is None
    assert find_exact("Cost sharing commitments", page) is None


def test_exact_is_case_and_dash_sensitive() -> None:
    page = clean("the file — it will")
    assert find_exact("the file — it will", page) is not None
    assert find_exact("the file - it will", page) is None
    assert find_exact("THE FILE — it will", page) is None


def test_exact_span_maps_back_to_the_page() -> None:
    raw = "Total due:\r\n$12,450.00 thanks"
    page = clean(raw)
    span = find_exact("due: $12,450.00", page)
    assert span is not None
    start, end = span
    assert raw[page.origin[start] : page.origin[end - 1] + 1] == "due:\r\n$12,450.00"


def test_contains_exactly() -> None:
    assert contains_exactly("$12,450.00", "Total due: $12,450.00")
    assert not contains_exactly("$12,540.00", "Total due: $12,450.00")
    assert contains_exactly("recently", f"most re{LINE_HYPHEN}cently")
    assert not contains_exactly("", "anything")


def test_letters_and_digits_widens_over_punctuation() -> None:
    page = clean("Amount: $9,850.00. Next line")
    span = find_letters_and_digits("AMOUNT $9850.00", page)
    assert span is not None
    assert page.text[span[0] : span[1]] == "Amount: $9,850.00."


def test_close_steps_skip_short_passages() -> None:
    page = clean("Total $40.00 and $4,000 more text here")
    assert find_letters_and_digits("$ 40.00", page) is None
    assert find_within_edits("$4O.00", page) is None


def test_within_edits_finds_a_misread_and_refuses_a_poor_match() -> None:
    page = clean("Nitrile gloves, size M (box of 100) 40 $14.50 $580.00")
    found = find_within_edits("Nitrlie gloves, size M (box of 100)", page)
    assert found is not None
    span, edits = found
    assert edits == 2
    assert page.text[span[0] : span[1]].startswith("Nitrile gloves")
    assert find_within_edits("Latex gloves, size L (box of 250)", page) is None


def _brute_force(pattern: str, text: str) -> int:
    """The fewest edits to turn `pattern` into any substring of `text`, by plain dynamic
    programming."""
    prev = list(range(len(pattern) + 1))
    best = prev[-1]
    for ch in text:
        cur = [0]
        for i, p in enumerate(pattern, 1):
            cur.append(min(prev[i] + 1, cur[i - 1] + 1, prev[i - 1] + (p != ch)))
        best = min(best, cur[-1])
        prev = cur
    return best


def test_best_substring_match_agrees_with_brute_force() -> None:
    rng = random.Random(19)
    for _ in range(300):
        text = "".join(rng.choice("abcd") for _ in range(rng.randint(1, 60)))
        pattern = "".join(rng.choice("abcd") for _ in range(rng.randint(1, 80)))
        found = best_substring_match(pattern, text)
        assert found is not None
        start, end, edits = found
        assert edits == _brute_force(pattern, text)
        # The span it returns really is that close.
        assert _brute_force(pattern, text[start:end]) == edits
