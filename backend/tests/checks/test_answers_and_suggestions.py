"""The questions and answers, the agent's flags, waiting suggestions and disputes."""

from datetime import date

from app.contracts.checks import Bucket
from app.contracts.records import Author

from .grant_builder import Grant, at, cited, failing, families


def _charge(g: Grant, t: dict[str, str], cost_date: date = date(2024, 3, 1)) -> str:
    """A supplies charge with its bill linked and assigned, and no answer yet."""
    when = at(cost_date.year, cost_date.month, cost_date.day)
    g.charge("c1", cost_date, 10000)
    f = g.file("f-c1", when)
    b = g.bill(10000, f, when)
    g.link(b, "c1", when, amount=10000, default="bill")
    g.assign("c1", t["ms"], when)
    return b


def test_a_required_question_with_no_answer_is_needs_a_human_and_open_for_the_agent() -> None:
    g = Grant()
    t = g.standard_terms()
    _charge(g, t)
    out = g.run(at(2024, 3, 2))
    status = out.charges[0]
    assert families(status) == {("allowable", "not_answered")}
    assert status.bucket == Bucket.NEEDS_HUMAN
    (q,) = out.questions
    assert (q.charge_id, q.question, q.answer_by) == ("c1", "allowable", Author.AGENT)


def test_answers_map_to_buckets() -> None:
    for answer, bucket in (
        ("supports", Bucket.EVIDENCE_COMPLETE),
        ("contradicts", Bucket.POSSIBLE_CONFLICT),
        ("unsure", Bucket.NEEDS_HUMAN),
    ):
        g = Grant()
        t = g.standard_terms()
        b = _charge(g, t)
        g.answer("c1", answer, at(2024, 3, 1), rests_on=[b])
        assert g.status("c1", at(2024, 3, 2)).bucket == bucket


def test_the_agents_out_of_date_answer_keeps_the_bucket_and_is_rechecked() -> None:
    g = Grant()
    t = g.standard_terms()
    b = _charge(g, t)
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b])
    f = g.file("f-later", at(2024, 3, 5))
    g.link(g.note(f, at(2024, 3, 5)), "c1", at(2024, 3, 5))  # a link written after the answer
    out = g.run(at(2024, 3, 6))
    status = out.charges[0]
    assert status.rechecking
    assert status.bucket == Bucket.EVIDENCE_COMPLETE
    assert [(q.question, q.answer_by) for q in out.questions] == [("allowable", Author.AGENT)]


def test_the_accountants_out_of_date_answer_goes_back_to_the_accountant() -> None:
    g = Grant()
    t = g.standard_terms()
    b = _charge(g, t)
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b], author="user")
    f = g.file("f-later", at(2024, 3, 5))
    g.link(g.note(f, at(2024, 3, 5)), "c1", at(2024, 3, 5))
    out = g.run(at(2024, 3, 6))
    status = out.charges[0]
    assert families(status) == {("allowable", "out_of_date")}
    assert status.bucket == Bucket.NEEDS_HUMAN
    assert not status.rechecking
    assert [(q.question, q.answer_by) for q in out.questions] == [("allowable", Author.USER)]


def test_a_correction_to_a_record_the_answer_rests_on_makes_it_out_of_date() -> None:
    g = Grant()
    t = g.standard_terms()
    b = _charge(g, t)
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b])
    fixed = g.bill(10000, "f-c1", at(2024, 3, 2))
    g.records[-1] = g.records[-1].model_copy(update={"replaces_id": b})
    g.confirm(fixed, when=at(2024, 3, 3))
    assert g.status("c1", at(2024, 3, 4)).rechecking


def test_the_latest_current_answer_counts() -> None:
    g = Grant()
    t = g.standard_terms()
    b = _charge(g, t)
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b], author="user")
    g.answer("c1", "contradicts", at(2024, 3, 2), rests_on=[b], author="user")
    assert g.status("c1", at(2024, 3, 3)).bucket == Bucket.POSSIBLE_CONFLICT


def test_an_unusual_term_in_force_on_the_charges_date_is_asked_about() -> None:
    g = Grant()
    t = g.standard_terms()
    b = _charge(g, t)
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b])
    leave = g.agent(
        {
            "kind": "other_term",
            "dated": cited(date(2024, 1, 1)),
            "label": "PI on leave",
            "statement": cited("The PI is on leave from January 2024."),
        },
        at(2024, 3, 2),
    )
    assert g.status("c1", at(2024, 3, 3)).bucket == Bucket.EVIDENCE_COMPLETE  # not confirmed yet
    g.confirm(leave, when=at(2024, 3, 4))
    out = g.run(at(2024, 3, 5))
    assert ("unusual_term", "not_answered") in families(out.charges[0])
    assert [(q.question, q.record_id) for q in out.questions] == [("unusual_term", leave)]


def test_the_agents_flag_is_needs_a_human_until_the_accountant_settles_it() -> None:
    g = Grant()
    t = g.standard_terms()
    b = _charge(g, t)
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b])
    flag = g.answer("c1", "unsure", at(2024, 3, 1), question="flag", rule="close-to-end-date")
    status = g.status("c1", at(2024, 3, 2))
    assert families(status) == {("flag", "flag:close-to-end-date")}
    assert status.bucket == Bucket.NEEDS_HUMAN

    # The agent withdrawing its own flag waits.
    g.agent({"kind": "retraction"}, at(2024, 3, 3), replaces=flag)
    status = g.status("c1", at(2024, 3, 4))
    assert {p for p in families(status) if p[0] == "suggestion"}
    assert ("flag", "flag:close-to-end-date") in families(status)

    g.answer("c1", "supports", at(2024, 3, 5), question="flag", author="user", replaces=flag)
    assert g.status("c1", at(2024, 3, 6)).bucket == Bucket.EVIDENCE_COMPLETE


def test_a_waiting_link_fix_keeps_the_charge_with_the_accountant_and_the_old_link_in_force() -> (
    None
):
    g = Grant()
    t = g.standard_terms()
    b = _charge(g, t)
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b])
    old = next(r.id for r in g.records if r.kind == "link")
    fix = g.link(b, "c1", at(2024, 3, 2), amount=9000, default="bill", replaces=old)
    status = g.status("c1", at(2024, 3, 3))
    assert families(status) == {("suggestion", f"waiting:{fix}")}
    assert status.bucket == Bucket.NEEDS_HUMAN
    assert status.checklist[0].filled  # the old link stays in force
    assert (
        failing(status)[0].text == "The agent suggests a fix to a link, waiting for the accountant."
    )


def _after_end(g: Grant, t: dict[str, str]) -> str:
    b = _charge(g, t, cost_date=date(2026, 2, 20))
    g.answer("c1", "supports", at(2026, 2, 20), rests_on=[b])
    return g.agent(
        {
            "kind": "dispute",
            "charge_id": "c1",
            "check": "period_of_performance",
            "reasoning": "The order was placed before the end date.",
            "quotes": [cited(0, "Ordered January 20, 2026", "f-c1")["citation"]],
        },
        at(2026, 2, 21),
    )


def test_a_waiting_dispute_turns_the_disputed_reason_into_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms()
    dispute = _after_end(g, t)
    status = g.status("c1", at(2026, 2, 22))
    reason = next(r for r in status.reasons if r.check == "period_of_performance")
    assert reason.bucket == Bucket.NEEDS_HUMAN
    assert dispute in reason.record_ids
    assert reason.dispute_id == dispute
    assert status.bucket == Bucket.NEEDS_HUMAN


def test_a_confirmed_dispute_accepts_the_reason_and_a_rejected_one_puts_it_back() -> None:
    g = Grant()
    t = g.standard_terms()
    dispute = _after_end(g, t)
    g.confirm(dispute, when=at(2026, 2, 23))
    status = g.status("c1", at(2026, 2, 24))
    assert status.bucket == Bucket.POSSIBLE_CONFLICT  # keeps the bucket the checks gave it
    assert status.accepted and not status.flagged
    assert (
        next(r for r in status.reasons if r.check == "period_of_performance").accepted_by == dispute
    )

    g2 = Grant()
    t2 = g2.standard_terms()
    dispute2 = _after_end(g2, t2)
    g2.confirm(dispute2, when=at(2026, 2, 23), decision="rejected")
    status = g2.status("c1", at(2026, 2, 24))
    assert status.bucket == Bucket.POSSIBLE_CONFLICT
    assert status.flagged and not status.accepted


def test_an_answer_resting_on_a_term_not_yet_confirmed_is_needs_a_human_not_out_of_date() -> None:
    g = Grant()
    t = g.standard_terms()
    b = _charge(g, t)
    leave = g.agent(
        {
            "kind": "other_term",
            "dated": cited(date(2024, 1, 1)),
            "label": "PI on leave",
            "statement": cited("The PI is on leave from January 2024."),
        },
        at(2024, 3, 1),
    )
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b, leave])
    status = g.status("c1", at(2024, 3, 2))
    assert not status.rechecking
    assert families(status) == {("values_confirmed", "term_not_confirmed")}
    g.confirm(leave, when=at(2024, 3, 3))
    status = g.status("c1", at(2024, 3, 4))
    assert ("values_confirmed", "term_not_confirmed") not in families(status)
    assert not status.rechecking


def test_two_current_links_between_one_bill_and_one_charge_both_count() -> None:
    """Until "one link in force" is decided, every current link counts in section 2's sums."""
    g = Grant()
    t = g.standard_terms()
    b = _charge(g, t)
    g.answer("c1", "supports", at(2024, 3, 1), rests_on=[b])
    g.link(b, "c1", at(2024, 3, 2), amount=10000, default="bill", author="user")
    out = g.run(at(2024, 3, 3))
    status = out.charges[0]
    assert ("checklist", "over:bill") in families(status)
    assert ("checklist", "bill_over_linked") in families(status)
    assert status.bucket == Bucket.NEEDS_HUMAN
    assert {p.problem for r in out.records for p in r.problems} == {"over_linked"}


# From a screens review: the accountant's answer, given while the agent's waits or is
# being rechecked, is the one in force.


def test_the_accountants_answer_counts_while_the_agents_is_being_rechecked() -> None:
    g = Grant()
    t = g.standard_terms()
    b = _charge(g, t)
    g.answer("c1", "unsure", at(2024, 3, 1), rests_on=[b])
    f = g.file("f-later", at(2024, 3, 5))
    g.link(g.note(f, at(2024, 3, 5)), "c1", at(2024, 3, 5))  # the agent's answer is out of date
    assert g.status("c1", at(2024, 3, 5, 13)).rechecking
    theirs = g.answer("c1", "supports", at(2024, 3, 6), author="user")
    out = g.run(at(2024, 3, 7))
    status = out.charges[0]
    allowable = next(r for r in status.reasons if r.check == "allowable")
    assert (allowable.problem, allowable.record_ids[0]) == ("supports", theirs)
    assert not status.rechecking
    assert out.questions == ()
    assert status.bucket == Bucket.EVIDENCE_COMPLETE


def test_the_accountants_answer_counts_while_the_agents_new_answer_waits() -> None:
    g = Grant()
    t = g.standard_terms()
    b = _charge(g, t)
    g.answer("c1", "contradicts", at(2024, 3, 1), rests_on=[b])
    waiting = g.answer("c1", "supports", at(2024, 3, 2), rests_on=[b])  # milder: it waits
    theirs = g.answer("c1", "unsure", at(2024, 3, 3), author="user")
    status = g.status("c1", at(2024, 3, 4))
    allowable = next(r for r in status.reasons if r.check == "allowable")
    assert (allowable.problem, allowable.record_ids[0]) == ("unsure", theirs)
    assert waiting not in allowable.record_ids
