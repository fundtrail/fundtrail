"""The functions other areas call (issue 106): budget figures, reusable-note coverage, and the
award limit's problem ID."""

from datetime import date

from app.checks import (
    BUDGET,
    OVER_LIMIT,
    Coverage,
    budget_figures,
    note_covers,
    note_limit,
)
from app.contracts.records import OVER_LIMIT_CHECK, OVER_LIMIT_PROBLEM, BudgetCategory

from .grant_builder import RECHARGE, Grant, at

# Budget figures.


def test_budget_figures_give_each_line_and_category_as_the_notes_compute_them() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2024, 3, 1), 4_200_000, at(2024, 3, 1), line=t["ms"])
    visible = [r for r in g.records if r.written_at <= at(2024, 3, 2)]
    figures = budget_figures("g1", visible, g.charges)

    lines = {f.record_id: (f.name, f.amount_cents, f.spent_cents) for f in figures.lines}
    assert lines[t["ms"]] == ("Materials and Supplies", 4_000_000, 4_200_000)
    assert lines[t["odc"]] == ("Other Direct Costs", 10_000_000, 0)  # nothing assigned to it

    by_category = {f.category: f for f in figures.categories}
    ms = by_category[BudgetCategory.MATERIALS_AND_SUPPLIES]
    assert (ms.name, ms.budget_cents, ms.spent_cents, ms.overspent) == (
        "Materials and Supplies",
        4_000_000,
        4_200_000,
        True,
    )
    odc = by_category[BudgetCategory.OTHER_DIRECT_COSTS]
    # A sub-line's spending counts on Other Direct Costs too.
    assert (odc.budget_cents, odc.spent_cents, odc.overspent) == (10_000_000, 4_200_000, False)

    notes = [n.text for n in g.run(at(2024, 3, 2)).notes]
    assert notes == [
        f"{f.name}: $42,000.00 of $40,000.00" for f in figures.categories if f.overspent
    ]


def test_budget_figures_give_the_award_limit_and_total_spending() -> None:
    g = Grant()
    t = g.standard_terms()  # $120,000 obligated to date on amendment 000
    g.supplies_charge("c1", date(2024, 3, 1), 4_200_000, at(2024, 3, 1), line=t["ms"])
    g.charge("c2", date(2024, 3, 2), 100_000)  # no budget line assigned yet
    figures = budget_figures("g1", g.records, g.charges)
    assert (figures.limit_cents, figures.limit_notice_id) == (12_000_000, t["notice"])
    assert figures.spent_cents == 4_300_000  # every charge, as the limit compares
    assert budget_figures("g1", [], []).limit_cents is None


def test_budget_figures_count_a_parent_and_its_sub_lines_once() -> None:
    g = Grant()
    g.standard_terms()  # Participant Support Costs, $20,000
    when = at(2023, 1, 12, 15)
    stipends = g.budget_line("Stipends", 1_500_000, "participant_support", when)
    travel = g.budget_line("Travel", 500_000, "participant_support", when)
    g.confirm(stipends, travel, when=at(2023, 1, 12, 17))
    figures = budget_figures("g1", g.records, g.charges)
    psc = next(f for f in figures.categories if f.category == BudgetCategory.PARTICIPANT_SUPPORT)
    assert psc.budget_cents == 2_000_000


# Reusable-note coverage.

FEE = "missing:usage_statement"
NOW = at(2024, 12, 1)


def _fee(g: Grant, id: str, posted: date, amount: int = 40000, vendor: str = "Example Facility"):  # type: ignore[no-untyped-def]
    return g.charge(id, posted, amount, account=RECHARGE, vendor=vendor)


def _note(g: Grant) -> str:
    _fee(g, "mar", date(2024, 3, 1))
    return g.user(
        {
            "kind": "accepted_reason",
            "charge_id": "mar",
            "reason": {"check": "checklist", "problem": FEE},
            "note": "The facility sends no statement.",
            "reusable": True,
        },
        at(2024, 3, 10),
    )


def test_note_covers_says_covered_offered_or_nothing() -> None:
    g = Grant()
    g.standard_terms()
    note = _note(g)
    _fee(g, "apr", date(2024, 4, 1))
    _fee(g, "jun", date(2024, 6, 1), amount=42000)
    charges = {c.id: c for c in g.charges}

    def covers(charge_id: str, problem: str = FEE) -> Coverage | None:
        return note_covers(
            note, charges[charge_id], "checklist", problem, g.records, g.charges, NOW
        )

    assert covers("apr") == Coverage.COVERED
    assert covers("jun") == Coverage.OFFERED  # over the amount limit
    assert covers("apr", problem="missing:other") is None
    assert covers("mar") is None  # the note's own charge
    assert note_covers("nope", charges["apr"], "checklist", FEE, g.records, g.charges, NOW) is None


def test_note_limit_rises_when_the_offer_is_accepted_for_similar_charges() -> None:
    g = Grant()
    g.standard_terms()
    note = _note(g)
    assert note_limit(note, g.records, g.charges, NOW) == 40000
    _fee(g, "jun", date(2024, 6, 1), amount=42000)
    g.user(
        {
            "kind": "accepted_reason",
            "charge_id": "jun",
            "reason": {"check": "checklist", "problem": FEE},
            "note": "The facility sends no statement.",
            "reusable": True,
            "reuses_id": note,
        },
        at(2024, 7, 1),
    )
    assert note_limit(note, g.records, g.charges, NOW) == 42000
    assert note_limit("nope", g.records, g.charges, NOW) is None


# The award limit's problem ID.


def test_the_award_limit_problem_uses_the_exported_ids() -> None:
    assert (BUDGET, OVER_LIMIT) == (OVER_LIMIT_CHECK, OVER_LIMIT_PROBLEM)
    g = Grant()
    t = g.standard_terms()  # $120,000 obligated to date
    g.supplies_charge("c1", date(2024, 3, 1), 12_100_000, at(2024, 3, 1), line=t["ms"])
    (status,) = g.run(at(2024, 3, 2)).grants
    (problem,) = status.problems
    assert (problem.check, problem.problem) == (BUDGET, OVER_LIMIT)
