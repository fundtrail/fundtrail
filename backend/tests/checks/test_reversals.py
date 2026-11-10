"""Decision 0020 (#78): a charge netted with the lines that correct it, the Reversed state,
the checklist judged on the net, the corrected line filled, and bills freed by a reversal."""

from datetime import date, datetime

from app.contracts.checks import Bucket, ChargeStatus

from .grant_builder import Grant, at, cited, failing, problems

POSTED = date(2024, 3, 1)
AFTER = at(2024, 4, 2)


def _original(g: Grant, t: dict[str, str]) -> str:
    """L-orig: $400 of supplies, with its invoice linked and answered."""
    return g.supplies_charge("orig", POSTED, 40000, at(2024, 3, 1), line=t["ms"])


def _correct(g: Grant, t: dict[str, str], id: str, amount: int, names: str | None) -> None:
    g.charge(id, date(2024, 4, 1), amount, original_line_id=names)
    g.assign(id, t["ms"], at(2024, 4, 1))


def _status(g: Grant, charge_id: str, when: datetime = AFTER) -> ChargeStatus:
    return g.status(charge_id, when)


def test_a_full_reversal_shows_the_original_as_reversed_and_off_the_list() -> None:
    g = Grant()
    t = g.standard_terms()
    _original(g, t)
    before = _status(g, "orig", at(2024, 3, 2))
    assert (before.net_cents, before.reversed, before.corrections) == (None, False, ())

    _correct(g, t, "rev", -40000, "L-orig")
    status = _status(g, "orig")
    assert (status.net_cents, status.reversed, status.corrections) == (0, True, ("rev",))
    assert not status.flagged
    assert status.bucket == before.bucket  # it keeps the bucket the checks give it


def test_a_reversed_charge_is_off_the_list_even_with_a_problem() -> None:
    g = Grant()
    t = g.standard_terms()
    g.charge("orig", date(2026, 2, 20), 40000)  # after the end date, no invoice
    g.assign("orig", t["ms"], at(2026, 2, 20))
    assert _status(g, "orig", at(2026, 2, 21)).flagged
    _correct(g, t, "rev", -40000, "L-orig")
    status = _status(g, "orig", at(2026, 4, 2))
    assert status.bucket == Bucket.POSSIBLE_CONFLICT and status.reversed
    assert not status.flagged
    # Its sums are no longer checked: the bill item is missing, but no amount is compared.
    assert not any(r.problem.startswith(("over:", "items_")) for r in failing(status))


def test_the_correcting_line_has_its_corrected_line_filled_by_the_ledger() -> None:
    g = Grant()
    t = g.standard_terms()
    _original(g, t)
    _correct(g, t, "rev", -40000, "L-orig")
    status = _status(g, "rev")
    entries = {e.default_item: e.filled for e in status.checklist}
    assert entries == {"corrected_line": True, "justification": False}
    assert problems(status) == {("checklist", "missing:justification")}


def test_a_line_named_but_not_on_the_grant_leaves_the_corrected_line_unfilled() -> None:
    g = Grant()
    t = g.standard_terms()
    _correct(g, t, "rev", -40000, "L-elsewhere")
    status = _status(g, "rev")
    assert ("checklist", "missing:corrected_line") in problems(status)
    assert status.net_cents is None and not status.reversed


def test_a_partly_corrected_charge_is_judged_on_its_net_amount() -> None:
    """A $400 charge and a -$150 credit naming it: the checklist adds up to $250."""
    g = Grant()
    t = g.standard_terms()
    invoice = _original(g, t)
    _correct(g, t, "cr", -15000, "L-orig")
    status = _status(g, "orig")
    assert (status.net_cents, status.reversed) == (25000, False)
    bill = next(e for e in status.checklist if e.default_item == "bill")
    assert bill.amount_cents == 25000
    assert ("checklist", "over:bill") in problems(status)  # the $400 invoice alone is over

    f = g.file("f-memo", at(2024, 4, 1))
    memo = g.bill(-15000, f, at(2024, 4, 1))
    g.link(memo, "orig", at(2024, 4, 1), amount=-15000, default="bill")
    g.answer("orig", "supports", at(2024, 4, 1), rests_on=[invoice, memo])
    status = _status(g, "orig")
    assert next(e for e in status.checklist if e.default_item == "bill").filled
    assert failing(status) == []


def test_a_correction_record_names_the_line_when_the_ledger_doesnt() -> None:
    g = Grant()
    t = g.standard_terms()
    _original(g, t)
    _correct(g, t, "rev", -40000, None)
    assert not _status(g, "orig").reversed

    data = {
        "kind": "correction",
        "charge_id": "rev",
        "corrects_line_id": "L-orig",
        "reason": "The transfer form names L-orig.",
    }
    g.user(data, at(2024, 4, 1))
    assert _status(g, "orig").reversed
    entries = {e.default_item: e.filled for e in _status(g, "rev").checklist}
    assert entries["corrected_line"]


def test_the_agents_correction_waits_and_nothing_nets_meanwhile() -> None:
    g = Grant()
    t = g.standard_terms()
    _original(g, t)
    _correct(g, t, "rev", -40000, None)
    f = g.file("f-transfer", at(2024, 4, 1))
    suggestion = g.agent(
        {
            "kind": "correction",
            "charge_id": "rev",
            "corrects_line_id": "L-orig",
            "reason": "The transfer form names L-orig.",
            "quotes": [cited(0, "Original line: L-orig", f)["citation"]],
        },
        at(2024, 4, 1),
    )
    assert not _status(g, "orig").reversed
    assert ("suggestion", f"waiting:{suggestion}") in problems(_status(g, "rev"))


def test_a_reversed_reversal_counts_the_original_in_full_again() -> None:
    g = Grant()
    t = g.standard_terms()
    _original(g, t)
    _correct(g, t, "rev", -40000, "L-orig")
    _correct(g, t, "rerev", 40000, "L-rev")
    status = _status(g, "orig")
    assert (status.net_cents, status.reversed) == (40000, False)


def test_a_bill_linked_to_a_fully_reversed_charge_is_free_again() -> None:
    g = Grant()
    t = g.standard_terms()
    invoice = _original(g, t)
    _correct(g, t, "rev", -40000, "L-orig")
    # The cost moves to a new line; the same invoice is linked to it in full.
    g.charge("new", date(2024, 4, 1), 40000)
    g.assign("new", t["ms"], at(2024, 4, 1))
    g.link(invoice, "new", at(2024, 4, 1), amount=40000, default="bill", author="user")
    out = g.run(at(2024, 7, 1))  # well past 60 days
    assert all(r.record_id != invoice for r in out.records)  # not over-linked, not unused
    new = next(c for c in out.charges if c.charge_id == "new")
    assert ("checklist", "bill_over_linked") not in problems(new)


def test_a_bill_freed_by_a_reversal_and_linked_nowhere_else_isnt_unused() -> None:
    g = Grant()
    t = g.standard_terms()
    invoice = _original(g, t)
    _correct(g, t, "rev", -40000, "L-orig")
    out = g.run(at(2024, 7, 1))
    assert all(r.record_id != invoice for r in out.records)
