from datetime import date

import pytest

from fundtrail.normalize import check_value, find_money, normalize_date, normalize_money


@pytest.mark.parametrize(
    "value",
    ["August 31, 2025", "Aug. 31, 2025", "Aug 31 2025", "31 August 2025", "2025-08-31", "8/31/2025", "08/31/25"],
)
def test_date_formats_normalize_to_same_day(value):
    assert normalize_date(value) == date(2025, 8, 31)


@pytest.mark.parametrize("value", ["next Tuesday", "", "September 1, 2022 through August 31, 2025", "February 30, 2025"])
def test_date_rejects_zero_or_several_or_invalid_dates(value):
    assert normalize_date(value) is None


@pytest.mark.parametrize(
    "value, cents",
    [("$300,000", 30_000_000), ("$1,180.50", 118_050), ("300,000", 30_000_000), ("$ 4200", 420_000)],
)
def test_money_normalizes_to_cents(value, cents):
    assert normalize_money(value) == cents


def test_money_rejects_non_amounts():
    assert normalize_money("about three hundred thousand") is None
    assert normalize_money("$300,000 in direct costs") is None


def test_find_money_ignores_numbers_without_dollar_sign():
    assert find_money("40 of 96 samples in 2026 cost $6,400.") == [640_000]


def test_reformatted_date_still_verifies_against_cited_text():
    normalized, ok = check_value("date", "2025-08-31", "The period is September 1, 2022 through August 31, 2025.")
    assert (normalized, ok) == ("2025-08-31", True)


def test_wrong_amount_does_not_verify_even_if_digits_overlap():
    _, ok = check_value("money", "$300,000", "Funds budgeted for participant support costs ($30,000) may not")
    assert ok is False


def test_text_match_ignores_case_and_whitespace():
    _, ok = check_value("text", "casey.lin@funder.example", "Grants Officer: Casey Lin,\n casey.lin@FUNDER.example")
    assert ok is True


def test_empty_text_never_verifies():
    assert check_value("text", "   ", "anything")[1] is False
