"""Ties at the same clock time go by stored order (call 36, rulings 3 and 4).

The demo clock stands still between moves, so a note, a ledger line and a file can all
carry the same time. Then the order they were stored in decides, never their IDs.
"""

from datetime import date, datetime

from app.contracts.checks import ChecksOutput

from .grant_builder import RECHARGE, Grant, at, failing

FEE = "missing:usage_statement"
FROZEN = at(2024, 3, 10, 0)  # a ledger line posted Mar 10 arrives at 00:00 that day


def _fee(g: Grant, t: dict[str, str], id: str, posted: date) -> None:
    g.charge(id, posted, 40000, account=RECHARGE, vendor="Example Facility")
    g.assign(id, t["other"], datetime(posted.year, posted.month, posted.day, tzinfo=FROZEN.tzinfo))


def _note(g: Grant) -> str:
    return g.user(
        {
            "kind": "accepted_reason",
            "charge_id": "mar",
            "reason": {"check": "checklist", "problem": FEE},
            "note": "The facility sends no statement.",
            "reusable": True,
        },
        FROZEN,
    )


def _reason(out: ChecksOutput, charge_id: str):  # type: ignore[no-untyped-def]
    status = next(c for c in out.charges if c.charge_id == charge_id)
    return next(r for r in failing(status) if r.problem == FEE)


def test_a_reusable_note_covers_a_charge_stored_after_it_at_the_same_time() -> None:
    """Ruling 3: a note written at a frozen "now" covers a ledger uploaded after it then."""
    g = Grant(stored=True)
    t = g.standard_terms()
    _fee(g, t, "mar", date(2024, 3, 1))
    note = _note(g)
    _fee(g, t, "apr", date(2024, 3, 10))  # arrives at FROZEN, stored after the note
    assert _reason(g.run(at(2024, 12, 1)), "apr").accepted_by == note


def test_a_reusable_note_doesnt_cover_a_charge_stored_before_it_at_the_same_time() -> None:
    g = Grant(stored=True)
    t = g.standard_terms()
    _fee(g, t, "mar", date(2024, 3, 1))
    _fee(g, t, "apr", date(2024, 3, 10))  # arrives at FROZEN, stored before the note
    _note(g)
    reason = _reason(g.run(at(2024, 12, 1)), "apr")
    assert (reason.accepted_by, reason.offered_note_id) == (None, None)


def test_identical_files_at_the_same_time_go_by_stored_order_not_id() -> None:
    """Ruling 4: the first stored is the original, whatever the IDs say."""
    g = Grant(stored=True)
    g.standard_terms()
    g.file("f-z", at(2024, 3, 1), sha="same")  # stored first
    g.file("f-a", at(2024, 3, 1), sha="same")  # stored second, with the smaller ID
    out = g.run(at(2024, 3, 2))
    assert [(r.file_id, r.problems[0].problem) for r in out.records] == [("f-a", "same_file")]
    assert "f-z.txt" in out.records[0].problems[0].text
