"""Problems on records, files and the grant itself, the budget check, and grant notes."""

from datetime import UTC, date, datetime

from app.contracts.checks import Bucket, ChecksOutput
from app.contracts.runs import AgentRun, RunStatus, Trigger, TriggerKind

from .grant_builder import Grant, at, problems


def record_problems(out: ChecksOutput) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for r in out.records:
        found.setdefault(r.record_id or r.file_id or "", set()).update(
            p.problem for p in r.problems
        )
    return found


def grant_problems(out: ChecksOutput) -> set[str]:
    return {p.problem for g in out.grants for p in g.problems}


def test_a_bill_linked_for_more_than_its_total_is_a_problem_and_needs_a_human_on_each_charge() -> (
    None
):
    g = Grant()
    t = g.standard_terms()
    f = g.file("f-inv", at(2024, 3, 1))
    b = g.bill(10000, f, at(2024, 3, 1))
    for cid in ("c1", "c2"):
        g.charge(cid, date(2024, 3, 1), 6000)
        g.link(b, cid, at(2024, 3, 1), amount=6000, default="bill")
        g.assign(cid, t["ms"], at(2024, 3, 1))
        g.answer(cid, "supports", at(2024, 3, 1), rests_on=[b])
    out = g.run(at(2024, 3, 2))
    assert record_problems(out) == {b: {"over_linked"}}
    assert out.records[0].flagged
    for status in out.charges:
        assert problems(status) == {("checklist", "bill_over_linked")}
        assert status.bucket == Bucket.NEEDS_HUMAN


def test_a_bill_with_money_nobody_charged_is_a_problem_60_days_after_it_arrived() -> None:
    g = Grant()
    g.standard_terms()
    f = g.file("f-inv", at(2024, 3, 1, 9))
    b = g.bill(10000, f, at(2024, 3, 1, 9))
    assert record_problems(g.run(at(2024, 4, 29, 12))) == {}
    out = g.run(at(2024, 4, 30, 12))
    assert record_problems(out) == {b: {"unused"}}
    assert out.records[0].problems[0].text.startswith("$100.00 of this bill's $100.00 isn't linked")


def test_terms_waiting_for_the_accountant_are_problems_until_confirmed() -> None:
    g = Grant()
    t = g.standard_terms(confirm=False)
    out = g.run(at(2023, 1, 13))
    assert set(record_problems(out)) == set(t.values())
    assert all(r.flagged for r in out.records)
    assert grant_problems(out) == {"no_dates", "no_budget"}
    g.confirm(*t.values(), when=at(2023, 1, 13, 13))
    out = g.run(at(2023, 1, 14))
    assert out.records == () and out.grants == ()


def test_the_exact_same_file_twice_is_a_problem_on_the_later_copy() -> None:
    g = Grant()
    g.standard_terms()
    g.file("f-a", at(2024, 3, 1), sha="same")
    g.file("f-b", at(2024, 3, 2), sha="same")
    assert record_problems(g.run(at(2024, 3, 3))) == {"f-b": {"same_file"}}


def test_the_agents_flag_on_a_file_is_a_problem_until_the_accountant_settles_it() -> None:
    g = Grant()
    g.standard_terms()
    f = g.file("f-blurry", at(2024, 3, 1))
    flag = g.answer(None, "unsure", at(2024, 3, 1), question="flag", file_id=f, rule="unreadable")
    assert record_problems(g.run(at(2024, 3, 2))) == {f: {"flag:unreadable"}}
    g.answer(
        None, "supports", at(2024, 3, 3), question="flag", file_id=f, author="user", replaces=flag
    )
    assert record_problems(g.run(at(2024, 3, 4))) == {}


def test_an_accepted_record_problem_leaves_the_list() -> None:
    g = Grant()
    g.standard_terms()
    g.file("f-a", at(2024, 3, 1), sha="same")
    g.file("f-b", at(2024, 3, 2), sha="same")
    g.user(
        {
            "kind": "accepted_reason",
            "file_id": "f-b",
            "reason": {"check": "same_file", "problem": "same_file"},
            "note": "Sent twice by the vendor.",
        },
        at(2024, 3, 3),
    )
    (status,) = g.run(at(2024, 3, 4)).records
    assert status.accepted and not status.flagged


def _failed(trigger: Trigger) -> AgentRun:
    t = datetime(2024, 3, 1, tzinfo=UTC)
    return AgentRun(
        id="run-1",
        workspace_id="w",
        grant_id="g1",
        trigger=trigger,
        status=RunStatus.FAILED,
        clock_now=t,
        queued_at=t,
    )


def test_a_run_that_failed_for_good_raises_a_problem_on_its_file_or_charge() -> None:
    g = Grant()
    t = g.standard_terms()
    g.file("f-x", at(2024, 3, 1))
    g.failed_runs = [_failed(Trigger(kind=TriggerKind.FILE, id="f-x"))]
    assert record_problems(g.run(at(2024, 3, 2))) == {"f-x": {"failed:run-1"}}

    g.supplies_charge("c1", date(2024, 3, 1), 10000, at(2024, 3, 1), line=t["ms"])
    g.failed_runs = [_failed(Trigger(kind=TriggerKind.CHARGE, id="c1"))]
    status = g.status("c1", at(2024, 3, 2))
    assert problems(status) == {("agent_run", "failed:run-1")}
    assert failing_text(status) == ["The agent couldn't finish reading this."]


def failing_text(status) -> list[str]:  # type: ignore[no-untyped-def]
    return [r.text for r in status.reasons if r.bucket != Bucket.EVIDENCE_COMPLETE]


# The grant itself.


def test_spending_over_the_awards_limit_is_a_problem_on_the_grant() -> None:
    g = Grant()
    t = g.standard_terms()  # $120,000 obligated to date
    g.supplies_charge("c1", date(2024, 3, 1), 12_000_001, at(2024, 3, 1), line=t["ms"])
    out = g.run(at(2024, 3, 2))
    assert grant_problems(out) == {"over_limit"}
    (status,) = out.grants
    assert status.flagged
    assert status.problems[0].text == (
        "Spending of $120,000.01 is over the award's limit of $120,000.00, "
        "the total obligated to date on amendment 000."
    )


def test_a_notice_that_adds_money_raises_the_limit_once_confirmed() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2024, 3, 1), 13_000_000, at(2024, 3, 1), line=t["ms"])
    inc = g.notice("001", 5_000_000, 17_000_000, at(2024, 3, 2), dated=date(2024, 3, 1))
    assert "over_limit" in grant_problems(g.run(at(2024, 3, 3)))
    g.confirm(inc, when=at(2024, 3, 3, 13))
    assert "over_limit" not in grant_problems(g.run(at(2024, 3, 4)))


def test_a_funding_notice_whose_totals_dont_add_up_or_that_skips_a_number_is_a_problem() -> None:
    g = Grant()
    g.standard_terms()
    bad = g.notice("001", 5_000_000, 18_000_000, at(2024, 3, 2), dated=date(2024, 3, 1))
    skip = g.notice("003", 1_000_000, 19_000_000, at(2024, 3, 2), dated=date(2024, 6, 1))
    g.confirm(bad, skip, when=at(2024, 3, 3))
    found = grant_problems(g.run(at(2024, 3, 4)))
    assert found == {"totals:001", "amendment_skipped:002"}


def test_an_overspent_budget_line_is_a_note_not_a_problem() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2024, 3, 1), 4_200_000, at(2024, 3, 1), line=t["ms"])
    out = g.run(at(2024, 3, 2))
    assert out.grants == ()
    assert [n.text for n in out.notes] == ["Materials and Supplies: $42,000.00 of $40,000.00"]
