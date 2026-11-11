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


def _scan_charge(g: Grant, t: dict[str, str], cid: str, day: int) -> None:
    """A charge whose bill total couldn't be found in its file (values: unconfirmed)."""
    g.charge(cid, date(2024, 3, day), 10000)
    f = g.file(f"f-{cid}", at(2024, 3, day))
    b = g.bill(10000, f, at(2024, 3, day), match="not_found")
    g.link(b, cid, at(2024, 3, day), amount=10000, default="bill")
    g.assign(cid, t["ms"], at(2024, 3, day))
    g.answer(cid, "supports", at(2024, 3, day), rests_on=[b])


def _values_reason(g: Grant, cid: str, day: int):
    status = g.status(cid, at(2024, 3, day))
    return next(r for r in status.reasons if r.check == "values_confirmed")


def test_a_reusable_note_still_reaches_a_later_charges_reason_of_its_family() -> None:
    """#315's review: a keyed code names one charge's record, so a reusable note matches a
    later charge's reason by family, as it did before issue 307."""
    for stored in ("new", "old"):
        g = Grant()
        t = g.standard_terms()
        _scan_charge(g, t, "c1", 1)
        first = _values_reason(g, "c1", 2)
        g.user(
            {
                "kind": "accepted_reason",
                "charge_id": "c1",
                "reason": {
                    "check": first.check,
                    "problem": first.problem if stored == "new" else "unconfirmed",
                },
                "note": "This supplier's scans never read.",
                "rests_on": list(first.record_ids),
                "reusable": True,
            },
            at(2024, 3, 3),
        )
        _scan_charge(g, t, "c2", 4)
        later = _values_reason(g, "c2", 5)
        assert later.problem != first.problem  # about another bill
        assert later.accepted_by is not None or later.offered_note_id is not None, stored


def test_a_colon_less_code_names_only_issue_307s_families() -> None:
    """An acceptance of ("approval", "missing") must not accept "missing:approval:{rule}":
    only issue 307's keyed families match a code stored without its key."""
    from app.checks.codes import same_code

    assert same_code("unusual_term", "unsure", "unusual_term", "unsure:r15")
    assert same_code("approval", "wrong_approver", "approval", "wrong_approver:r17")
    assert not same_code("approval", "missing", "approval", "missing:approval:rule-1")
    assert not same_code("checklist", "missing", "checklist", "missing:bill")
    assert not same_code("flag", "flag", "flag", "flag:refund")


def test_two_current_flags_with_one_rule_have_their_own_codes() -> None:
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2024, 3, 1), 10000)
    f = g.file("f1", at(2024, 3, 1))
    b = g.bill(10000, f, at(2024, 3, 1))
    g.link(b, "c1", at(2024, 3, 1), amount=10000, default="bill")
    g.assign("c1", t["ms"], at(2024, 3, 1))
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b])
    g.answer("c1", "unsure", at(2024, 3, 1), question="flag", rule="refund")
    g.answer("c1", "unsure", at(2024, 3, 2), question="flag", rule="refund")
    codes = [r.problem for r in g.status("c1", at(2024, 3, 3)).reasons if r.check == "flag"]
    assert len(codes) == 2 == len(set(codes))
    assert "flag:refund" in codes  # the first keeps its code, so its acceptances still match


def test_one_approval_filling_two_items_is_one_reason_per_code() -> None:
    from .test_charge_checks import _stipend

    g = Grant()
    t = g.standard_terms()
    _stipend(g, t)
    f = g.file("f1", at(2024, 6, 3))
    a = g.approval(f, at(2024, 6, 3), on=date(2024, 7, 1))
    item = g.item("stip", "Sponsor approval", at(2024, 6, 3), nsf_standing_list="x")
    g.link(a, "stip", at(2024, 6, 3), default=f"approval:{t['rule']}")
    g.link(a, "stip", at(2024, 6, 3), item=item)
    codes = [(r.check, r.problem) for r in g.status("stip", at(2024, 6, 4)).reasons]
    assert len(codes) == len(set(codes))
    assert any(p.startswith("approval_late:") for c, p in codes if c == "approval")


def _two_flags() -> tuple[Grant, str, str]:
    g = Grant()
    t = g.standard_terms()
    g.charge("c1", date(2024, 3, 1), 10000)
    f = g.file("f1", at(2024, 3, 1))
    b = g.bill(10000, f, at(2024, 3, 1))
    g.link(b, "c1", at(2024, 3, 1), amount=10000, default="bill")
    g.assign("c1", t["ms"], at(2024, 3, 1))
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b])
    f1 = g.answer("c1", "unsure", at(2024, 3, 1), question="flag", rule="refund")
    f2 = g.answer("c1", "unsure", at(2024, 3, 2), question="flag", rule="refund")
    return g, f1, f2


def _flag_codes(g: Grant, day: int) -> dict[str, str]:
    """Each flag's code, by the root of the flag it belongs to."""
    status = g.status("c1", at(2024, 3, day))
    return {r.record_ids[0]: r.problem for r in status.reasons if r.check == "flag"}


def test_a_flags_code_never_moves_when_another_flag_is_answered_or_withdrawn() -> None:
    g, f1, f2 = _two_flags()
    assert _flag_codes(g, 3) == {f1: "flag:refund", f2: f"flag:refund:{f2}"}
    # The accountant answers flag 1: flag 2 keeps its own code.
    answer = g.answer("c1", "unsure", at(2024, 3, 4), question="flag", author="user", replaces=f1)
    codes = _flag_codes(g, 5)
    assert codes[f2] == f"flag:refund:{f2}" and codes[answer] == "flag:refund"
    # The agent withdraws flag 2 and the accountant confirms: flag 1's code stays too.
    g2, a1, a2 = _two_flags()
    retraction = g2.agent({"kind": "retraction"}, at(2024, 3, 4), replaces=a1)
    g2.confirm(retraction, when=at(2024, 3, 4, 13))
    assert _flag_codes(g2, 5) == {a2: f"flag:refund:{a2}"}


def test_a_snooze_or_acceptance_of_one_flag_stays_with_that_flag() -> None:
    from datetime import date as d

    g, f1, f2 = _two_flags()
    g.user(
        {
            "kind": "accepted_reason",
            "charge_id": "c1",
            "reason": {"check": "flag", "problem": f"flag:refund:{f2}"},
            "note": "The refund is expected.",
            "rests_on": [f2],
        },
        at(2024, 3, 3),
    )
    g.user(
        {
            "kind": "snooze",
            "charge_id": "c1",
            "until": d(2024, 9, 1),
            "note": "Waiting on the vendor.",
            "reasons": [{"check": "flag", "problem": "flag:refund"}],
        },
        at(2024, 3, 3),
    )
    g.answer("c1", "unsure", at(2024, 3, 4), question="flag", author="user", replaces=f1)
    status = g.status("c1", at(2024, 3, 5))
    second = next(r for r in status.reasons if r.problem == f"flag:refund:{f2}")
    assert second.accepted_by is not None


def test_a_reusable_note_on_a_second_flag_reaches_a_later_charges_flag() -> None:
    from app.checks.codes import same_family

    assert same_family("flag", "flag:refund:r16", "flag", "flag:refund")
    assert same_family("flag", "flag:refund", "flag", "flag:refund:r40")
    assert not same_family("flag", "flag:refund", "flag", "flag:late")
