"""Issue 307: every reason on one subject has its own check:problem code, so the screens can
key them apart and accepting one reason with a note accepts only that one."""

from datetime import date

from app.checks import run_checks
from app.contracts.checks import ChecksInput, ChecksOutput
from app.contracts.fixtures import load_sample_grant

from .grant_builder import Grant, at, cited


def _term(g: Grant, label: str) -> str:
    term = g.agent(
        {
            "kind": "other_term",
            "dated": cited(date(2024, 1, 1)),
            "label": label,
            "statement": cited(f"{label} applies from January 2024."),
        },
        at(2024, 2, 1),
    )
    g.confirm(term, when=at(2024, 2, 2))
    return term


def _two_terms_answered() -> tuple[Grant, str, str, str]:
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2024, 3, 1), 10000)
    f = g.file("f1", at(2024, 3, 1))
    b = g.bill(10000, f, at(2024, 3, 1))
    g.link(b, "c1", at(2024, 3, 1), amount=10000, default="bill")
    g.assign("c1", t["ms"], at(2024, 3, 1))
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b])
    leave, travel = _term(g, "PI on leave"), _term(g, "No foreign travel")
    for term in (leave, travel):
        g.answer("c1", "unsure", at(2024, 3, 2), question="unusual_term", record_id=term)
    return g, b, leave, travel


def _codes(out: ChecksOutput) -> list[tuple[str, str]]:
    return [(r.check, r.problem) for s in out.charges for r in s.reasons]


def test_two_unusual_terms_on_one_charge_have_their_own_codes() -> None:
    g, _, leave, travel = _two_terms_answered()
    codes = _codes(g.run(at(2024, 3, 3)))
    assert len(codes) == len(set(codes))
    assert ("unusual_term", f"unsure:{leave}") in codes
    assert ("unusual_term", f"unsure:{travel}") in codes


def test_unanswered_terms_have_their_own_codes_too() -> None:
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2024, 3, 1), 10000)
    g.assign("c1", t["ms"], at(2024, 3, 1))
    leave, travel = _term(g, "PI on leave"), _term(g, "No foreign travel")
    codes = _codes(g.run(at(2024, 3, 3)))
    assert len(codes) == len(set(codes))
    expected = {("unusual_term", f"not_answered:{t}") for t in (leave, travel)}
    assert expected <= set(codes)


def test_accepting_one_terms_reason_leaves_the_other_open() -> None:
    g, _, leave, travel = _two_terms_answered()
    status = g.status("c1", at(2024, 3, 3))
    reason = next(r for r in status.reasons if r.problem == f"unsure:{leave}")
    g.user(
        {
            "kind": "accepted_reason",
            "charge_id": "c1",
            "reason": {"check": "unusual_term", "problem": reason.problem},
            "note": "Leave doesn't affect supplies.",
            "rests_on": list(reason.record_ids),
        },
        at(2024, 3, 4),
    )
    status = g.status("c1", at(2024, 3, 5))
    by_code = {r.problem: r for r in status.reasons}
    assert by_code[f"unsure:{leave}"].accepted_by is not None
    assert by_code[f"unsure:{travel}"].accepted_by is None


def test_an_acceptance_stored_under_the_old_code_still_covers_its_own_reason() -> None:
    """Before issue 307 the code was just the answer ("unsure"). An acceptance stored that
    way still covers the reason it was written for: the one whose records it rested on."""
    g, _, leave, travel = _two_terms_answered()
    status = g.status("c1", at(2024, 3, 3))
    reason = next(r for r in status.reasons if r.problem == f"unsure:{leave}")
    g.user(
        {
            "kind": "accepted_reason",
            "charge_id": "c1",
            "reason": {"check": "unusual_term", "problem": "unsure"},
            "note": "Leave doesn't affect supplies.",
            "rests_on": list(reason.record_ids),
        },
        at(2024, 3, 4),
    )
    by_code = {r.problem: r for r in g.status("c1", at(2024, 3, 5)).reasons}
    assert by_code[f"unsure:{leave}"].accepted_by is not None
    assert by_code[f"unsure:{travel}"].accepted_by is None


def test_no_subject_in_the_sample_has_two_reasons_with_one_code() -> None:
    """The audit as a test: on the golden sample at each record's moment, every charge,
    record, file and the grant have at most one reason or problem per code."""
    s = load_sample_grant()
    for now in sorted({r.written_at for r in s.records}):
        out = run_checks(
            ChecksInput(
                now=now,
                charges=tuple(c for c in s.charges if c.arrived_at <= now),
                files=tuple(f for f in s.files if f.arrived_at <= now),
                records=tuple(r for r in s.records if r.written_at <= now),
            )
        )
        lists = [[(r.check, r.problem) for r in c.reasons] for c in out.charges]
        lists += [[(p.check, p.problem) for p in r.problems] for r in out.records]
        lists += [[(p.check, p.problem) for p in g.problems] for g in out.grants]
        for codes in lists:
            assert len(codes) == len(set(codes)), (now, codes)
