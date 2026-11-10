"""upcoming_dates (#165): the dates the checks work out after a grant's "now", for a sample
timeline's "Coming up". The standard grant runs Feb 1, 2023 to Jan 31, 2026, so its closeout
window opens Nov 2, 2025."""

from datetime import date, datetime

from app.checks import UpcomingDate, upcoming_dates
from app.contracts.checks import ChecksInput

from .grant_builder import STIPENDS, Grant, at


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
