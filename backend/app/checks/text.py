"""How status text writes money, dates and names. Every reason's text is built by code."""

import re
from datetime import date


def money(cents: int) -> str:
    """$1,240.00, or -$400.00 for a credit."""
    sign = "-" if cents < 0 else ""
    dollars, rest = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{rest:02d}"


def day(d: date) -> str:
    """Feb 20, 2026."""
    return f"{d:%b} {d.day}, {d.year}"


def norm(text: str) -> str:
    """Lowercase words with punctuation dropped, for comparing names the documents write."""
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text.lower()).split())


def slug(text: str) -> str:
    """A short stable ID made from text, for naming a problem."""
    return norm(text).replace(" ", "_")[:60] or "item"
