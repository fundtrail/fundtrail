"""Normalize extracted values and check them against the text they cite.

The model is told to copy values verbatim, but code never trusts that. A field
counts as verified only if its normalized value also appears in the passage its
citation points to. Dates compare as calendar dates, money as integer cents,
and everything else as case- and whitespace-insensitive text.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

FieldKind = Literal["date", "money", "text"]

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH = (
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
)
_DATE_MONTH_FIRST = re.compile(rf"\b{_MONTH}\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.IGNORECASE)
_DATE_DAY_FIRST = re.compile(rf"\b(\d{{1,2}})\s+{_MONTH},?\s+(\d{{4}})\b", re.IGNORECASE)
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_DATE_US_NUMERIC = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b")

# In cited text, only amounts written with a dollar sign count as money, so
# years and sample counts are never mistaken for amounts.
_MONEY_IN_TEXT = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?(?!\d)")
_MONEY_VALUE = re.compile(r"^\$?\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?$")


def _safe_date(year: int, month: int, day: int) -> date | None:
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_dates(text: str) -> list[date]:
    """Every calendar date written in the text, in any supported format."""
    found: list[date] = []
    for m in _DATE_MONTH_FIRST.finditer(text):
        found.append(_safe_date(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2))))
    for m in _DATE_DAY_FIRST.finditer(text):
        found.append(_safe_date(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1))))
    for m in _DATE_ISO.finditer(text):
        found.append(_safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in _DATE_US_NUMERIC.finditer(text):
        found.append(_safe_date(int(m.group(3)), int(m.group(1)), int(m.group(2))))
    return [d for d in found if d is not None]


def normalize_date(value: str) -> date | None:
    """The single date a value states, or None if it states zero or several."""
    dates = set(find_dates(value))
    return dates.pop() if len(dates) == 1 else None


def _to_cents(whole: str, fraction: str | None) -> int:
    return int(whole.replace(",", "")) * 100 + int(fraction or 0)


def find_money(text: str) -> list[int]:
    """Every dollar amount in the text, in cents."""
    return [_to_cents(m.group(1), m.group(2)) for m in _MONEY_IN_TEXT.finditer(text)]


def normalize_money(value: str) -> int | None:
    """A value such as "$300,000" or "1,180.50" in cents, or None if it is not an amount."""
    m = _MONEY_VALUE.match(value.strip())
    return _to_cents(m.group(1), m.group(2)) if m else None


def normalize_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def check_value(kind: FieldKind, value: str, cited_text: str) -> tuple[str | int | None, bool]:
    """Normalize a value and report whether the cited text states the same value.

    Returns (normalized value, whether the cited text supports it). The
    normalized value is an ISO date string, an integer number of cents, or
    normalized text, and is None when the value cannot be read as its kind.
    """
    if kind == "date":
        d = normalize_date(value)
        return (d.isoformat() if d else None), (d is not None and d in find_dates(cited_text))
    if kind == "money":
        cents = normalize_money(value)
        return cents, (cents is not None and cents in find_money(cited_text))
    text = normalize_text(value)
    return text, (bool(text) and text in normalize_text(cited_text))
