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
    # Accepting it would net the line it names, so that line shows it too.
    assert ("suggestion", f"waiting:{suggestion}") in problems(_status(g, "orig"))


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


# From PR 155's review.


def test_more_taken_off_than_was_charged_is_needs_a_human() -> None:
    """A $400 charge and a -$500 credit naming it: the net is -$100."""
    g = Grant()
    t = g.standard_terms()
    invoice = _original(g, t)
    _correct(g, t, "cr", -50000, "L-orig")
    f = g.file("f-memo", at(2024, 4, 1))
    memo = g.bill(-50000, f, at(2024, 4, 1))
    g.link(memo, "orig", at(2024, 4, 1), amount=-50000, default="bill")
    g.answer("orig", "supports", at(2024, 4, 1), rests_on=[invoice, memo])
    status = _status(g, "orig")
    assert (status.net_cents, status.reversed) == (-10000, False)
    # The invoice and the memo add up to the -$100 net, but it's never complete.
    assert problems(status) == {("checklist", "over_corrected")}
    assert status.bucket == Bucket.NEEDS_HUMAN
    reason = failing(status)[0]
    assert reason.text == (
        "The lines correcting this charge (L-cr) take off $500.00, more than its $400.00."
    )


def test_two_full_reversals_of_one_charge_are_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms()
    _original(g, t)
    _correct(g, t, "rev1", -40000, "L-orig")
    _correct(g, t, "rev2", -40000, "L-orig")
    status = _status(g, "orig")
    assert (status.net_cents, status.reversed) == (-40000, False)
    assert ("checklist", "over_corrected") in problems(status)
    assert status.bucket == Bucket.NEEDS_HUMAN


def test_a_correction_naming_a_line_on_another_fund_fills_the_item_and_nets_nothing() -> None:
    """Decision 0020: the paperwork is the only way for a line this grant can't see."""
    g = Grant()
    t = g.standard_terms()
    _correct(g, t, "out", -40000, None)
    g.user(
        {
            "kind": "correction",
            "charge_id": "out",
            "corrects_line_id": "OTHER-FUND-77",
            "reason": "The transfer form names line OTHER-FUND-77 on another fund.",
        },
        at(2024, 4, 1),
    )
    status = _status(g, "out")
    entries = {e.default_item: e.filled for e in status.checklist}
    assert entries == {"corrected_line": True, "justification": False}
    assert (status.net_cents, status.reversed) == (None, False)


def test_a_reversal_frees_only_its_own_part_of_a_bill() -> None:
    """A $1,000 invoice linked $400 to the reversed charge and $300 to another: $300 is
    still money nobody charged."""
    g = Grant()
    t = g.standard_terms()
    g.charge("orig", POSTED, 40000)
    g.charge("b", POSTED, 30000)
    f = g.file("f-inv", at(2024, 3, 1))
    invoice = g.bill(100000, f, at(2024, 3, 1))
    for cid, amount in (("orig", 40000), ("b", 30000)):
        g.link(invoice, cid, at(2024, 3, 1), amount=amount, default="bill")
        g.assign(cid, t["ms"], at(2024, 3, 1))
    _correct(g, t, "rev", -40000, "L-orig")
    out = g.run(at(2024, 7, 1))  # well past 60 days
    (problem,) = next(r for r in out.records if r.record_id == invoice).problems
    assert problem.problem == "unused"
    assert problem.text.startswith("$300.00 of this bill's $1,000.00 isn't linked")


def test_a_line_that_names_the_reversal_cancels_it() -> None:
    """Call 42 (provisional, likely to change): orig +$400 with its invoice, rev -$400
    naming it, rerev +$400 naming rev. rerev cancels the reversal: orig counts in full
    again with its bills where they are, and rerev gets only the two correction items."""
    g = Grant()
    t = g.standard_terms()
    _original(g, t)
    _correct(g, t, "rev", -40000, "L-orig")
    _correct(g, t, "rerev", 40000, "L-rev")
    orig = _status(g, "orig")
    assert (orig.net_cents, orig.reversed) == (40000, False)
    assert failing(orig) == []  # its invoice still fills it
    rerev = _status(g, "rerev")
    assert [(e.default_item, e.amount_cents, e.filled) for e in rerev.checklist] == [
        ("corrected_line", None, True),
        ("justification", None, False),
    ]
    assert problems(rerev) == {("checklist", "missing:justification")}


def test_a_line_that_adds_money_and_names_the_original_is_a_re_post() -> None:
    """A re-post stands alone (decision 0020): its own bills, plus the two items. The
    original stays reversed. This is how a move between two accounts on the same grant
    comes out: the old line is reversed, and the new line carries the cost."""
    g = Grant()
    t = g.standard_terms()
    _original(g, t)
    _correct(g, t, "rev", -40000, "L-orig")
    _correct(g, t, "repost", 40000, "L-orig")
    assert _status(g, "orig").reversed
    repost = _status(g, "repost")
    assert [(e.default_item, e.amount_cents) for e in repost.checklist] == [
        ("bill", 40000),
        ("corrected_line", None),
        ("justification", None),
    ]
    assert repost.net_cents is None


def test_a_line_that_adds_money_and_names_nothing_stands_alone() -> None:
    g = Grant()
    t = g.standard_terms()
    _original(g, t)
    _correct(g, t, "rev", -40000, "L-orig")
    _correct(g, t, "new", 40000, None)
    new = _status(g, "new")
    assert [e.default_item for e in new.checklist] == ["bill"]
