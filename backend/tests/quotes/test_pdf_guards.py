"""The guards on a match, on small PDFs drawn in memory with reportlab (a dev dependency).

A close match still confirms a value, so it must not be able to hide a wrong number; and a
value must not be found as the head or tail of a longer number on the page.
"""

import io
from typing import NamedTuple

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.quotes import find_pdf_quote


def _pdf(pages: list[list[str]]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter, invariant=True)
    c.setFont("Helvetica", 10)
    for lines in pages:
        y = 700
        for line in lines:
            c.drawString(72, y, line)
            y -= 14
        c.showPage()
    c.save()
    return buf.getvalue()


class Probe(NamedTuple):
    name: str
    pages: list[list[str]]
    passage: str
    value: str | None
    expect: str
    value_found: bool | None
    end_page: int = 2
    pages_hit: tuple[int, ...] = ()


TRAVEL = "Travel to the Boston conference cost {} in total for the trip."
TYPO = "Travel to the Bostn conference cost $1,450.00 in total for the trip."
SPLIT_1 = ["The cost of the conference travel was"]
SIGNED = [
    ("an attached hyphen", "-$450.00"),
    ("an attached en dash", "\u2013$450.00"),
    ("a trailing minus", "$450.00-"),
]
"""Clearly negative under call 31: a value stated as positive must not confirm."""
SPLIT_PASSAGE = "The cost of the conference travel was $1,450.00 for the whole trip."

PROBES = [
    Probe(
        "close, letter typo only", [[TRAVEL.format("$1,450.00")]], TYPO, "$1,450.00", "close", True
    ),
    Probe(
        "close, digit changed",
        [[TRAVEL.format("$1,451.00")]],
        TYPO,
        "$1,450.00",
        "not_found",
        False,
    ),
    Probe(
        "close, digit dropped", [[TRAVEL.format("$1,45.00")]], TYPO, "$1,450.00", "not_found", False
    ),
    Probe(
        "close, digits swapped",
        [[TRAVEL.format("$1,540.00")]],
        TYPO,
        "$1,450.00",
        "not_found",
        False,
    ),
    Probe(
        "close, digit inserted",
        [[TRAVEL.format("$1,4500.00")]],
        TYPO,
        "$1,450.00",
        "not_found",
        False,
    ),
    Probe(
        "close, a number added after",
        [[TRAVEL.format("$1,450.00 2")]],
        TYPO,
        "$1,450.00",
        "not_found",
        False,
    ),
    Probe(
        "close, a number added before, no value",
        [["Travel to the Boston conference cost 7 $1,450.00 in total for the trip."]],
        TYPO,
        None,
        "not_found",
        None,
    ),
    Probe(
        "exact, passage starts mid-number",
        [["Total due for the order: $12,450.00 was paid on time"]],
        "450.00 was paid on time",
        "450.00",
        "not_found",
        False,
    ),
    Probe(
        "exact, passage ends mid-number",
        [["The order total came to $12,450.00 net 30"]],
        "The order total came to $12,450",
        "$12,450",
        "not_found",
        False,
    ),
    Probe(
        "exact, passage ends on a digit prefix",
        [["The travel cost for the trip was $450 in total"]],
        "The travel cost for the trip was $45",
        "$45",
        "not_found",
        False,
    ),
    Probe(
        "close, passage starts mid-number",
        [["Total due for the order: $12,450.00 was paid on time"]],
        "450.00 was pad on time",
        "450.00",
        "not_found",
        False,
    ),
    Probe(
        "close, passage ends mid-number",
        [["The order total came to $12,450.00 net 30"]],
        "The order totl came to $12,450",
        "$12,450",
        "not_found",
        False,
    ),
    Probe(
        "exact, value is the tail of a number in the span",
        [["Total due for the order: $12,450.00 net 30"]],
        "Total due for the order: $12,450.00 net 30",
        "450.00",
        "exact",
        False,
    ),
    Probe(
        "exact, value is the head of a number in the span",
        [["Total due for the order: $12,450.00 net 30"]],
        "Total due for the order: $12,450.00 net 30",
        "$12,450",
        "exact",
        False,
    ),
    Probe(
        "exact, sign on the page the value lacks",
        [["Adjustment to the order total of -$450.00 posted"]],
        "Adjustment to the order total of -$450.00 posted",
        "$450.00",
        "exact",
        False,
    ),
    Probe(
        "close, sign on the page the passage lacks",
        [["Adjustment to the order total of -$450.00 posted"]],
        "Adjustment to the order totl of $450.00 posted",
        "$450.00",
        "not_found",
        False,
    ),
    Probe(
        "two pages, value on page 2",
        [SPLIT_1, ["$1,450.00 for the whole trip."]],
        SPLIT_PASSAGE,
        "$1,450.00",
        "exact",
        True,
        end_page=3,
        pages_hit=(1, 2),
    ),
    Probe(
        "two pages, page 2 says another amount",
        [SPLIT_1, ["$1,451.00 for the whole trip."]],
        SPLIT_PASSAGE,
        "$1,450.00",
        "not_found",
        False,
        end_page=3,
    ),
    Probe(
        "two pages, close, page 2 says another amount",
        [SPLIT_1, ["$1,451.00 for the whole trip."]],
        "The cost of the conferense travel was $1,450.00 for the whole trip.",
        "$1,450.00",
        "not_found",
        False,
        end_page=3,
    ),
    Probe(
        "one-page citation doesn't read page 2",
        [SPLIT_1, ["$1,450.00 for the whole trip."]],
        SPLIT_PASSAGE,
        "$1,450.00",
        "not_found",
        False,
    ),
    Probe(
        "twice, close, the other one has another amount",
        [
            [
                "Lodging was $300.00 per night for staff.",
                "filler line",
                "Lodging was $390.00 per night for staff.",
            ]
        ],
        "Lodgng was $300.00 per night for staff.",
        "$300.00",
        "close",
        True,
    ),
    Probe(
        "twice, edits, the better one has a wrong digit",
        [
            [
                "Lodging was $390.00 per night for the staff.",
                "filler line",
                "Ldging ws $300.00 per night for the staff.",
            ]
        ],
        "Lodging was $300.00 per night for the staf.",
        "$300.00",
        "close",
        True,
    ),
    Probe(
        "a space inside a number is a different number",
        [["Invoice number 12 345 was paid on March 3"]],
        "Invoice number 12345 was paid on March 3",
        None,
        "not_found",
        None,
    ),
    *[
        Probe(
            f"exact, {name} on the page the value lacks",
            [[f"Adjustment to the order total of {amount} posted"]],
            f"Adjustment to the order total of {amount} posted",
            "$450.00",
            "exact",
            False,
        )
        for name, amount in SIGNED
    ],
    *[
        Probe(
            f"close, {name} on the page the passage lacks",
            [[f"Adjustment to the order total of {amount} posted"]],
            "Adjustment to the order totl of $450.00 posted",
            "$450.00",
            "not_found",
            False,
        )
        for name, amount in SIGNED
    ],
    # Call 31, point 3: a spaced dash could be either, so the value's sign stands.
    *[
        Probe(f"either: {line}", [[line]], line, value, "exact", True)
        for line, value in [
            ("Airfare \u2013 $450.00", "$450.00"),
            ("Year 2 - $50,000", "$50,000"),
            ("Hotel rates run $400 \u2013 $500 per night", "$500"),
        ]
    ],
    # Call 31, point 4: a date has no sign, so both dates confirm.
    *[
        Probe(
            f"never a sign: date {value}",
            [["Period of performance: 09/01/2025 - 08/31/2027"]],
            "Period of performance: 09/01/2025 - 08/31/2027",
            value,
            "exact",
            True,
        )
        for value in ["09/01/2025", "08/31/2027"]
    ],
    Probe(
        "a dash ending the line after a number, next line a date",
        [["Travel refund 450.00-", "2026-03-04 Lodging 300.00"]],
        "Travel refund 450.00",
        "450.00",
        "exact",
        False,
    ),
    Probe(
        "close, a dash ending the line after a number",
        [["Travel refund for the conference 450.00-", "2026-03-04 Lodging 300.00"]],
        "Travl refund for the conference 450.00",
        "450.00",
        "not_found",
        False,
    ),
    *[
        Probe(
            f"a dash ending the line after a number, next line {next_line!r}",
            [["Travel refund $450.00-", next_line]],
            "Travel refund $450.00",
            "$450.00",
            "exact",
            False,
        )
        for next_line in ["$300.00 Lodging", "(see note 2)", "* adjusted", "# 14", "\u2022 Lodging"]
    ],
    *[
        Probe(
            f"an attached dash after {line.split('$')[0][-2:]!r} is a minus",
            [[line]],
            line,
            "$450.00",
            "exact",
            False,
        )
        for line in [
            'The ledger line reads "-$450.00" for the refund',
            "The ledger line reads '-$450.00' for the refund",
            "Balance=-$450.00 after the refund",
            "Credits;-$450.00 after the refund",
            "Adjustments,-$450.00 after the refund",
            "Item *-$450.00 refund",
        ]
    ],
    *[
        Probe(
            f"a trailing minus before a date-shaped line: {value}",
            [lines],
            lines[0],
            value,
            "exact",
            False,
        )
        for lines, value in [
            (["Refund $12-", "3-15 Fee waived"], "$12"),
            (["Refund 1234-", "05-06 Lodging"], "1234"),
        ]
    ],
    *[
        Probe(
            f"a minus starting the line after a line-end dash, value {value}",
            [["Travel refund 450.00-", "-$12.00 Fee"]],
            "-$12.00 Fee",
            value,
            "exact",
            found,
        )
        for value, found in [("$12.00", False), ("-$12.00", True)]
    ],
    Probe(
        "a date broken at its dash confirms",
        [["Travel dates 2026-", "03-04 to 2026-03-09"]],
        "Travel dates 2026-03-04 to 2026-03-09",
        "2026-03-04",
        "exact",
        True,
    ),
    Probe(
        "a range broken across lines confirms as a whole",
        [["Stay of 10-", "20 days for the field work"]],
        "Stay of 10-20 days for the field work",
        "10-20",
        "exact",
        True,
    ),
    Probe(
        "a negative value where the page's dash is a hyphen",
        [["Hotel rates run $300-$450 per night"]],
        "Hotel rates run $300-$450 per night",
        "-$450",
        "exact",
        False,
    ),
]


@pytest.mark.parametrize("probe", PROBES, ids=[p.name for p in PROBES])
def test_guard(probe: Probe) -> None:
    result = find_pdf_quote(
        _pdf(probe.pages),
        probe.passage,
        start_page_number=1,
        end_page_number=probe.end_page,
        value_text=probe.value,
    )
    assert (result.match, result.value_found) == (probe.expect, probe.value_found), result
    if probe.expect != "not_found":
        assert len(result.occurrences) == 1
        pages = sorted({rect.page_number for rect in result.rects})
        assert pages == list(probe.pages_hit or (1,))
