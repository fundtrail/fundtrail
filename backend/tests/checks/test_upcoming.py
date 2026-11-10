"""upcoming_dates (#165): the dates the checks work out after a grant's "now", for a sample
timeline's "Coming up". The standard grant runs Feb 1, 2023 to Jan 31, 2026, so its closeout
window opens Nov 2, 2025."""

from datetime import date, datetime

from app.checks import UpcomingDate, upcoming_dates
from app.contracts.checks import ChecksInput

from .grant_builder import STIPENDS, TRAVEL, Grant, at


def _input(g: Grant, now: datetime) -> ChecksInput:
    return ChecksInput(
        now=now,
        charges=tuple(c for c in g.charges if c.arrived_at <= now),
        files=tuple(f for f in g.files if f.arrived_at <= now),
        records=tuple(r for r in g.records if r.written_at <= now),
    )


def _kinds(found: list[UpcomingDate]) -> list[tuple[date, str]]:
    return [(u.on, u.kind) for u in found]


def test_the_grants_own_dates_and_a_missing_item_come_up_in_date_order() -> None:
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2024, 2, 28), 10000, posted=date(2024, 3, 1))  # no invoice yet
    g.assign("c1", t["ms"], at(2024, 3, 1))
    found = upcoming_dates(_input(g, at(2024, 3, 2)), "g1")
    assert _kinds(found) == [
        (date(2024, 4, 30), "missing_flagged"),  # 60 days past the posting date
        (date(2025, 11, 2), "closeout_window_opens"),
        (date(2026, 1, 31), "grant_ends"),
    ]
    missing = found[0]
    assert (missing.charge_id, missing.check, missing.problem) == (
        "c1",
        "checklist",
        "missing:bill",
    )


def test_a_missing_item_due_inside_the_window_comes_up_when_the_window_opens() -> None:
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2025, 10, 1), 10000)  # 60 days past is Nov 30, after the window opens
    g.assign("c1", t["ms"], at(2025, 10, 1))
    found = upcoming_dates(_input(g, at(2025, 10, 2)), "g1")
    assert (date(2025, 11, 2), "missing_flagged") in _kinds(found)


def test_a_snooze_comes_up_on_the_day_it_ends() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2024, 3, 1), 10000, at(2024, 3, 1), line=t["ms"])
    g.answer("c1", "unsure", at(2024, 3, 2), question="flag", rule="refund")
    snooze = g.user(
        {
            "kind": "snooze",
            "charge_id": "c1",
            "until": date(2024, 6, 1),
            "note": "Refund coming.",
            "reasons": [{"check": "flag", "problem": "flag:refund"}],
        },
        at(2024, 3, 3),
    )
    found = upcoming_dates(_input(g, at(2024, 3, 4)), "g1")
    (ends,) = [u for u in found if u.kind == "snooze_ends"]
    assert (ends.on, ends.charge_id, ends.record_id) == (date(2024, 6, 1), "c1", snooze)


def test_a_snooze_set_before_the_window_ends_when_the_window_opens() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2025, 9, 1), 10000, at(2025, 9, 1), line=t["ms"])
    g.answer("c1", "unsure", at(2025, 9, 2), question="flag", rule="refund")
    g.user(
        {
            "kind": "snooze",
            "charge_id": "c1",
            "until": date(2025, 12, 31),
            "note": "Refund coming.",
            "reasons": [{"check": "flag", "problem": "flag:refund"}],
        },
        at(2025, 10, 1),
    )
    found = upcoming_dates(_input(g, at(2025, 10, 2)), "g1")
    assert [u.on for u in found if u.kind == "snooze_ends"] == [date(2025, 11, 2)]


def test_only_dates_after_now_come_up_and_a_missing_approval_has_none() -> None:
    g = Grant()
    t = g.standard_terms()
    # A stipend with no approval yet: the approval item is on the list right away.
    g.charge("stip", date(2025, 12, 1), 50000, account=STIPENDS, vendor=None)
    g.assign("stip", t["psc"], at(2025, 12, 1))
    found = upcoming_dates(_input(g, at(2025, 12, 2)), "g1")
    # The window opened on Nov 2, so it's past; every missing item is already flagged.
    assert _kinds(found) == [(date(2026, 1, 31), "grant_ends")]


def test_a_grant_with_no_confirmed_dates_has_nothing_from_its_period() -> None:
    g = Grant()
    g.standard_terms(confirm=False)
    assert upcoming_dates(_input(g, at(2023, 1, 13)), "g1") == []


# From PR 181's review.


def test_a_snooze_naming_a_missing_item_before_its_due_holds_it_back_until_it_ends() -> None:
    """The write check lets a snooze name a reason that isn't on the list yet. The item then
    stays hidden until the snooze ends, so that later date is when it comes up."""
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2024, 2, 28), 10000, posted=date(2024, 3, 1))  # due Apr 30
    g.assign("c1", t["ms"], at(2024, 3, 1))
    g.user(
        {
            "kind": "snooze",
            "charge_id": "c1",
            "until": date(2024, 6, 1),
            "note": "Invoice promised for May.",
            "reasons": [{"check": "checklist", "problem": "missing:bill"}],
        },
        at(2024, 3, 2),
    )
    found = upcoming_dates(_input(g, at(2024, 3, 3)), "g1")
    assert [u.on for u in found if u.kind == "missing_flagged"] == [date(2024, 6, 1)]


def test_a_missing_approval_before_the_window_has_no_date_but_the_other_items_do() -> None:
    g = Grant()
    t = g.standard_terms()  # Participant Support Costs need the Program Officer's approval
    g.charge("stip", date(2024, 6, 1), 50000, account=STIPENDS, vendor=None)
    g.assign("stip", t["psc"], at(2024, 6, 1))
    found = upcoming_dates(_input(g, at(2024, 6, 2)), "g1")
    missing = [(u.check, u.problem) for u in found if u.kind == "missing_flagged"]
    assert ("checklist", "missing:participant_list") in missing
    assert all(check != "approval" for check, _ in missing)  # on the list right away


def test_a_snooze_on_a_bill_says_which_bill() -> None:
    g = Grant()
    g.standard_terms()
    f = g.file("f-inv", at(2024, 3, 1))
    bill = g.bill(10000, f, at(2024, 3, 1))
    g.user(
        {
            "kind": "snooze",
            "record_id": bill,
            "until": date(2024, 6, 1),
            "note": "The charge posts next month.",
            "reasons": [{"check": "bill", "problem": "unused"}],
        },
        at(2024, 3, 2),
    )
    (ends,) = [
        u for u in upcoming_dates(_input(g, at(2024, 3, 3)), "g1") if u.kind == "snooze_ends"
    ]
    assert (ends.on, ends.about_record_id, ends.charge_id) == (date(2024, 6, 1), bill, None)


def _trip_with_one_item_snoozed(until: date, expense_report_due: date | None = None) -> Grant:
    """A travel charge missing its expense report and its bills, both due Apr 30, 2024.
    A snooze names only the bills."""
    g = Grant()
    g.standard_terms()
    g.charge("trip", date(2024, 2, 28), 50000, account=TRAVEL, posted=date(2024, 3, 1))
    g.assign("trip", g.confirmed_line("Travel", "travel", at(2024, 3, 1)), at(2024, 3, 1))
    if expense_report_due is not None:
        # The accountant replaces the default with an item expected later.
        g.user(
            {"kind": "checklist_removal", "charge_id": "trip", "default_item": "expense_report"},
            at(2024, 3, 1),
        )
        g.item(
            "trip", "Expense report", at(2024, 3, 1), author="user", expected_by=expense_report_due
        )
    g.user(
        {
            "kind": "snooze",
            "charge_id": "trip",
            "until": until,
            "note": "Receipts in the mail.",
            "reasons": [{"check": "checklist", "problem": "missing:bills"}],
        },
        at(2024, 3, 2),
    )
    return g


def test_a_covered_item_comes_up_when_an_uncovered_one_on_the_charge_does() -> None:
    """From PR 181's recheck: the expense report isn't snoozed, so on Apr 30 the charge is
    on the list, and the snoozed bills with it."""
    g = _trip_with_one_item_snoozed(until=date(2024, 6, 1))
    found = upcoming_dates(_input(g, at(2024, 3, 3)), "g1")
    flagged = {u.problem: u.on for u in found if u.kind == "missing_flagged"}
    assert flagged == {
        "missing:expense_report": date(2024, 4, 30),
        "missing:bills": date(2024, 4, 30),
    }


def test_a_covered_item_waits_for_the_snooze_when_the_uncovered_one_comes_later() -> None:
    g = _trip_with_one_item_snoozed(until=date(2024, 6, 1), expense_report_due=date(2024, 7, 1))
    found = upcoming_dates(_input(g, at(2024, 3, 3)), "g1")
    flagged = {u.problem: u.on for u in found if u.kind == "missing_flagged"}
    assert flagged["missing:bills"] == date(2024, 6, 1)  # the snooze ends first
    assert flagged["missing:item:expense_report"] == date(2024, 8, 30)


# From PR 193's review.


def test_a_reason_shown_on_its_terms_row_doesnt_end_a_snooze() -> None:
    """The grant's dates aren't confirmed, so the charge has Needs a human reasons that
    the terms' own rows stand for. They never flag the charge, so the snoozed bill waits
    for the snooze to end."""
    g = Grant()
    t = g.standard_terms(confirm=False)
    g.charge("c1", date(2024, 3, 1), 10000)  # the bill is due Apr 30
    g.assign("c1", t["ms"], at(2024, 3, 1))
    g.user(
        {
            "kind": "snooze",
            "charge_id": "c1",
            "until": date(2024, 6, 15),
            "note": "Invoice promised for June.",
            "reasons": [{"check": "checklist", "problem": "missing:bill"}],
        },
        at(2024, 3, 3),
    )
    found = upcoming_dates(_input(g, at(2024, 3, 4)), "g1")
    assert [u.on for u in found if u.kind == "missing_flagged"] == [date(2024, 6, 15)]


def test_two_snoozes_with_different_ends_release_the_charge_when_the_first_ends() -> None:
    """Both items are due Apr 30. One snooze names the participant list until Jun 15, the
    other the payment record until May 15. On May 15 the payment record is on the list and
    no running snooze names it, so the charge is listed with both items."""
    g = Grant()
    t = g.standard_terms(with_rule=False)
    g.charge("stip", date(2024, 3, 1), 50000, account=STIPENDS, vendor=None)
    g.assign("stip", t["psc"], at(2024, 3, 1))
    for until, problem in (
        (date(2024, 6, 15), "missing:participant_list"),
        (date(2024, 5, 15), "missing:payment_record"),
    ):
        g.user(
            {
                "kind": "snooze",
                "charge_id": "stip",
                "until": until,
                "note": "Waiting on the program office.",
                "reasons": [{"check": "checklist", "problem": problem}],
            },
            at(2024, 3, 3),
        )
    found = upcoming_dates(_input(g, at(2024, 3, 4)), "g1")
    flagged = {u.problem: u.on for u in found if u.kind == "missing_flagged"}
    assert flagged == {
        "missing:participant_list": date(2024, 5, 15),
        "missing:payment_record": date(2024, 5, 15),
    }
