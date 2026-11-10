"""Accepted reasons, reusable notes and their three limits, snoozes, and flag timing."""

from datetime import date
from typing import Any

from app.contracts.checks import Bucket

from .grant_builder import RECHARGE, SALARY, Grant, at, failing


def accept(
    g: Grant, charge_id: str, check: str, problem: str, rests_on: list[str], **kw: Any
) -> str:
    when = kw.pop("when", at(2025, 6, 1))
    return g.user(
        {
            "kind": "accepted_reason",
            "charge_id": charge_id,
            "reason": {"check": check, "problem": problem},
            "note": kw.pop("note", "Refunded in March."),
            "rests_on": rests_on,
            **kw,
        },
        when,
    )


def snooze(g: Grant, charge_id: str, until: date, reasons: list[tuple[str, str]], when: Any) -> str:
    return g.user(
        {
            "kind": "snooze",
            "charge_id": charge_id,
            "until": until,
            "note": "Refund coming.",
            "reasons": [{"check": c, "problem": p} for c, p in reasons],
        },
        when,
    )


# Accepting a reason.


def _late(g: Grant, t: dict[str, str]) -> None:
    g.supplies_charge("c1", date(2026, 2, 20), 10000, at(2026, 2, 20), line=t["ms"])


def test_an_accepted_charge_keeps_its_bucket_shows_accepted_and_leaves_the_list() -> None:
    g = Grant()
    t = g.standard_terms()
    _late(g, t)
    ok = accept(
        g, "c1", "period_of_performance", "after_end_date", [t["period"]], when=at(2026, 2, 21)
    )
    status = g.status("c1", at(2026, 2, 22))
    assert status.bucket == Bucket.POSSIBLE_CONFLICT
    assert status.accepted and not status.flagged
    assert failing(status)[0].accepted_by == ok


def test_an_acceptance_covers_the_problem_as_it_stood() -> None:
    g = Grant()
    t = g.standard_terms()
    _late(g, t)
    accept(g, "c1", "period_of_performance", "after_end_date", [t["period"]], when=at(2026, 2, 21))
    # An extension that still ends before the cost: the reason now rests on a new term.
    ext = g.period(None, date(2026, 2, 1), date(2026, 1, 15), at(2026, 2, 23))
    g.confirm(ext, when=at(2026, 2, 23, 13))
    status = g.status("c1", at(2026, 2, 24))
    assert not status.accepted and status.flagged


def test_reopening_an_acceptance_is_a_retraction() -> None:
    g = Grant()
    t = g.standard_terms()
    _late(g, t)
    ok = accept(
        g, "c1", "period_of_performance", "after_end_date", [t["period"]], when=at(2026, 2, 21)
    )
    g.user({"kind": "retraction"}, at(2026, 2, 22), replaces=ok)
    assert g.status("c1", at(2026, 2, 23)).flagged


# Reusable notes: a $400 monthly facility fee with no usage statement.

FEE = "missing:usage_statement"


def _fee(
    g: Grant, id: str, posted: date, amount: int = 40000, vendor: str | None = "Example Facility"
) -> str:
    g.charge(id, posted, amount, account=RECHARGE, vendor=vendor)
    other = next(r.id for r in g.records if r.kind == "budget_line" and "Other" == _name(r))
    g.assign(id, other, at(posted.year, posted.month, posted.day))
    return id


def _name(r: Any) -> str:
    return r.data.name.value


def _with_note(reusable: bool = True) -> tuple[Grant, str]:
    g = Grant()
    g.standard_terms()
    _fee(g, "mar", date(2024, 3, 1))
    note = accept(g, "mar", "checklist", FEE, [], reusable=reusable, when=at(2024, 3, 10))
    return g, note


NOW = at(2024, 12, 1)  # long past the 60 days, before the closeout window


def test_a_reusable_note_applies_on_its_own_inside_its_limits() -> None:
    g, note = _with_note()
    _fee(g, "apr", date(2024, 4, 1))
    status = g.status("apr", NOW)
    reason = next(r for r in failing(status) if r.problem == FEE)
    assert reason.accepted_by == note
    assert status.accepted and not status.flagged
    assert (
        status.bucket == Bucket.MISSING_EVIDENCE
    )  # every other check still runs; the bucket stays


def test_outside_the_vendor_or_amount_limit_the_note_is_offered() -> None:
    g, note = _with_note()
    _fee(g, "jun", date(2024, 6, 1), amount=42000)
    _fee(g, "big", date(2024, 7, 1), amount=4_000_000)
    _fee(g, "renamed", date(2024, 8, 1), vendor="Example Facility Services")
    _fee(g, "novendor", date(2024, 9, 1), vendor=None)
    for cid in ("jun", "big", "renamed", "novendor"):
        status = g.status(cid, NOW)
        reason = next(r for r in failing(status) if r.problem == FEE)
        assert (reason.accepted_by, reason.offered_note_id) == (None, note), cid
        assert status.flagged


def test_accepting_the_offer_for_similar_charges_raises_the_limit_and_just_this_one_doesnt() -> (
    None
):
    g, note = _with_note()
    _fee(g, "jun", date(2024, 6, 1), amount=42000)
    accept(g, "jun", "checklist", FEE, [], reuses_id=note, reusable=False, when=at(2024, 7, 1))
    _fee(g, "jul", date(2024, 7, 2), amount=41000)
    assert g.status("jul", NOW).flagged  # just this charge left the limit at $400

    g, note = _with_note()
    _fee(g, "jun", date(2024, 6, 1), amount=42000)
    accept(g, "jun", "checklist", FEE, [], reuses_id=note, reusable=True, when=at(2024, 7, 1))
    _fee(g, "jul", date(2024, 7, 2), amount=41000)
    status = g.status("jul", NOW)
    assert status.accepted and not status.flagged


def test_a_one_off_note_is_never_reused() -> None:
    g, _ = _with_note(reusable=False)
    _fee(g, "apr", date(2024, 4, 1))
    reason = next(r for r in failing(g.status("apr", NOW)) if r.problem == FEE)
    assert (reason.accepted_by, reason.offered_note_id) == (None, None)


def test_withdrawing_a_reusable_note_brings_its_charges_back() -> None:
    g, note = _with_note()
    _fee(g, "apr", date(2024, 4, 1))
    g.user({"kind": "retraction"}, at(2024, 11, 1), replaces=note)
    assert g.status("apr", NOW).flagged


# Snoozes.


def test_a_snooze_hides_the_charge_until_its_date_and_keeps_the_bucket() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2024, 3, 1), 10000, at(2024, 3, 1), line=t["ms"])
    g.answer("c1", "unsure", at(2024, 3, 2), question="flag", rule="refund")
    snooze(g, "c1", date(2024, 4, 1), [("flag", "flag:refund")], at(2024, 3, 3))
    status = g.status("c1", at(2024, 3, 31))
    assert status.snoozed and not status.flagged
    assert status.bucket == Bucket.NEEDS_HUMAN
    status = g.status("c1", at(2024, 4, 1))
    assert not status.snoozed and status.flagged


def test_a_new_problem_ends_a_snooze_early() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2024, 3, 1), 10000, at(2024, 3, 1), line=t["ms"])
    g.answer("c1", "unsure", at(2024, 3, 2), question="flag", rule="refund")
    snooze(g, "c1", date(2024, 6, 1), [("flag", "flag:refund")], at(2024, 3, 3))
    g.answer("c1", "unsure", at(2024, 3, 4), question="flag", rule="duplicate")
    status = g.status("c1", at(2024, 3, 5))
    assert not status.snoozed and status.flagged


def test_every_snooze_ends_when_the_closeout_window_opens() -> None:
    # The grant ends Jan 31, 2026, so the window opens Nov 2, 2025.
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2025, 9, 1), 10000, at(2025, 9, 1), line=t["ms"])
    g.answer("c1", "unsure", at(2025, 9, 2), question="flag", rule="refund")
    snooze(g, "c1", date(2025, 12, 31), [("flag", "flag:refund")], at(2025, 10, 1))
    assert g.status("c1", at(2025, 11, 1)).snoozed
    assert not g.status("c1", at(2025, 11, 2)).snoozed


def test_inside_the_window_a_snooze_lasts_up_to_the_end_date() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2025, 11, 10), 10000, at(2025, 11, 10), line=t["ms"])
    g.answer("c1", "unsure", at(2025, 11, 11), question="flag", rule="refund")
    snooze(g, "c1", date(2026, 3, 1), [("flag", "flag:refund")], at(2025, 11, 12))
    assert g.status("c1", at(2026, 1, 31)).snoozed
    assert not g.status("c1", at(2026, 2, 1)).snoozed


# When missing evidence goes on the list.


def test_missing_evidence_is_flagged_60_days_past_the_posting_date() -> None:
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2024, 2, 27), 10000, posted=date(2024, 3, 1))
    g.assign("c1", t["ms"], at(2024, 3, 1))
    assert g.status("c1", at(2024, 3, 1)).bucket == Bucket.MISSING_EVIDENCE
    assert not g.status("c1", at(2024, 4, 29)).flagged
    assert g.status("c1", at(2024, 4, 30)).flagged


def test_inside_the_closeout_window_every_missing_item_is_flagged_with_its_expected_date() -> None:
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2025, 12, 1), 10000)
    g.assign("c1", t["ms"], at(2025, 12, 1))
    status = g.status("c1", at(2025, 12, 1, 13))
    assert status.flagged
    assert failing(status)[0].expected_by == date(2025, 12, 1)


def test_an_item_that_says_when_its_expected_isnt_late_before_then() -> None:
    g = Grant()
    g.standard_terms()
    g.charge("sal", date(2024, 1, 31), 600000, account=SALARY, vendor=None)
    line = g.confirmed_line("Other Personnel", "other_personnel", at(2024, 1, 31))
    g.assign("sal", line, at(2024, 1, 31))
    f = g.file("f-letter-2", at(2024, 1, 31))
    g.link(g.note(f, at(2024, 1, 31)), "sal", at(2024, 1, 31), default="appointment_letter")
    g.answer("sal", "supports", at(2024, 1, 31))
    status = g.status("sal", at(2024, 12, 26))
    (reason,) = failing(status)
    assert (reason.problem, reason.expected_by) == ("missing:effort_report", date(2024, 10, 28))
    assert not status.flagged
    assert g.status("sal", at(2024, 12, 27)).flagged
