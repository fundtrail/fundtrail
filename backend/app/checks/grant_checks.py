"""Check 4, the budget, and the other problems on the grant itself (contracts.md section 8).

Problems on the grant: no dates or no budget at all (confirmed or waiting), a
closeout review run that failed for good, spending over the award's
limit, a funding notice whose totals don't add up, and a skipped amendment number.
An overspent budget line is a grant note, not a problem.

How a funding notice's own budget lines combine with the lines already confirmed
is the builder's (provisional). A category's budget is counted once per notice
(the lines with the same date): the parent line's amount when the notice prints
one, otherwise the sum of the category's lines. The sub-lines of Participant
Support Costs and of Travel carry their parent's category (contract ruling f),
so this keeps a parent and its sub-lines from being counted twice. Then the
notices add up. A charge's spending counts on its assigned line's category and,
for a sub-line of Other Direct Costs, on Other Direct Costs too. Notes are per
category, named as NSF prints the category.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from app.checks.findings import AGENT_RUN, BUDGET, GRANT_TERMS, NOTICE, Finding
from app.checks.ledger_accounts import CATEGORY_NAMES, category_name
from app.checks.rules_match import name_key
from app.checks.text import money
from app.checks.view import GrantView, notice_number
from app.contracts.checks import Bucket, GrantNote
from app.contracts.records import (
    CATEGORY_PARENT,
    BudgetCategory,
    BudgetLine,
    Notice,
    Record,
    RecordKind,
)
from app.contracts.runs import AgentRun, TriggerKind


def _label(n: int) -> str:
    return f"{n:03d}"


def _notice_findings(view: GrantView) -> list[Finding]:
    numbered: list[tuple[int, Record, Notice]] = []
    for r in view.notices():
        assert isinstance(r.data, Notice)
        n = notice_number(r.data)
        if n is not None:
            numbered.append((n, r, r.data))
    numbered.sort(key=lambda t: (t[0], view.pos[t[1].id]))
    out: list[Finding] = []
    if numbered:
        have = {n for n, _, _ in numbered}
        top = max(have)
        for n in range(top + 1):
            if n not in have:
                out.append(
                    Finding(
                        NOTICE,
                        f"amendment_skipped:{_label(n)}",
                        Bucket.NEEDS_HUMAN,
                        f"Amendment {_label(n)} is missing: the confirmed notices go up to "
                        f"{_label(top)}.",
                        [r.id for _, r, _ in numbered],
                    )
                )
    previous: tuple[int, Record] | None = None  # the earlier confirmed total
    for n, r, d in numbered:
        prior_total = 0 if n == 0 else (previous[0] if previous else None)
        if (
            d.obligated_by_amendment is not None
            and d.obligated_to_date is not None
            and prior_total is not None
        ):
            expected = prior_total + d.obligated_by_amendment.value
            if expected != d.obligated_to_date.value:
                ids = ([previous[1].id] if previous and n != 0 else []) + [r.id]
                out.append(
                    Finding(
                        NOTICE,
                        f"totals:{_label(n)}",
                        Bucket.NEEDS_HUMAN,
                        f"Amendment {_label(n)}: the earlier total of {money(prior_total)} plus "
                        "the "
                        f"{money(d.obligated_by_amendment.value)} it adds is {money(expected)}, "
                        "not the "
                        f"{money(d.obligated_to_date.value)} it prints.",
                        ids,
                    )
                )
        if d.obligated_to_date is not None:
            previous = (d.obligated_to_date.value, r)
    return out


def _limit(view: GrantView) -> tuple[int, Record] | None:
    """The Total Amount Obligated to Date on the latest confirmed notice that prints one."""
    best: tuple[tuple[object, ...], int, Record] | None = None
    for r in view.notices():
        d = r.data
        assert isinstance(d, Notice)
        if d.obligated_to_date is None:
            continue
        key = (d.dated.value, notice_number(d) or -1, view.pos[r.id])
        if best is None or key > best[0]:
            best = (key, d.obligated_to_date.value, r)
    return (best[1], best[2]) if best else None


def _has_term(view: GrantView, kind: RecordKind) -> bool:
    """Whether the grant has a term of this kind at all, confirmed or waiting."""
    return bool(view.terms[kind]) or any(r.kind == kind for r in view.waiting_terms)


def grant_problems(view: GrantView, failed_runs: Sequence[AgentRun] = ()) -> list[Finding]:
    out: list[Finding] = []
    # Only when no such term exists at all: a waiting one is its own row on the list.
    if not _has_term(view, RecordKind.PERIOD_OF_PERFORMANCE):
        out.append(
            Finding(GRANT_TERMS, "no_dates", Bucket.NEEDS_HUMAN, "The grant has no dates on file.")
        )
    if not _has_term(view, RecordKind.BUDGET_LINE):
        out.append(
            Finding(
                GRANT_TERMS, "no_budget", Bucket.NEEDS_HUMAN, "The grant has no budget on file."
            )
        )
    for run in failed_runs:
        # The closeout review, which the clock starts, fails on the grant.
        if run.trigger.kind == TriggerKind.CLOCK and run.grant_id == view.grant_id:
            out.append(
                Finding(
                    AGENT_RUN,
                    f"failed:{run.id}",
                    Bucket.NEEDS_HUMAN,
                    "The agent couldn't finish its review of the grant.",
                )
            )
    limit = _limit(view)
    spending = sum(c.amount_cents for c in view.charges)
    if limit is not None and spending > limit[0]:
        d = limit[1].data
        assert isinstance(d, Notice)
        out.append(
            Finding(
                BUDGET,
                "over_limit",
                Bucket.NEEDS_HUMAN,
                f"Spending of {money(spending)} is over the award's limit of {money(limit[0])}, "
                f"the total obligated to date on amendment {d.amendment_number.value}.",
                [limit[1].id],
            )
        )
    out += _notice_findings(view)
    return out


def _notice_budget(category: BudgetCategory, members: list[Record]) -> int:
    """One notice's budget for a category: its parent line's amount, or its lines' sum."""
    names = {name_key(n) for n in CATEGORY_NAMES[category]}
    parents = [
        r
        for r in members
        if isinstance(r.data, BudgetLine) and name_key(r.data.name.value) in names
    ]
    counted = parents[-1:] if parents else members
    return sum(r.data.amount.value for r in counted if isinstance(r.data, BudgetLine))


def grant_notes(view: GrantView) -> list[GrantNote]:
    """An overspent budget line, for example "Materials and Supplies: $42,000.00 of $40,000.00"."""
    by_notice: dict[tuple[BudgetCategory, date], list[Record]] = defaultdict(list)
    lines: dict[BudgetCategory, list[Record]] = defaultdict(list)
    for r in view.budget_lines():
        assert isinstance(r.data, BudgetLine)
        by_notice[(r.data.category, r.data.dated.value)].append(r)
        lines[r.data.category].append(r)
    budget: dict[BudgetCategory, int] = defaultdict(int)
    for (category, _), members in by_notice.items():
        budget[category] += _notice_budget(category, members)
    spent: dict[BudgetCategory, int] = defaultdict(int)
    for c in view.charges:
        assigned = view.assigned_line(c.id)
        if assigned is None or assigned[1] is None:
            continue
        line = assigned[1].data
        assert isinstance(line, BudgetLine)
        spent[line.category] += c.amount_cents
        parent = CATEGORY_PARENT.get(line.category)
        if parent is not None:
            spent[parent] += c.amount_cents
    notes: list[GrantNote] = []
    for category, amount in budget.items():
        if spent[category] > amount:
            name = category_name(category)
            notes.append(
                GrantNote(
                    grant_id=view.grant_id,
                    check=BUDGET,
                    text=f"{name}: {money(spent[category])} of {money(amount)}",
                    record_ids=tuple(r.id for r in lines[category]),
                )
            )
    return notes
