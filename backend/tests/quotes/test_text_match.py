"""The clean-up and matching steps, without any PDF."""

import random

import pytest

from app.quotes.text_match import (
    LINE_DASH,
    LINE_HYPHEN,
    _end_scores,  # pyright: ignore[reportPrivateUsage]
    best_substring_match,
    clean,
    close_span_ok,
    contains_exactly,
    find_exact,
    find_letters_and_digits,
    find_within_edits,
    span_stands_alone,
    value_in_span,
)


def test_clean_collapses_whitespace_and_keeps_origins() -> None:
    result = clean("  a \r\n\t b  ")
    assert result.text == "a b"
    assert result.origin == (2, 3, 8)


def test_clean_marks_line_end_hyphens() -> None:
    assert clean("re-\r\ncently").text == f"re{LINE_HYPHEN}cently"
    assert clean("re\x02cently").text == f"re{LINE_HYPHEN}cently"
    assert clean("re\u2010\r\ncently").text == f"re{LINE_HYPHEN}cently"
    # A hyphen followed by a plain space is a real hyphen.
    assert clean("pre- and post-award").text == "pre- and post-award"


def test_clean_straightens_quotes_and_spells_out_ligatures() -> None:
    result = clean("\u201cof\ufb01ce\u201d \u2018it\u2019s\u2019")
    assert result.text == "\"office\" 'it's'"
    # Both letters of the ligature map back to the one character they came from.
    assert result.origin[3:5] == (3, 3)


def test_clean_drops_zero_width_characters() -> None:
    assert clean("ab\u200bc\ufeff").text == "abc"


@pytest.mark.parametrize(
    "passage",
    ["approved by", "ap-proved by", "ap- proved by", "ap-\nproved by", "ap\u00adproved by"],
)
def test_exact_accepts_each_way_of_writing_a_line_hyphen(passage: str) -> None:
    page = clean("rate ap-\r\nproved by the")
    assert find_exact(passage, page)


def test_exact_keeps_a_real_hyphen_at_a_line_end() -> None:
    page = clean("the cost-\r\nsharing quote")
    assert find_exact("cost-sharing quote", page)
    assert find_exact("costsharing quote", page)


def test_exact_does_not_ignore_a_mid_line_hyphen() -> None:
    page = clean("Cost-sharing commitments")
    assert not find_exact("Costsharing commitments", page)
    assert not find_exact("Cost sharing commitments", page)


def test_exact_is_case_and_dash_sensitive() -> None:
    page = clean("the file \u2014 it will")
    assert find_exact("the file \u2014 it will", page)
    assert not find_exact("the file - it will", page)
    assert not find_exact("THE FILE \u2014 it will", page)


def test_exact_span_maps_back_to_the_page() -> None:
    raw = "Total due:\r\n$12,450.00 thanks"
    page = clean(raw)
    ((start, end),) = find_exact("due: $12,450.00", page)
    assert raw[page.origin[start] : page.origin[end - 1] + 1] == "due:\r\n$12,450.00"


def test_exact_finds_every_occurrence() -> None:
    page = clean("Total $40.00, tax $3.00, Total $40.00")
    assert len(find_exact("Total $40.00", page)) == 2


def test_contains_exactly() -> None:
    assert contains_exactly("$12,450.00", "Total due: $12,450.00")
    assert not contains_exactly("$12,540.00", "Total due: $12,450.00")
    assert contains_exactly("recently", f"most re{LINE_HYPHEN}cently")
    assert not contains_exactly("", "anything")


@pytest.mark.parametrize(
    ("value", "text", "found"),
    [
        ("450.00", "Total due: $12,450.00", False),
        ("$12,450", "Total due: $12,450.00", False),
        ("12,450", "Total due: $12,450.00", False),
        ("2,450.00", "Total due: $12,450.00", False),
        ("$12,450.00", "Total due: $12,450.00.", True),
        ("$12,450.00", "($12,450.00)", False),
        ("($12,450.00)", "Refund ($12,450.00) posted", True),
        ("$450.00", "Adjustment of -$450.00 posted", False),
        ("-$450.00", "Adjustment of -$450.00 posted", True),
        ("$450.00", "Adjustment of \u2212$450.00 posted", False),
        ("500", "the total (500 units) was", True),
        ("2026", "SYN-2026-0117", True),
        ("20", "pages 10-20 of the", True),
        ("SYN", "SYNTHETIC", False),
        ("40", "40 boxes, 400 tips", True),
        ("40", "400 tips", False),
        ("4", "rate 4\u00bd dollars", False),
    ],
)
def test_a_value_has_to_stand_on_its_own(value: str, text: str, found: bool) -> None:
    assert contains_exactly(value, clean(text).text) is found


def test_a_value_is_found_later_in_the_text_after_a_partial_hit() -> None:
    assert contains_exactly("450.00", "$12,450.00 then $450.00")


def test_a_value_at_the_edge_of_a_span_is_checked_against_the_page() -> None:
    page = "Total due: $12,450.00 was paid"
    start = page.index("450.00")
    assert not value_in_span("450.00", page, start, len(page))
    end = page.index(".00")
    assert not value_in_span("$12,450", page, 0, end)
    assert value_in_span("$12,450.00", page, 0, len(page))


@pytest.mark.parametrize(
    ("page", "passage"),
    [
        ("Total due for the order: $12,450.00 was paid on time", "450.00 was paid on time"),
        ("The order total came to $12,450.00 net 30", "The order total came to $12,450"),
        ("The travel cost for the trip was $450 in total", "The travel cost for the trip was $45"),
        ("The Total due was paid", "otal due was paid"),
    ],
)
def test_a_span_cut_out_of_a_number_or_word_is_refused(page: str, passage: str) -> None:
    text = clean(page)
    (span,) = find_exact(passage, text)
    assert not span_stands_alone(text.text, *span)


def test_a_whole_span_stands_alone() -> None:
    text = clean("Total due: $12,450.00 was paid")
    (span,) = find_exact("$12,450.00 was paid", text)
    assert span_stands_alone(text.text, *span)


def test_letters_and_digits_widens_over_punctuation() -> None:
    page = clean("Amount: $9,850.00. Next line")
    ((start, end),) = find_letters_and_digits("AMOUNT $9850.00", page)
    assert page.text[start:end] == "Amount: $9,850.00."


def _ok(passage: str, value: str | None, page: str) -> bool:
    return close_span_ok(passage, value, page, 0, len(page))


def test_close_guard_numbers_must_match_exactly() -> None:
    span = "Benchtop centrifuge, 24-place rotor 1 $9,850.00 $9,850.00"
    assert _ok("Benchtop centrifuge, 24-place rotr 1 $9,850.00 $9,850.00", None, span)
    assert not _ok("Benchtop centrifuge, 24-place rotor 1 $9,850.00 $9,580.00", None, span)
    assert not _ok("Benchtop centrifuge 24 place rotor 19,850.00", None, span)


@pytest.mark.parametrize(
    ("passage", "page"),
    [
        ("Travel cost $1,450.00 in total", "Travel cost 7 $1,450.00 in total"),
        ("Travel cost $1,450.00 in total", "Travel cost $1,450.00 2 in total"),
        ("Travel cost $1,450.00 in total", "Travel cost $1,4500.00 in total"),
        ("hourly rate 4\u00bd dollars", "hourly rate 4\u00bc dollars"),
        ("area of 10\u00b2 square feet", "area of 10\u00b3 square feet"),
        ("Adjustment of $450.00 posted", "Adjustment of -$450.00 posted"),
        ("Adjustment of $450.00 posted", "Adjustment of ($450.00) posted"),
        ("Invoice number 12345 was paid", "Invoice number 12 345 was paid"),
    ],
)
def test_close_guard_refuses_any_change_to_a_number(passage: str, page: str) -> None:
    """Digits added, dropped or changed, fractions, superscripts, signs, and split numbers."""
    assert not _ok(passage, None, page)


def test_close_guard_ignores_a_changed_separator_when_no_value_is_given() -> None:
    page = "The order total came to $12.450 net"
    assert _ok("The order total came to $12,450 net", None, page)
    assert not _ok("The order total came to $12,450 net", "$12,450", page)


def test_close_guard_value_must_be_in_the_span() -> None:
    span = "Total due: $12,450.00"
    assert _ok("TOTAL DUE: $12,450.00", "$12,450.00", span)
    assert not _ok("TOTAL DUE: $12,450.00", "$12,540.00", span)
    assert not _ok("TOTAL DUE: $12,450.00", "450.00", span)


def test_close_steps_skip_short_passages() -> None:
    page = clean("Total $40.00 and $4,000 more text here")
    assert not find_letters_and_digits("$ 40.00", page)
    assert not find_within_edits("$4O.00", page)


def test_within_edits_finds_a_misread_and_refuses_a_poor_match() -> None:
    page = clean("Nitrile gloves, size M (box of 100) 40 $14.50 $580.00")
    ((span, edits),) = find_within_edits("Nitrlie gloves, size M (box of 100)", page)
    assert edits == 2
    assert page.text[span[0] : span[1]].startswith("Nitrile gloves")
    assert not find_within_edits("Latex gloves, size L (box of 250)", page)


def test_within_edits_returns_every_place_and_takes_whole_words() -> None:
    page = clean(
        "Lodging was $390.00 per night for the staff.\r\nfiller line\r\n"
        "Ldging ws $300.00 per night for the staff."
    )
    found = find_within_edits("Lodging was $300.00 per night for the staf.", page)
    assert len(found) == 2
    texts = [page.text[s:e] for (s, e), _ in found]
    assert texts[0] == "Lodging was $390.00 per night for the staff."
    assert texts[1] == "Ldging ws $300.00 per night for the staff."


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


def test_clean_keeps_a_line_end_hyphen_between_digits() -> None:
    assert clean("pages 10-\r\n20 of the").text == f"pages 10{LINE_DASH}20 of the"
    assert clean("pages 10\x0220 of the").text == f"pages 10{LINE_DASH}20 of the"
    page = clean("pages 10-\r\n20 of the")
    assert not find_exact("pages 1020 of the", page)
    assert find_exact("pages 10-20 of the", page)
    assert find_exact("pages 10-\n20 of the", page)
    assert find_exact("pages 10- 20 of the", page)


def test_clean_turns_two_single_quotes_into_a_double_quote() -> None:
    gpo = clean("rule, \u2018\u2018New Restrictions,\u2019\u2019 published")
    assert gpo.text == 'rule, "New Restrictions," published'
    assert clean("''quoted''").text == '"quoted"'
    # Two apostrophes with something between them stay single quotes.
    assert clean("\u2018it\u2019").text == "'it'"


def test_clean_lets_a_soft_hyphen_drop() -> None:
    page = clean("hyphen\u00adation")
    assert find_exact("hyphenation", page)


def test_clean_drops_a_soft_hyphen_between_digits() -> None:
    assert (
        clean("the order total was 1\u00ad450 dollars").text == "the order total was 1450 dollars"
    )
    # pdfium's own line-end hyphen between digits is a real dash that ended a line.
    assert clean("pages 10\x0220").text == f"pages 10{LINE_DASH}20"


@pytest.mark.parametrize(
    "page",
    [
        "Travel refund 450.00-\n2026-03-04 Lodging 300.00",
        "Travel refund 450.00\x022026-03-04 Lodging 300.00",
    ],
)
def test_a_dash_ending_a_line_after_a_number_is_a_trailing_minus(page: str) -> None:
    """A ledger report's "450.00-" with a date on the next line isn't confirmed as 450.00."""
    text = clean(page)
    (span,) = find_exact("Travel refund 450.00", text)
    assert not value_in_span("450.00", text.text, *span)
    # The date on the next line is still read as written.
    assert contains_exactly("2026-03-04", text.text)
    # A passage keeping the minus matches, and its tokens carry the sign.
    assert find_exact("Travel refund 450.00-\n2026-03-04", text)


def test_close_guard_reads_a_dash_ending_a_line_as_a_minus() -> None:
    page = clean("Travel refund for the conference 450.00-\n2026-03-04 Lodging").text
    end = page.index("Lodging")
    assert not close_span_ok("Travl refund for the conference 450.00", "450.00", page, 0, end)


def test_a_range_broken_across_lines_doesnt_confirm_its_first_number() -> None:
    """On the safe side (stricter than call 31): "10-" then "20" may be a trailing minus.

    So "10" alone isn't confirmed. The whole range "10-20" is, since the value runs on through
    the dash, and so is "20".
    """
    page = clean("Stay of 10-\n20 days for the field work").text
    assert not contains_exactly("10", page)
    assert contains_exactly("10-20", page)
    assert contains_exactly("20", page)
    close = "Stay of 10-\n20 dys for the field work"
    text = clean(close).text
    assert close_span_ok("Stay of 10-20 days for the field work", None, text, 0, len(text))


@pytest.mark.parametrize(
    ("page", "value"),
    [
        ("Travel dates 2026-\n03-04 to 2026-03-09", "2026-03-04"),
        ("Travel dates 2026\x0203-04 to 2026-03-09", "2026-03-04"),
        ("Period 09-\n01-2025 to 08-31-2027", "09-01-2025"),
        ("Travel dates 2026-\n03-04 to 2026-03-09", "2026"),
    ],
)
def test_a_date_broken_at_its_dash_confirms(page: str, value: str) -> None:
    """A date has no sign, so a dash ending the line inside it isn't a minus."""
    assert contains_exactly(value, clean(page).text)


@pytest.mark.parametrize(
    "next_line",
    ["$300.00 Lodging", "(see note 2)", "* adjusted", "# 14 Lodging", "\u2022 Lodging", "Lodging"],
)
def test_a_dash_ending_a_line_after_a_digit_is_a_minus_whatever_follows(next_line: str) -> None:
    """ "$450.00-" at a line end is a credit whatever starts the next line."""
    page = clean(f"Travel refund $450.00-\n{next_line}").text
    assert not contains_exactly("$450.00", page)
    assert contains_exactly("$450.00-", page)


@pytest.mark.parametrize(
    ("value", "page", "found"),
    [
        ("20%", "a share of 10%-20% of the cost", True),
        ("$450", "item (a)-$450 for lodging", True),
        ("$450", "Adjustment:-$450 posted", False),
        ("$450", "Adjustment [-$450] posted", False),
        ("$450", "Adjustment {-$450} posted", False),
    ],
)
def test_a_dash_after_other_punctuation_is_a_range(value: str, page: str, found: bool) -> None:
    """Call 31 names a space, line start, opening bracket or currency symbol, plus ":"."""
    assert contains_exactly(value, clean(page).text) is found


@pytest.mark.parametrize(
    ("value", "page", "found"),
    [
        ("-$450", "Hotel rates run $300-$450 per night", False),
        ("-450", "Charged to account 10-450 for the lab", False),
        ("-450", "Charged to account SYN-450 for the lab", False),
        ("-$450", "Adjustment of -$450 posted", True),
        ("-$450", "Adjustment:-$450 posted", True),
        ("$450-", "Adjustment of $450- posted", True),
        ("$450-", "Rates $450-$500 per night", False),
        ("$450-", "Rates $450-500 per night", False),
        ("450.00-", "refund 450.00-\n2026-03-04", True),
    ],
)
def test_a_value_carrying_its_own_minus_needs_a_minus_on_the_page(
    value: str, page: str, found: bool
) -> None:
    """A negative record must not confirm where the page's dash is a hyphen."""
    assert contains_exactly(value, clean(page).text) is found


@pytest.mark.parametrize(
    ("value", "page", "found"),
    [
        # 1. Clearly negative: a positive value doesn't confirm.
        ("$450.00", "Adjustment of -$450.00 posted", False),
        ("$450.00", "Adjustment of \u2013$450.00 posted", False),
        ("450.00", "Adjustment of $-450.00 posted", False),
        ("$450.00", "Adjustment of (-$450.00) posted", False),
        ("$450.00", "Adjustment of \u2212$450.00 posted", False),
        ("$450.00", "Adjustment of \u2212 $450.00 posted", False),
        ("$450.00", "Adjustment of $450.00- posted", False),
        ("$450.00", "Adjustment of $450.00\u2013 posted", False),
        ("$450.00", "Adjustment of $450.00-", False),
        ("$450.00", "Adjustment of $450.00 CR posted", False),
        ("$450.00", "Adjustment ($450.00)", False),
        ("$450.00", "The airfare ($450.00) was booked", False),
        # 2. No mark: a positive value confirms.
        ("$450.00", "Adjustment of $450.00 posted", True),
        # 3. Could be either: the value's sign stands.
        ("$450.00", "Airfare \u2013 $450.00", True),
        ("$50,000", "Year 2 - $50,000", True),
        ("$500", "Rates run $400 \u2013 $500 per night", True),
        ("$450.00", "Adjustment of - $450.00 posted", True),
        ("20", "pages 10 - 20 of the", True),
        # 4. Never a sign.
        ("$450.00", "Total \u2014 $450.00 posted", True),
        ("$500", "Rates $400-$500 per night", True),
        ("$400", "Rates $400-$500 per night", True),
        ("$450", "Rates $450\u2013$500 per night", True),
        ("$50,000", "Year 2-$50,000", True),
        ("20", "pages 10-20 of the", True),
        ("20", "pages 10\u201320 of the", True),
        ("10", "pages 10-20 of the", True),
        ("2026", "Award SYN-2026 funded", True),
        ("09/01/2025", "Period of performance: 09/01/2025 - 08/31/2027", True),
        ("08/31/2027", "Period of performance: 09/01/2025 - 08/31/2027", True),
        ("08/31/2027", "Period of performance: 09/01/2025 -08/31/2027", True),
    ],
)
def test_signs_follow_call_31(value: str, page: str, found: bool) -> None:
    """Provisional call 31: a sign is rejected only where the text can be read one way."""
    assert contains_exactly(value, clean(page).text) is found


@pytest.mark.parametrize(
    "page",
    [
        "Adjustment of -$450.00 posted",
        "Adjustment of \u2013$450.00 posted",
        "Adjustment of $450.00- posted",
    ],
)
def test_close_guard_reads_a_clear_minus(page: str) -> None:
    assert not close_span_ok("Adjustment of $450.00 posted", None, page, 0, len(page))


@pytest.mark.parametrize(
    "page",
    ["Airfare - $450.00 posted", "Airfare \u2013 $450.00 posted"],
)
def test_close_guard_lets_the_passage_sign_stand_on_a_spaced_dash(page: str) -> None:
    assert close_span_ok("Airfare $450.00 posted", None, page, 0, len(page))


def _brute_force_anchored(pattern: str, text: str) -> list[int]:
    """Edit distance from `pattern` to each prefix text[:j + 1], by plain dynamic programming."""
    prev = list(range(len(pattern) + 1))
    out = []
    for j, ch in enumerate(text, 1):
        cur = [j]
        for i, p in enumerate(pattern, 1):
            cur.append(min(prev[i] + 1, cur[i - 1] + 1, prev[i - 1] + (p != ch)))
        out.append(cur[-1])
        prev = cur
    return out


def test_anchored_scores_agree_with_brute_force() -> None:
    rng = random.Random(32)
    for _ in range(300):
        text = "".join(rng.choice("abcd") for _ in range(rng.randint(1, 60)))
        pattern = "".join(rng.choice("abcd") for _ in range(rng.randint(1, 80)))
        assert _end_scores(pattern, text, anchored=True) == _brute_force_anchored(pattern, text)


def test_a_line_end_hyphen_is_not_a_word_edge() -> None:
    """ "Smith-" then "son" may be "Smithson", so "Smith" isn't found there."""
    page = clean("Trip approved by Smith-\nson for the visit").text
    assert not contains_exactly("Smith", page)
    assert contains_exactly("Smithson", page)
    room = clean("Moved to Room-\n450 for the setup").text
    assert not contains_exactly("450", room)


@pytest.mark.parametrize(
    "page",
    [
        'The ledger line reads "-$450.00" for the refund',
        "The ledger line reads '-$450.00' for the refund",
        "Balance=-$450.00 after the refund",
        "Credits;-$450.00 after the refund",
        "Adjustments,-$450.00 after the refund",
        "Total / -$450.00 after the refund",
        "Total \u2014-$450.00 after the refund",
        "Item *-$450.00 refund",
    ],
)
def test_an_attached_dash_after_other_punctuation_is_a_minus(page: str) -> None:
    """Only a letter, digit, "%", closing bracket, or a quote after one of those makes a hyphen."""
    assert not contains_exactly("$450.00", clean(page).text)
    assert contains_exactly("-$450.00", clean(page).text)


@pytest.mark.parametrize(
    ("page", "value"),
    [
        ("Effort of 10%-20% on the award", "20%"),
        ("Option (a)-$450 per night", "$450"),
        ("Option [b]-$450 per night", "$450"),
        ('the "Gold"-$450 rate', "$450"),
    ],
)
def test_an_attached_dash_after_a_word_end_is_a_range(page: str, value: str) -> None:
    assert contains_exactly(value, clean(page).text)


@pytest.mark.parametrize(
    ("page", "value"),
    [
        ("Refund $12-\n3-15 Fee waived", "$12"),
        ("Refund 1234-\n05-06 Lodging", "1234"),
    ],
)
def test_a_date_across_a_line_end_dash_needs_the_whole_date(page: str, value: str) -> None:
    """A trailing minus before something date-shaped on the next line stays a minus."""
    assert not contains_exactly(value, clean(page).text)
    assert contains_exactly(f"{value}-", clean(page).text)


@pytest.mark.parametrize(
    "page",
    ["Travel refund 450.00-\n-$12.00 Fee", "Late credit-\n-$12.00 Fee"],
)
def test_a_minus_starting_a_line_after_a_line_end_dash_is_a_minus(page: str) -> None:
    """Call 31, point 1: a dash at the start of a line, attached to the amount, is a minus."""
    text = clean(page).text
    assert not contains_exactly("$12.00", text)
    assert contains_exactly("-$12.00", text)


@pytest.mark.parametrize(
    "page",
    ["Credit amount – USD 248.00", "Credit amount - usd 248.00", "Hotel - US$248.00"],
)
def test_a_currency_code_after_a_spaced_dash_reads_either_way(page: str) -> None:
    """Ruling 3 (the coordinator's call on PR 105): like a spaced dash alone."""
    from app.quotes.text_match import EITHER, amount_sign, sign_reads_either_way

    text = clean(page).text
    start = text.index("248")
    assert amount_sign(text, start, len(text)) == EITHER
    assert sign_reads_either_way(text, start, len(text))


def test_a_currency_code_with_no_dash_before_it_stays_positive() -> None:
    from app.quotes.text_match import POSITIVE, amount_sign

    text = clean("Credit amount USD 248.00").text
    assert amount_sign(text, text.index("248"), len(text)) == POSITIVE
