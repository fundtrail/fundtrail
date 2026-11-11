"""Ruling 73: an item with an amount that the linked bills only partly cover says so, in
words only. It stays not filled, and the charge's bucket doesn't change."""

from datetime import date

from app.contracts.checks import Bucket

from .grant_builder import Grant, at


def _status(linked: int | None, charge: int = 67600):
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2024, 3, 1), charge)
    if linked is not None:
        f = g.file("f1", at(2024, 3, 1))
        b = g.bill(linked, f, at(2024, 3, 1))  # the whole bill, so no part needs a basis
        g.link(b, "c1", at(2024, 3, 1), amount=linked, default="bill")
        g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b])
    g.assign("c1", t["ms"], at(2024, 3, 1))
    return g.status("c1", at(2024, 3, 2))


def test_an_item_the_bills_partly_cover_says_how_much() -> None:
    status = _status(25000)
    [entry] = status.checklist
    assert not entry.filled
    assert entry.covered_cents == 25000
    assert entry.partly_filled_text == "Partly filled, $250.00 of $676.00"
    assert status.bucket == Bucket.MISSING_EVIDENCE  # the same bucket as before


def test_a_filled_an_empty_or_an_over_item_isnt_partly_filled() -> None:
    for linked in (67600, None, 70000):
        [entry] = _status(linked).checklist
        assert entry.covered_cents is None and entry.partly_filled_text is None
