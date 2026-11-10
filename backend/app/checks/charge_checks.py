"""Every reason on one charge: the checks about a charge, the answers and flags, the waiting
suggestions and disputes, the budget line against the ledger account, and failed runs.

Acceptances, reusable notes, snoozes and flagging are applied afterwards (decisions.py).
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.checks import checklist as checklist_check
from app.checks.answers import ANSWER_BUCKET, AnswerState, answer_state
from app.checks.checklist import compare
from app.checks.findings import (
    AGENT_RUN,
    APPROVAL,
    BUDGET_LINE,
    CHECKLIST,
    PERIOD,
    SUGGESTION,
    VALUES,
    Finding,
    passed,
)
from app.checks.ledger_accounts import categories, category_name
from app.checks.rules_match import rules_for
from app.checks.text import day, money, norm
from app.checks.view import GrantView, LinkInForce
from app.contracts.charges import Charge
from app.contracts.checks import Bucket, ChecklistEntry, OpenQuestion
from app.contracts.records import (
    TERM_KINDS,
    Answer,
    Approval,
    ApprovalRule,
    Author,
    Bill,
    BudgetLine,
    Dispute,
    Duplicate,
    Judgment,
    Note,
    OtherTerm,
    Question,
    Record,
    RecordKind,
    categories_match,
)
from app.contracts.runs import AgentRun, TriggerKind

QUESTION_LABELS = {
    Question.ALLOWABLE: "Allowable",
}


@dataclass
class ChargeEval:
    findings: list[Finding]
    entries: list[ChecklistEntry]
    questions: list[OpenQuestion] = field(default_factory=list[OpenQuestion])
    rechecking: bool = False


def describe(record: Record) -> str:
    data = record.data
    if isinstance(data, Bill):
        number = f" {data.document_number.value}" if data.document_number else ""
        return f"The bill{number}"
    if isinstance(data, Approval):
        return f"The approval from {data.approver_email.value}"
    if isinstance(data, Note):
        return f"The note '{data.label}'"
    return f"The {record.kind.value.replace('_', ' ')}"


def _questions(
    charge: Charge, view: GrantView, approvals: list[Record], ask_covers: bool
) -> list[AnswerState]:
    states: list[AnswerState] = []
    if view.links[charge.id]:
        states.append(
            answer_state(
                view, charge.id, Question.ALLOWABLE, None, QUESTION_LABELS[Question.ALLOWABLE]
            )
        )
    if ask_covers:
        for a in approvals:
            label = f"Covers, for {describe(a).lower()}"
            states.append(answer_state(view, charge.id, Question.COVERS, a.id, label))
    for term in view.other_terms_on(charge.transaction_date):
        assert isinstance(term.data, OtherTerm)
        label = f"Unusual term '{term.data.label}'"
        states.append(answer_state(view, charge.id, Question.UNUSUAL_TERM, term.id, label))
    return states


def _date_check(charge: Charge, view: GrantView, covers: list[AnswerState]) -> Finding:
    p = view.period
    if p is None:
        waiting = [r.id for r in view.waiting_terms if r.kind == RecordKind.PERIOD_OF_PERFORMANCE]
        text = (
            "The grant's dates aren't confirmed yet."
            if waiting
            else "The grant has no dates on file yet."
        )
        # The waiting terms' own rows, or the grant's "no dates" row, stand for it.
        return Finding(
            PERIOD, "not_confirmed", Bucket.NEEDS_HUMAN, text, waiting, shown_on_term=True
        )
    if p.disagree:
        return Finding(
            PERIOD,
            "terms_disagree",
            Bucket.NEEDS_HUMAN,
            "The grant's confirmed terms give different dates, so code can't tell the period "
            "in force.",
            p.disagree,
            shown_on_term=True,
        )
    if p.start is None:
        return Finding(
            PERIOD,
            "start_not_confirmed",
            Bucket.NEEDS_HUMAN,
            "The grant's start date isn't confirmed yet.",
            p.record_ids,
        )
    d = charge.transaction_date
    ids = list(p.record_ids)
    if d > p.end:
        return Finding(
            PERIOD,
            "after_end_date",
            Bucket.POSSIBLE_CONFLICT,
            f"Dated {day(d)}, after the grant's end date, {day(p.end)}.",
            ids,
        )
    if d >= p.start:
        return passed(
            PERIOD,
            f"Dated {day(d)}, inside the grant's period, {day(p.start)} to {day(p.end)}.",
            ids,
        )
    if d >= p.start - timedelta(days=checklist_check.PRE_AWARD_DAYS):
        return passed(
            PERIOD,
            f"Dated {day(d)}, within 90 days before the start date, {day(p.start)}. "
            "The checklist asks for the university's own pre-award approval.",
            ids,
        )
    approved = [s.record_id for s in covers if s.record_id and s.counts_as(Answer.SUPPORTS)]
    if approved:
        return passed(
            PERIOD,
            f"Dated {day(d)}, more than 90 days before the start date, {day(p.start)}, "
            "with NSF's approval on file.",
            ids + [a for a in approved if a],
        )
    return Finding(
        PERIOD,
        "before_start",
        Bucket.POSSIBLE_CONFLICT,
        f"Dated {day(d)}, more than 90 days before the start date, {day(p.start)}, "
        "with no NSF approval on file.",
        ids,
    )


# The NSF officials an award notice names (domain.md, "What an NSF award notice
# contains"). An NSF standing-list approval has to come from one of them.
_NSF_OFFICIALS = ("program officer", "grants officer", "grants official", "awarding official")


def _nsf_official(role: str) -> bool:
    words = norm(role)
    return any(title in words for title in _NSF_OFFICIALS)


def _approval_findings(
    charge: Charge, view: GrantView, approval: Record, item: checklist_check.ItemSpec
) -> list[Finding]:
    """Whether one linked approval is from the right person, through the right channel,
    before the cost."""
    a = approval.data
    assert isinstance(a, Approval)
    rule = item.rule.data if item.rule is not None else None
    assert rule is None or isinstance(rule, ApprovalRule)
    ids = [approval.id] + ([item.rule.id] if item.rule else [])
    out: list[Finding] = []
    person = view.people_by_email().get(a.approver_email.value.strip().lower())
    right_person = False
    if person is None:
        out.append(
            Finding(
                APPROVAL,
                "approver_unknown",
                Bucket.NEEDS_HUMAN,
                f"Code can't match the approver, {a.approver_email.value}, to anyone named on "
                "the grant.",
                ids,
            )
        )
    elif rule is not None and norm(rule.approver.value) not in norm(person.role.value):
        out.append(
            Finding(
                APPROVAL,
                "wrong_approver",
                Bucket.POSSIBLE_CONFLICT,
                f"Approved by {person.name.value} ({person.role.value}), "
                f"but the rule needs the {rule.approver.value}.",
                ids,
            )
        )
    elif item.kind == "nsf" and not _nsf_official(person.role.value):
        out.append(
            Finding(
                APPROVAL,
                "wrong_approver",
                Bucket.POSSIBLE_CONFLICT,
                f"Approved by {person.name.value} ({person.role.value}), "
                "who isn't one of the NSF officials on the award notice.",
                ids,
            )
        )
    else:
        right_person = True

    required = rule.channel.value if rule is not None and rule.channel is not None else None
    if item.kind == "nsf":
        required = "Research.gov"
    if required is not None:
        got = a.channel.value if a.channel is not None else None
        if got is None or norm(required) not in norm(got):
            got_words = norm(got or "")
            by_email = (
                "email" in got_words
                or "e mail" in got_words
                or (got is None and view.is_email(approval))
            )
            if by_email and right_person and norm(required) == norm("Research.gov"):
                out.append(
                    Finding(
                        APPROVAL,
                        "email_approval",
                        Bucket.NEEDS_HUMAN,
                        "The approval came by email, outside Research.gov. "
                        "Whether that counts isn't settled.",
                        ids,
                    )
                )
            elif got is None and not by_email:
                out.append(
                    Finding(
                        APPROVAL,
                        "channel_unknown",
                        Bucket.NEEDS_HUMAN,
                        "The approval doesn't say how it was given, and the rule needs "
                        f"{required}.",
                        ids,
                    )
                )
            else:
                out.append(
                    Finding(
                        APPROVAL,
                        "wrong_channel",
                        Bucket.POSSIBLE_CONFLICT,
                        f"The approval came through {got or 'email'}, but the rule needs "
                        f"{required}.",
                        ids,
                    )
                )
    if a.approved_on is None:
        out.append(
            Finding(
                APPROVAL,
                "approval_date_unknown",
                Bucket.NEEDS_HUMAN,
                "The approval doesn't say when it was given, so code can't tell it came before "
                "the cost.",
                ids,
            )
        )
    elif a.approved_on.value > charge.transaction_date:
        out.append(
            Finding(
                APPROVAL,
                "approval_late",
                Bucket.POSSIBLE_CONFLICT,
                f"Approved on {day(a.approved_on.value)}, after the cost on "
                f"{day(charge.transaction_date)}.",
                ids,
            )
        )
    return out


def _approval_check(
    charge: Charge, view: GrantView, result: checklist_check.ChecklistResult
) -> list[Finding]:
    rules = rules_for(view, charge)
    out: list[Finding] = []
    for rule in rules.unmatched:
        assert isinstance(rule.data, ApprovalRule)
        out.append(
            Finding(
                APPROVAL,
                f"rule_unmatched:{view.root(rule.id)}",
                Bucket.NEEDS_HUMAN,
                f"Code can't tell whether the approval rule for '{rule.data.applies_to.value}' "
                "applies to this charge.",
                [rule.id],
                shown_on_term=True,
            )
        )
    for rule in rules.waiting:
        assert isinstance(rule.data, ApprovalRule)
        out.append(
            Finding(
                APPROVAL,
                f"rule_not_confirmed:{view.root(rule.id)}",
                Bucket.NEEDS_HUMAN,
                f"An approval rule for '{rule.data.applies_to.value}' may apply to this charge, "
                "and it isn't confirmed yet.",
                [rule.id],
                shown_on_term=True,
            )
        )
    checked = [i for i in result.items if i.spec.kind in ("rule", "nsf") and i.filled]
    for item in checked:
        approvals = [lk.fact for lk in item.links if isinstance(lk.fact.data, Approval)]
        others = [lk.fact for lk in item.links if not isinstance(lk.fact.data, Approval)]
        per = [_approval_findings(charge, view, a, item.spec) for a in approvals]
        if any(not fs for fs in per):
            continue  # one approval is right on every count
        for fs in per:
            out.extend(fs)
        for fact in others:
            out.append(
                Finding(
                    APPROVAL,
                    "not_an_approval",
                    Bucket.NEEDS_HUMAN,
                    f"{item.spec.needed}: it's filled by {describe(fact).lower()}, not an "
                    "approval.",
                    [fact.id],
                )
            )
    missing = [f for i in result.items if i.spec.is_approval for f in i.findings]
    if not out and not any(f.failing for f in missing):
        needed = [i for i in result.items if i.spec.is_approval]
        if needed:
            ids = [lk.fact.id for i in needed for lk in i.links]
            out.append(
                passed(
                    APPROVAL,
                    "Each required approval is on file, as the rule asks, before the cost.",
                    ids,
                )
            )
        else:
            out.append(passed(APPROVAL, "No approval rule applies to this charge."))
    return out


_VALUE_FIELDS: dict[RecordKind, tuple[str, ...]] = {
    RecordKind.BILL: ("total",),
    RecordKind.APPROVAL: ("approver_email", "covers", "approved_on", "channel"),
    RecordKind.NOTE: ("statement", "period"),
}


def _under(path: str, prefixes: tuple[str, ...] | None) -> bool:
    if prefixes is None:
        return True
    return any(path == p or path.startswith(f"{p}.") or path.startswith(f"{p}[") for p in prefixes)


def _values_check(
    view: GrantView,
    links: list[LinkInForce],
    result: checklist_check.ChecklistResult,
    answers: list[AnswerState],
) -> list[Finding]:
    """Check 5: every value a check or an answer rests on is confirmed."""
    targets: dict[str, tuple[Record, tuple[str, ...] | None]] = {}
    for link in links:
        targets.setdefault(link.fact.id, (link.fact, _VALUE_FIELDS.get(link.fact.kind, ())))
        if link.data.stated_amount is not None or link.data.share is not None:
            # Decision 0021: the basis behind a link for part of a bill.
            targets.setdefault(link.link.id, (link.link, ("stated_amount", "share")))
    for item in result.items:
        if item.spec.record is not None and item.spec.rate is not None:
            targets.setdefault(item.spec.record.id, (item.spec.record, ("rate",)))
    for state in answers:
        if state.judgment is None:
            continue
        j = state.judgment.data
        assert isinstance(j, Judgment)
        for rid in j.rests_on:
            r = view.state.by_id.get(rid)
            if r is not None:
                targets[rid] = (r, None)  # an answer may rest on any of a record's values
    out: list[Finding] = []
    for record, prefixes in targets.values():
        if record.kind in TERM_KINDS and view.state.is_waiting(record.id):
            out.append(
                Finding(
                    VALUES,
                    "term_not_confirmed",
                    Bucket.NEEDS_HUMAN,
                    f"An answer rests on a {record.kind.value.replace('_', ' ')} "
                    "that isn't confirmed yet.",
                    [record.id],
                    shown_on_term=True,
                )
            )
            continue
        paths = [p for p in view.state.unconfirmed_values(record) if _under(p, prefixes)]
        if paths:
            out.append(
                Finding(
                    VALUES,
                    "unconfirmed",
                    Bucket.NEEDS_HUMAN,
                    f"{describe(record)}: {', '.join(paths)} couldn't be confirmed in its file.",
                    [record.id],
                )
            )
    if not out:
        out.append(passed(VALUES, "Every value this charge rests on is confirmed.", list(targets)))
    return out


def _part_of_bill_check(view: GrantView, links: list[LinkInForce]) -> list[Finding]:
    """Decision 0021: a link for part of a bill rests on a cited basis.

    When a link covers less than its bill's total and the bill's other links on this
    grant don't account for the rest, the link's amount needs a line on the bill that
    states the part (`stated_amount`), or a share with its cited basis (`share`).
    Without one the charge is Needs a human, whatever the sums say, since matching
    amounts alone could come from copying the charge. A stated amount has to equal the
    link's amount, and a share's worked-out amount has to match it within one cent.
    """
    out: list[Finding] = []
    for link in links:
        bill = link.fact.data
        amount = link.data.amount_cents
        if not isinstance(bill, Bill) or amount is None or abs(amount) >= abs(bill.total.value):
            continue
        ids = [link.link.id, link.fact.id]
        used = sum(lk.data.amount_cents or 0 for lk in view.using_links(link.fact.id))
        stated, share = link.data.stated_amount, link.data.share
        if stated is None and share is None:
            if compare(used, bill.total.value) >= 0:
                continue  # this grant's charges account for the whole bill
            out.append(
                Finding(
                    CHECKLIST,
                    f"part_without_basis:{view.root(link.link.id)}",
                    Bucket.NEEDS_HUMAN,
                    f"{describe(link.fact)} is linked for {money(amount)} of its "
                    f"{money(bill.total.value)}, with nothing cited for that part: a line "
                    "on the bill that states it, or the basis for the share.",
                    ids,
                )
            )
        elif stated is not None and stated.value != amount:
            out.append(
                Finding(
                    CHECKLIST,
                    f"part_mismatch:{view.root(link.link.id)}",
                    Bucket.NEEDS_HUMAN,
                    f"{describe(link.fact)}: the part it states is {money(stated.value)}, "
                    f"but the link is for {money(amount)}.",
                    ids,
                )
            )
        elif share is not None and not share.matches(amount):
            worked = share.amount().quantize(Decimal(1), rounding=ROUND_HALF_UP)
            out.append(
                Finding(
                    CHECKLIST,
                    f"share_mismatch:{view.root(link.link.id)}",
                    Bucket.NEEDS_HUMAN,
                    f"{describe(link.fact)}: {share.share.value} of {share.out_of.value} of "
                    f"{money(share.total.value)} is {money(int(worked))}, "
                    f"not the {money(amount)} linked.",
                    ids,
                )
            )
        elif share is not None and share.total.value != bill.total.value:
            out.append(
                Finding(
                    CHECKLIST,
                    f"share_total_mismatch:{view.root(link.link.id)}",
                    Bucket.NEEDS_HUMAN,
                    f"{describe(link.fact)}: the share is worked out of "
                    f"{money(share.total.value)}, but the bill's total is "
                    f"{money(bill.total.value)}.",
                    ids,
                )
            )
    return out


def _budget_line_check(charge: Charge, view: GrantView) -> list[Finding]:
    """The ledger account's category against the assigned budget line.

    Needs a human when they disagree.
    """
    assigned = view.assigned_line(charge.id)
    if assigned is None:
        # The agent assigns a line, or flags the charge, on every run that covers it.
        # While a run is queued or running, the app shows the charge as rechecking.
        return [
            Finding(
                BUDGET_LINE,
                "not_assigned",
                Bucket.NEEDS_HUMAN,
                "No budget line is assigned to this charge yet.",
            )
        ]
    assignment, line = assigned
    if line is None:
        waiting = view.unconfirmed_line(charge.id)
        if waiting is not None:
            assert isinstance(waiting.data, BudgetLine)
            return [
                Finding(
                    BUDGET_LINE,
                    "line_not_confirmed",
                    Bucket.NEEDS_HUMAN,
                    f"The budget line this charge is assigned to, {waiting.data.name.value}, "
                    "isn't confirmed yet.",
                    [assignment.id, waiting.id],
                    shown_on_term=True,
                )
            ]
        return [
            Finding(
                BUDGET_LINE,
                "line_not_in_force",
                Bucket.NEEDS_HUMAN,
                "The budget line this charge is assigned to is no longer in force.",
                [assignment.id],
            )
        ]
    account_categories = categories(charge.account)
    if not account_categories:
        return []
    data = line.data
    assert isinstance(data, BudgetLine)
    names = " or ".join(category_name(c) for c in account_categories)
    ids = [assignment.id, line.id]
    if any(categories_match(c, data.category) for c in account_categories):
        return [
            passed(
                BUDGET_LINE,
                f"The ledger account's category, {names}, agrees with the assigned line, "
                f"{data.name.value}.",
                ids,
            )
        ]
    return [
        Finding(
            BUDGET_LINE,
            "disagrees",
            Bucket.NEEDS_HUMAN,
            f"The ledger account, {charge.account}, is {names}, "
            f"but the charge is assigned to {data.name.value}.",
            ids,
        )
    ]


def _flags(charge: Charge, view: GrantView) -> list[Finding]:
    out: list[Finding] = []
    for r in view.judgments:
        j = r.data
        assert isinstance(j, Judgment)
        if j.question != Question.FLAG or j.charge_id != charge.id:
            continue
        if r.author == Author.AGENT:
            text = f"The agent flagged this charge: {j.text}"
        else:
            text = f"The accountant answered the agent's flag ({j.text}): {j.answer.value}."
        out.append(
            Finding(
                "flag",
                f"flag:{j.rule or view.root(r.id)}",
                ANSWER_BUCKET[j.answer],
                text,
                [r.id, *j.rests_on],
            )
        )
    return out


def describe_suggestion(view: GrantView, r: Record) -> str:
    old = view.state.by_id.get(r.replaces_id) if r.replaces_id else None
    if r.kind == RecordKind.CHECKLIST_REMOVAL:
        return "The agent suggests removing a checklist item"
    if r.kind == RecordKind.DUPLICATE:
        return "The agent marked a file as a copy of another"
    if r.kind == RecordKind.RETRACTION and old is not None:
        if old.kind == RecordKind.JUDGMENT:
            return "The agent suggests withdrawing its flag"
        return f"The agent suggests withdrawing a {old.kind.value.replace('_', ' ')}"
    if old is not None:
        if old.kind == RecordKind.LINK:
            return "The agent suggests a fix to a link"
        if old.kind == RecordKind.JUDGMENT:
            return "The agent suggests a new answer"
        return f"The agent suggests a correction to a {old.kind.value.replace('_', ' ')}"
    if r.kind == RecordKind.LINK:
        return "The agent suggests a second link between a bill and this charge"
    return f"The agent suggests a {r.kind.value.replace('_', ' ')}"


def suggestions_by_charge(view: GrantView) -> dict[str, list[Record]]:
    """The agent's waiting suggestions (not terms or disputes), by each charge they touch."""
    out: dict[str, list[Record]] = {}
    for r in view.waiting:
        if r.kind == RecordKind.DISPUTE or r.kind in TERM_KINDS:
            continue
        touched: set[str] = set()
        if r.charge_id is not None:
            touched.add(r.charge_id)
        old = view.state.by_id.get(r.replaces_id) if r.replaces_id else None
        if old is not None:
            if old.charge_id is not None:
                touched.add(old.charge_id)
            touched.update(lk.data.charge_id for lk in view.links_to_fact.get(old.id, []))
        if r.kind == RecordKind.DUPLICATE:
            assert isinstance(r.data, Duplicate)
            files = {r.data.copy_file_id, r.data.original_file_id}
            for fact_id, links in view.links_to_fact.items():
                fact = view.state.by_id[fact_id]
                if view.files_of(fact) & files:
                    touched.update(lk.data.charge_id for lk in links)
        for charge_id in touched:
            out.setdefault(charge_id, []).append(r)
    return out


def _failed_run_on_charge(run: AgentRun, charge_id: str) -> str | None:
    """The text of a failed run's reason on this charge, when the run was about it."""
    kind = run.trigger.kind
    if kind == TriggerKind.CHARGE and run.trigger.id == charge_id:
        return "The agent couldn't finish reading this."
    if kind == TriggerKind.THREAD_MESSAGE and run.thread_charge_id == charge_id:
        return "The agent couldn't finish answering a message in this charge's thread."
    if kind == TriggerKind.OPEN_QUESTION and run.trigger.id == charge_id:
        return "The agent couldn't finish answering an open question on this charge."
    return None


def evaluate_charge(
    charge: Charge,
    view: GrantView,
    suggestions: list[Record],
    failed_runs: list[AgentRun],
    over_linked_bills: set[str],
) -> ChargeEval:
    result = checklist_check.evaluate(charge, view)
    links = view.links[charge.id]
    approvals = list(
        {lk.fact.id: lk.fact for lk in links if lk.fact.kind == RecordKind.APPROVAL}.values()
    )
    p = view.period
    early = (
        p is not None
        and p.start is not None
        and charge.transaction_date < p.start - timedelta(days=checklist_check.PRE_AWARD_DAYS)
    )
    rules_apply = bool(rules_for(view, charge).applying)
    # An NSF standing-list item is an approval like any other, so Covers is asked for it too.
    standing_list = any(i.spec.kind == "nsf" for i in result.items)
    answers = _questions(charge, view, approvals, rules_apply or early or standing_list)
    covers = [s for s in answers if s.question == Question.COVERS]

    findings: list[Finding] = [_date_check(charge, view, covers)]
    findings += [f for f in result.findings if f.check == CHECKLIST]
    findings += [f for f in result.findings if f.check == APPROVAL]
    findings += _approval_check(charge, view, result)
    findings += _values_check(view, links, result, answers)
    findings += _budget_line_check(charge, view)
    findings += _part_of_bill_check(view, links)
    findings += [s.finding() for s in answers]
    findings += _flags(charge, view)

    for r in suggestions:
        findings.append(
            Finding(
                SUGGESTION,
                f"waiting:{r.id}",
                Bucket.NEEDS_HUMAN,
                f"{describe_suggestion(view, r)}, waiting for the accountant.",
                [r.id] + ([r.replaces_id] if r.replaces_id else []),
            )
        )

    for link in links:
        if link.fact.id in over_linked_bills:
            findings.append(
                Finding(
                    CHECKLIST,
                    "bill_over_linked",
                    Bucket.NEEDS_HUMAN,
                    f"{describe(link.fact)} is linked for more than its total.",
                    [link.fact.id],
                )
            )

    for run in failed_runs:
        text = _failed_run_on_charge(run, charge.id)
        if text is not None:
            findings.append(Finding(AGENT_RUN, f"failed:{run.id}", Bucket.NEEDS_HUMAN, text))

    # A waiting dispute: the disputed reason counts as Needs a human.
    for r in view.waiting:
        d = r.data
        if not isinstance(d, Dispute) or d.charge_id != charge.id:
            continue
        for f in findings:
            if f.check == d.check and f.failing:
                f.bucket = Bucket.NEEDS_HUMAN
                f.text += " The agent disputes this, waiting for the accountant."
                f.record_ids.append(r.id)
                f.flag_now = True
                f.dispute_id = r.id

    questions = [s.open_question(charge.id) for s in answers if s.is_open]
    return ChargeEval(
        findings=findings,
        entries=result.entries,
        questions=questions,
        rechecking=any(s.rechecking for s in answers),
    )
