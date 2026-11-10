"""Problems on records, files and the grant itself, the budget check, and grant notes."""

from datetime import UTC, date, datetime

from app.contracts.checks import Bucket, ChecksOutput
from app.contracts.runs import AgentRun, RunStatus, Trigger, TriggerKind

from .grant_builder import STIPENDS, Grant, at, problems


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
    assert grant_problems(out) == set()  # the waiting terms are their own rows
    g.confirm(*t.values(), when=at(2023, 1, 13, 13))
    out = g.run(at(2023, 1, 14))
    assert out.records == () and out.grants == ()


def test_a_grant_with_no_dates_or_budget_at_all_is_a_problem_on_the_grant() -> None:
    g = Grant()  # only the award letter's file, no terms read yet
    out = g.run(at(2023, 1, 13))
    assert grant_problems(out) == {"no_dates", "no_budget"}
    assert out.grants[0].flagged


def test_a_charge_whose_only_problem_is_a_waiting_term_isnt_its_own_row() -> None:
    g = Grant()
    t = g.standard_terms(confirm=False)
    g.supplies_charge("c1", date(2023, 5, 1), 10000, at(2023, 5, 1), line=t["ms"])
    status = g.status("c1", at(2023, 5, 2))
    assert status.bucket == Bucket.NEEDS_HUMAN
    assert {r.problem for r in status.reasons if r.bucket != Bucket.EVIDENCE_COMPLETE} == {
        "not_confirmed",
        "line_not_confirmed",
    }
    assert not status.flagged  # the waiting terms' rows stand for it


def test_a_rule_code_cant_place_is_a_problem_on_its_record_too() -> None:
    g = Grant()
    t = g.standard_terms(with_rule=False)
    rule = g.approval_rule("Field safety gear", "Grants Officer", None, at(2023, 1, 12, 15))
    g.confirm(rule, when=at(2023, 1, 12, 17))
    g.supplies_charge("c1", date(2024, 5, 1), 10000, at(2024, 5, 1), line=t["ms"])
    out = g.run(at(2024, 5, 2))
    assert record_problems(out) == {rule: {"rule_unmatched"}}
    status = out.charges[0]
    assert status.bucket == Bucket.NEEDS_HUMAN
    assert not status.flagged  # the rule's row stands for it


def test_failed_runs_go_where_their_trigger_points() -> None:
    g = Grant()
    t = g.standard_terms()
    g.failed_runs = [
        _failed(Trigger(kind=TriggerKind.RECORD, id=t["confirm"])),
        _failed(Trigger(kind=TriggerKind.CLOCK)).model_copy(update={"id": "run-2"}),
    ]
    out = g.run(at(2024, 3, 2))
    assert record_problems(out) == {t["confirm"]: {"failed:run-1"}}
    assert grant_problems(out) == {"failed:run-2"}


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


def _failed(
    trigger: Trigger,
    run_id: str = "run-1",
    thread_charge_id: str | None = None,
    thread_record_id: str | None = None,
) -> AgentRun:
    t = datetime(2024, 3, 1, tzinfo=UTC)
    return AgentRun(
        id=run_id,
        workspace_id="w",
        grant_id="g1",
        trigger=trigger,
        status=RunStatus.FAILED,
        clock_now=t,
        queued_at=t,
        thread_charge_id=thread_charge_id,
        thread_record_id=thread_record_id,
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


def _stipend_overspend(g: Grant, line: str) -> list[str]:
    g.charge("stip", date(2024, 3, 1), 2_500_000, account=STIPENDS, vendor=None)
    g.assign("stip", line, at(2024, 3, 1))
    return [n.text for n in g.run(at(2024, 3, 2)).notes]


def test_a_parent_line_and_its_sub_lines_count_the_budget_once() -> None:
    """PSC $20,000 printed with Stipends $15,000 and Travel $5,000; $25,000 spent on stipends."""
    g = Grant()
    g.standard_terms()  # prints Participant Support Costs, $20,000
    when = at(2023, 1, 12, 15)
    stipends = g.budget_line("Stipends", 1_500_000, "participant_support", when)
    travel = g.budget_line("Travel", 500_000, "participant_support", when)
    g.confirm(stipends, travel, when=at(2023, 1, 12, 17))
    assert _stipend_overspend(g, stipends) == [
        "Participant Support Costs: $25,000.00 of $20,000.00"
    ]


def test_two_notices_add_up_even_when_they_share_a_date() -> None:
    """Lines belong to the notice whose file they're read from, not to a date."""
    g = Grant()
    g.standard_terms()  # the award letter: Participant Support Costs, $20,000
    g.file("f-increment", at(2023, 6, 1))
    more = g.budget_line(
        "Participant Support Costs",
        1_000_000,
        "participant_support",
        at(2023, 6, 1),
        dated=date(2023, 1, 10),  # the same date as the award letter
        f="f-increment",
    )
    g.confirm(more, when=at(2023, 6, 1, 13))
    assert _stipend_overspend(g, more) == []  # $25,000 of $30,000 isn't overspent
    g.charge("stip2", date(2024, 3, 2), 600_000, account=STIPENDS, vendor=None)
    g.assign("stip2", more, at(2024, 3, 2))
    assert [n.text for n in g.run(at(2024, 3, 3)).notes] == [
        "Participant Support Costs: $31,000.00 of $30,000.00"
    ]


def test_a_notice_that_prints_only_sub_lines_sums_them() -> None:
    g = Grant()
    when = at(2023, 1, 12, 15)
    stipends = g.budget_line("Stipends", 1_500_000, "participant_support", when)
    travel = g.budget_line("Travel", 500_000, "participant_support", when)
    g.confirm(stipends, travel, when=at(2023, 1, 12, 17))
    assert _stipend_overspend(g, stipends) == [
        "Participant Support Costs: $25,000.00 of $20,000.00"
    ]


def test_a_failed_thread_message_run_goes_on_its_threads_charge_or_record() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2024, 3, 1), 10000, at(2024, 3, 1), line=t["ms"])
    message = Trigger(kind=TriggerKind.THREAD_MESSAGE, id="msg-1")
    g.failed_runs = [
        _failed(message, "run-1", thread_charge_id="c1"),
        _failed(message, "run-2", thread_record_id=t["period"]),
    ]
    out = g.run(at(2024, 3, 2))
    assert out.grants == ()
    status = out.charges[0]
    assert problems(status) == {("agent_run", "failed:run-1")}
    assert status.bucket == Bucket.NEEDS_HUMAN and status.flagged
    assert record_problems(out) == {t["period"]: {"failed:run-2"}}


def test_a_failed_open_question_run_goes_on_the_charge_whose_question_is_open() -> None:
    g = Grant()
    t = g.standard_terms()
    g.supplies_charge("c1", date(2024, 3, 1), 10000, at(2024, 3, 1), line=t["ms"])
    g.failed_runs = [_failed(Trigger(kind=TriggerKind.OPEN_QUESTION, id="c1"))]
    out = g.run(at(2024, 3, 2))
    assert problems(out.charges[0]) == {("agent_run", "failed:run-1")}
    assert out.records == () and out.grants == ()
