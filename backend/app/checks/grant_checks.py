"""Check 4, the budget, and the other problems on the grant itself (contracts.md section 8).

Problems on the grant: no dates or no budget at all (confirmed or waiting), a
closeout review run that failed for good, spending over the award's
limit, a funding notice whose totals don't add up, and a skipped amendment number.
An overspent budget line is a grant note, not a problem.

How a funding notice's own budget lines combine with the lines already confirmed
is the builder's (provisional). A category's budget is counted once per notice:
the parent line's amount when the notice prints one, otherwise the sum of the
category's lines. A line belongs to the notice whose file it's cited from (call
36). A line the accountant typed has no citation: when it corrects a cited line
it belongs to that line's notice. A typed sub-line joins the one cited notice
that prints its parent with the same date; any other typed line is grouped with
the typed lines of its date.
The sub-lines of Participant Support Costs and of Travel carry their parent's
category (contract ruling f),
so this keeps a parent and its sub-lines from being counted twice. Then the
notices add up. A charge's spending counts on its assigned line's category and,
for a sub-line of Other Direct Costs, on Other Direct Costs too. Notes are per
category, named as NSF prints the category.
"""

import hashlib
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from app.checks.findings import (
    AGENT_RUN,
    BUDGET,
    GRANT_TERMS,
    NOTICE,
    OVER_LIMIT,
    SKIPPED_FILES,
    Finding,
)
from app.checks.ledger_accounts import CATEGORY_NAMES, category_name
from app.checks.rules_match import name_key
from app.checks.text import money
from app.checks.view import GrantView, notice_number
from app.contracts.charges import Charge
from app.contracts.checks import Bucket, GrantNote
from app.contracts.mail import SkippedFile, SkipReason
from app.contracts.records import (
    CATEGORY_PARENT,
    BudgetCategory,
    BudgetLine,
    Notice,
    Record,
    RecordKind,
)
from app.contracts.rules import RecordState
from app.contracts.runs import AgentRun, TriggerKind

_SKIP_WHY = {
    SkipReason.TOO_LARGE: "too large",
    SkipReason.NOT_EXPORTABLE: "couldn't be exported to a PDF",
}


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


def grant_problems(
    view: GrantView,
    failed_runs: Sequence[AgentRun] = (),
    skipped_files: Sequence[SkippedFile] = (),
) -> list[Finding]:
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
    skipped = [s for s in skipped_files if s.grant_id == view.grant_id]
    if skipped:
        # The problem names the set of files, so accepting it covers just those, and
        # a file skipped later raises it again.
        names = sorted(f"{s.source}:{s.source_ref}:{s.name}" for s in skipped)
        digest = hashlib.sha256("\n".join(names).encode()).hexdigest()[:12]
        out.append(
            Finding(
                SKIPPED_FILES,
                f"skipped:{digest}",
                Bucket.NEEDS_HUMAN,
                "These files weren't taken in: "
                + "; ".join(f"{s.name} ({_SKIP_WHY[s.reason]})" for s in skipped)
                + ".",
            )
        )
    limit = _limit(view)
    spending = sum(c.amount_cents for c in view.charges)
    if limit is not None and spending > limit[0]:
        d = limit[1].data
        assert isinstance(d, Notice)
        over = spending - limit[0]
        out.append(
            Finding(
                BUDGET,
                OVER_LIMIT,
                Bucket.NEEDS_HUMAN,
                f"Spending of {money(spending)} is {money(over)} over the award's limit of "
                f"{money(limit[0])}, the total obligated to date on amendment "
                f"{d.amendment_number.value}.",
                [limit[1].id],
                amount_cents=over,
            )
        )
    out += _notice_findings(view)
    return out


def _cited_file(line: BudgetLine) -> str | None:
    """The file a budget line's amount, or failing that its name, is cited from."""
    for value in (line.amount, line.name):
        if value.citation is not None:
            return value.citation.file_id
    return None


def _notice_of(view: GrantView, record: Record) -> tuple[str, str]:
    """Which notice a budget line belongs to (call 36).

    The file it's cited from. A line the accountant typed has no citation: when it
    corrects a cited line, it belongs to that line's file, followed back through the
    corrections. A typed line with no cited line behind it is keyed by its date here,
    and _notice_keys() then puts it with the one cited notice of that date, if exactly
    one exists (#84).
    """
    seen: set[str] = set()
    r: Record | None = record
    while r is not None and r.id not in seen:
        seen.add(r.id)
        if isinstance(r.data, BudgetLine):
            found = _cited_file(r.data)
            if found is not None:
                return ("file", found)
        r = view.state.by_id.get(r.replaces_id) if r.replaces_id else None
    assert isinstance(record.data, BudgetLine)
    return ("dated", record.data.dated.value.isoformat())


def _is_parent(category: BudgetCategory, line: BudgetLine) -> bool:
    """Whether a line is its category's parent line, named as NSF prints the category."""
    return name_key(line.name.value) in {name_key(n) for n in CATEGORY_NAMES[category]}


def _notice_keys(view: GrantView, lines: list[Record]) -> dict[str, tuple[str, str]]:
    """Each budget line's notice.

    A typed line with no cited line behind it joins a cited notice only when it can't
    be a separate notice's line: it's a sub-line, and exactly one cited notice prints
    its category's parent line with the same date (#84). A typed parent line could be
    a separate notice's, such as an increment typed with the award letter's date, so
    it never joins; it stays with the other typed lines of its date.
    """
    keys = {r.id: _notice_of(view, r) for r in lines}
    parents_in: dict[tuple[BudgetCategory, str], set[str]] = defaultdict(set)
    for r in lines:
        kind, value = keys[r.id]
        data = r.data
        if kind == "file" and isinstance(data, BudgetLine) and _is_parent(data.category, data):
            parents_in[(data.category, data.dated.value.isoformat())].add(value)
    for r in lines:
        kind, value = keys[r.id]
        data = r.data
        if kind != "dated" or not isinstance(data, BudgetLine) or _is_parent(data.category, data):
            continue
        files = parents_in.get((data.category, value), set())
        if len(files) == 1:
            keys[r.id] = ("file", next(iter(files)))
    return keys


def _notice_budget(category: BudgetCategory, members: list[Record], typed: bool = False) -> int:
    """One notice's budget for a category: its parent line's amount, or its lines' sum.

    In a group of typed lines (grouped by date because nothing ties them to a notice),
    each typed parent line may be a different notice's, so every parent counts (#104).
    Counting them all can only raise the budget, so this rule can miss a note but
    doesn't make a false one. Two false notes are still possible, both because nothing
    ties a typed line to its notice (#104):
    - an increment's typed sub-line that shares the award letter's date joins the
      letter (see _notice_keys), and its amount drops out;
    - in a group of typed lines, one notice's typed parent and another notice's typed
      sub-line with the same date: the sub-line drops out, because a group with a
      parent counts only parents.
    """
    parents = [
        r for r in members if isinstance(r.data, BudgetLine) and _is_parent(category, r.data)
    ]
    counted = (parents if typed else parents[-1:]) if parents else members
    return sum(r.data.amount.value for r in counted if isinstance(r.data, BudgetLine))


@dataclass(frozen=True)
class LineFigure:
    """One confirmed budget line: its amount, and what's spent on it."""

    record_id: str
    name: str
    category: BudgetCategory
    amount_cents: int
    spent_cents: int  # the charges assigned to this line


@dataclass(frozen=True)
class CategoryFigure:
    """One NSF category's budget and spending, as the grant notes compute them.

    The budget counts each notice once (its parent line, or its lines' sum). Spending
    counts the charges assigned to the category's lines and, for Other Direct Costs,
    to its sub-lines too.
    """

    category: BudgetCategory
    name: str  # as NSF prints the category
    budget_cents: int
    spent_cents: int
    record_ids: tuple[str, ...]  # the category's budget lines

    @property
    def overspent(self) -> bool:
        return self.spent_cents > self.budget_cents


@dataclass(frozen=True)
class BudgetFigures:
    lines: tuple[LineFigure, ...]
    categories: tuple[CategoryFigure, ...]
    # The award's limit: the Total Amount Obligated to Date on the latest confirmed
    # notice that prints one, and that notice. None when no confirmed notice prints one.
    limit_cents: int | None
    limit_notice_id: str | None
    spent_cents: int  # the sum of every charge on the grant's ledger, as the limit compares


def _figures(view: GrantView) -> BudgetFigures:
    by_notice: dict[tuple[BudgetCategory, tuple[str, str]], list[Record]] = defaultdict(list)
    lines: dict[BudgetCategory, list[Record]] = defaultdict(list)
    keys = _notice_keys(view, view.budget_lines())
    for r in view.budget_lines():
        assert isinstance(r.data, BudgetLine)
        by_notice[(r.data.category, keys[r.id])].append(r)
        lines[r.data.category].append(r)
    budget: dict[BudgetCategory, int] = defaultdict(int)
    for (category, (kind, _)), members in by_notice.items():
        budget[category] += _notice_budget(category, members, typed=kind == "dated")
    spent: dict[BudgetCategory, int] = defaultdict(int)
    spent_on_line: dict[str, int] = defaultdict(int)
    for c in view.charges:
        assigned = view.assigned_line(c.id)
        if assigned is None or assigned[1] is None:
            continue
        line = assigned[1].data
        assert isinstance(line, BudgetLine)
        spent_on_line[assigned[1].id] += c.amount_cents
        spent[line.category] += c.amount_cents
        parent = CATEGORY_PARENT.get(line.category)
        if parent is not None:
            spent[parent] += c.amount_cents
    line_figures: list[LineFigure] = []
    for r in view.budget_lines():
        assert isinstance(r.data, BudgetLine)
        line_figures.append(
            LineFigure(
                record_id=r.id,
                name=r.data.name.value,
                category=r.data.category,
                amount_cents=r.data.amount.value,
                spent_cents=spent_on_line[r.id],
            )
        )
    category_figures = tuple(
        CategoryFigure(
            category=category,
            name=category_name(category),
            budget_cents=amount,
            spent_cents=spent[category],
            record_ids=tuple(r.id for r in lines[category]),
        )
        for category, amount in budget.items()
    )
    limit = _limit(view)
    return BudgetFigures(
        lines=tuple(line_figures),
        categories=category_figures,
        limit_cents=limit[0] if limit is not None else None,
        limit_notice_id=limit[1].id if limit is not None else None,
        spent_cents=sum(c.amount_cents for c in view.charges),
    )


def budget_figures(
    grant_id: str, records: Sequence[Record], charges: Sequence[Charge]
) -> BudgetFigures:
    """A grant's budget figures, the same ones the grant notes come from (issue 106).

    Per confirmed budget line: its amount and what's spent on it. Per category: its
    budget and spending. `records` are the workspace's records visible at the clock's
    "now", in the order they were written, and `charges` the charges that have arrived.
    """
    view = GrantView(grant_id, RecordState(records), list(charges), [])
    return _figures(view)


def grant_notes(view: GrantView) -> list[GrantNote]:
    """An overspent budget line, for example "Materials and Supplies: $42,000.00 of $40,000.00"."""
    return [
        GrantNote(
            grant_id=view.grant_id,
            check=BUDGET,
            text=f"{f.name}: {money(f.spent_cents)} of {money(f.budget_cents)}",
            record_ids=f.record_ids,
        )
        for f in _figures(view).categories
        if f.overspent
    ]
