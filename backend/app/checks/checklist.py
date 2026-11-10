"""Check 2: each charge's evidence checklist, filled or missing, and its sums.

Default items aren't stored. They're worked out each time from the charge's
ledger account (its account group), the grant's confirmed approval rules, and the
period in force. Added items and removals are records.

- The account group's bill-like item (bill, partner's invoice, usage statement,
  participant payment record) carries a default amount worked out each time: it
  covers whatever the charge's other amount-carrying items don't. When the other
  items add up to the whole charge it needs nothing and isn't shown missing.
- A required approval is a default item, one per confirmed approval rule that
  applies, keyed by the rule's first record so the key survives a correction.
- A cost dated up to 90 days before the start date gets the university's own
  pre-award approval as a default item.
- Correcting lines follow decision 0020's change to 0016 (provisional). A line
  that takes money off the grant (a negative amount) gets only the two
  correction items: the line it corrects, and a written justification. A line
  that adds money and names a line it corrects (original_line_id) gets its
  account group's default plus the two. The rest of 0020 (netting a charge
  against its corrections, a Reversed charge, the corrected-line item filled
  from the ledger) waits for its contract shapes and plugs in at
  _correction_items() and items_in_force().
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.checks.findings import APPROVAL, CHECKLIST, Finding, passed
from app.checks.ledger_accounts import group_items
from app.checks.rules_match import rules_for
from app.checks.text import money, slug
from app.checks.view import GrantView, LinkInForce
from app.contracts.charges import Charge
from app.contracts.checks import Bucket, ChecklistEntry, ItemSource
from app.contracts.records import (
    ApprovalRule,
    Author,
    ChecklistItem,
    ChecklistRemoval,
    DefaultItem,
    Note,
    Period,
    Rate,
    RateMath,
    Record,
)
from app.contracts.rules import RecordState

PRE_AWARD_DAYS = 90  # costs up to this many days before the start date are allowed

# Item kinds that are approvals: missing ones go on the problem list right away.
APPROVAL_KINDS = frozenset({"rule", "nsf", "pre_award"})


@dataclass
class ItemSpec:
    """One item on a charge's checklist, a default or an added one."""

    needed: str
    kind: str  # plain, bill_like, reversal, rule, nsf or pre_award
    default_key: str | None = None
    record: Record | None = None  # the added checklist_item, as it stands now
    added_by: ItemSource = ItemSource.DEFAULT
    amount_cents: int | None = None
    period: Period | None = None
    expected_by: date | None = None
    rule: Record | None = None  # the approval rule a required approval comes from
    rate: RateMath | None = None

    @property
    def stable(self) -> str:
        """Names the item the same way on every charge, so a reusable note can match it."""
        return self.default_key or f"item:{slug(self.needed)}"

    @property
    def is_approval(self) -> bool:
        return self.kind in APPROVAL_KINDS


@dataclass
class ItemResult:
    spec: ItemSpec
    links: list[LinkInForce]
    filled: bool
    removal_waiting_id: str | None
    findings: list[Finding] = field(default_factory=list[Finding])


@dataclass
class ChecklistResult:
    items: list[ItemResult]
    entries: list[ChecklistEntry]
    findings: list[Finding]


def _correction_items(charge: Charge) -> list[ItemSpec]:
    """The two items of a line that corrects another. The rest of decision 0020 plugs in here."""
    corrects = "The line it corrects"
    if charge.original_line_id:
        corrects += f", ledger line {charge.original_line_id}"
    return [
        ItemSpec(corrects, "reversal", "corrected_line"),
        ItemSpec("A written justification", "reversal", "justification"),
    ]


def _approval_needed(rule: ApprovalRule) -> str:
    text = f"The {rule.approver.value}'s approval"
    if rule.channel is not None:
        text += f" through {rule.channel.value}"
    return text


def default_specs(charge: Charge, view: GrantView) -> list[ItemSpec]:
    """The charge's default items, before amounts are worked out and removals applied."""
    specs: list[ItemSpec] = []
    # The account group's items, with the table's due dates. The table applies
    # decision 0020's sign rule, so a line that takes money off gets none here.
    for item in group_items(charge):
        specs.append(
            ItemSpec(
                item.needed,
                "bill_like" if item.bill_like else "plain",
                item.key,
                period=item.period,
                expected_by=item.expected_by,
            )
        )
    # Decision 0020's two correction items, which the table doesn't hold: for a
    # line that takes money off the grant, or one that names a line it corrects.
    # "Takes money off the grant" is a negative amount, the same test as
    # account_groups.account_group_items uses; change the two together.
    if charge.amount_cents < 0 or charge.original_line_id:
        specs += _correction_items(charge)
    for rule in rules_for(view, charge).applying:
        assert isinstance(rule.data, ApprovalRule)
        specs.append(
            ItemSpec(
                _approval_needed(rule.data),
                "rule",
                f"approval:{view.root(rule.id)}",
                rule=rule,
                added_by=ItemSource.RULE,
            )
        )
    p = view.period
    if p is not None and p.start is not None and not p.disagree:
        if p.start - timedelta(days=PRE_AWARD_DAYS) <= charge.transaction_date < p.start:
            specs.append(
                ItemSpec(
                    "The university's own pre-award approval", "pre_award", "pre_award_approval"
                )
            )
    return specs


def added_specs(charge: Charge, view: GrantView) -> list[ItemSpec]:
    specs: list[ItemSpec] = []
    for r in view.items[charge.id]:
        item = r.data
        assert isinstance(item, ChecklistItem)
        specs.append(
            ItemSpec(
                item.needed,
                "nsf" if item.nsf_standing_list else "plain",
                record=r,
                added_by=ItemSource.USER if r.author == Author.USER else ItemSource.AGENT,
                amount_cents=item.amount_cents,
                period=item.period,
                expected_by=item.expected_by,
                rate=item.rate,
            )
        )
    return specs


def _removals(charge: Charge, view: GrantView) -> tuple[set[str], dict[str, str]]:
    """The items removed (by default key or item record ID) and the agent's removals that wait."""

    def target(data: ChecklistRemoval) -> str:
        if data.default_item is not None:
            return f"default:{data.default_item}"
        assert data.item_record_id is not None
        now = view.state.current_version(data.item_record_id)
        return f"item:{now.id if now else data.item_record_id}"

    removed = set()
    for r in view.removals[charge.id]:
        assert isinstance(r.data, ChecklistRemoval)
        removed.add(target(r.data))
    waiting: dict[str, str] = {}
    for r in view.waiting:
        if isinstance(r.data, ChecklistRemoval) and r.data.charge_id == charge.id:
            waiting[target(r.data)] = r.id
    return removed, waiting


def _ident(spec: ItemSpec) -> str:
    return (
        f"default:{spec.default_key}"
        if spec.default_key
        else f"item:{spec.record.id if spec.record else ''}"
    )


def compare(total: int, target: int) -> int:
    """0 when the amounts agree, 1 when total goes over target, -1 when it's under.

    A credit's target is negative, and going over means more negative. A total of
    the opposite sign is over (call 38): it can't be part of the target.
    """
    if total == target:
        return 0
    if target == 0:
        return 1
    if total != 0 and (total > 0) != (target > 0):
        return 1
    sign = 1 if target > 0 else -1
    return 1 if (total - target) * sign > 0 else -1


def items_in_force(charge: Charge, view: GrantView) -> tuple[list[ItemSpec], dict[str, str]]:
    """The checklist's items, with removals applied and the default amount worked out."""
    removed, waiting = _removals(charge, view)
    specs = [
        s
        for s in default_specs(charge, view) + added_specs(charge, view)
        if _ident(s) not in removed
    ]
    others = sum(
        s.amount_cents for s in specs if s.amount_cents is not None and s.kind != "bill_like"
    )
    for s in specs:
        if s.kind == "bill_like":
            rest = charge.amount_cents - others
            # Items over the charge leave the bill item nothing; the charge's sum then goes over.
            same_sign = rest == 0 or (rest > 0) == (charge.amount_cents > 0)
            s.amount_cents = rest if same_sign else 0
    return specs, waiting


def default_items(charge: Charge, records: Sequence[Record]) -> list[DefaultItem]:
    """A charge's default checklist items. Matches records.DefaultItems, for the write check."""
    state = RecordState(records)
    view = GrantView(charge.grant_id, state, [charge], [])
    specs, _ = items_in_force(charge, view)
    return [
        DefaultItem(
            key=s.default_key,
            needed=s.needed,
            amount_cents=s.amount_cents,
            period=s.period,
            expected_by=s.expected_by,
        )
        for s in specs
        if s.default_key is not None
    ]


def _names(link: LinkInForce, spec: ItemSpec, view: GrantView) -> bool:
    data = link.data
    if spec.default_key is not None:
        return data.default_item == spec.default_key
    if spec.record is None or data.item_record_id is None:
        return False
    now = view.state.current_version(data.item_record_id)
    return now is not None and now.id == spec.record.id


def _covers(link: LinkInForce, period: Period) -> bool:
    note = link.fact.data
    if not isinstance(note, Note) or note.period is None:
        return False
    return note.period.start.value <= period.start and note.period.end.value >= period.end


def _rate_value(spec: ItemSpec, view: GrantView) -> tuple[Decimal | None, Finding | None]:
    math = spec.rate
    assert math is not None
    if math.rate is not None:
        return math.rate.value, None
    assert math.rate_id is not None
    term = view.state.current_version(math.rate_id)
    if term is not None and isinstance(term.data, Rate):
        return term.data.rate.value, None
    if view.state.by_id.get(math.rate_id) is not None and view.state.is_waiting(math.rate_id):
        return None, Finding(
            CHECKLIST,
            f"rate_not_confirmed:{spec.stable}",
            Bucket.NEEDS_HUMAN,
            f"{spec.needed}: the rate term it uses isn't confirmed yet.",
            [math.rate_id],
        )
    return None, None


def evaluate_item(
    spec: ItemSpec, charge: Charge, view: GrantView, waiting_removal: str | None
) -> ItemResult:
    links = [lk for lk in view.links[charge.id] if _names(lk, spec, view)]
    result = ItemResult(spec, links, filled=False, removal_waiting_id=waiting_removal)
    facts = [lk.fact.id for lk in links]
    own = [spec.record.id] if spec.record else []
    missing_text: str | None = None

    if spec.rate is not None and spec.amount_cents is not None:
        rate, problem = _rate_value(spec, view)
        if problem is not None:
            result.findings.append(problem)
        elif rate is None:
            missing_text = f"{spec.needed}: the rate isn't on file."
        else:
            quantity = spec.rate.quantity.value
            computed = int((quantity * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            if computed != spec.amount_cents:
                result.findings.append(
                    Finding(
                        CHECKLIST,
                        f"rate_math:{spec.stable}",
                        Bucket.NEEDS_HUMAN,
                        f"{spec.needed}: {quantity} times {rate} is {money(computed)}, "
                        f"not {money(spec.amount_cents)}.",
                        own,
                    )
                )
            else:
                result.filled = True
    else:
        ok = bool(links)
        if spec.amount_cents is not None:
            total = sum(lk.data.amount_cents or 0 for lk in links)
            side = compare(total, spec.amount_cents)
            if side > 0:
                result.findings.append(
                    Finding(
                        CHECKLIST,
                        f"over:{spec.stable}",
                        Bucket.NEEDS_HUMAN,
                        f"{spec.needed}: the bills linked add up to {money(total)}, "
                        + (
                            f"the opposite sign of the {money(spec.amount_cents)} it needs."
                            if (total > 0) != (spec.amount_cents > 0) and spec.amount_cents != 0
                            else f"more than {money(spec.amount_cents)}."
                        ),
                        facts + own,
                    )
                )
                ok = False
            elif side < 0:
                ok = False
                if links:
                    missing_text = (
                        f"{spec.needed}: the bills linked add up to {money(total)} "
                        f"of {money(spec.amount_cents)}."
                    )
            else:
                ok = True
        if ok and spec.period is not None and not any(_covers(lk, spec.period) for lk in links):
            ok = False
            missing_text = (
                f"{spec.needed}: no linked document's own period covers "
                f"{spec.period.start} to {spec.period.end}."
            )
        result.filled = ok and not result.findings

    if not result.filled and not result.findings:
        result.findings.append(
            Finding(
                APPROVAL if spec.is_approval else CHECKLIST,
                f"missing:{spec.stable}",
                Bucket.MISSING_EVIDENCE,
                missing_text or f"Missing: {spec.needed}.",
                facts + own,
                expected_by=spec.expected_by or charge.posting_date,
                flag_now=spec.is_approval,
            )
        )
    return result


def evaluate(charge: Charge, view: GrantView) -> ChecklistResult:
    specs, waiting = items_in_force(charge, view)
    items = [evaluate_item(s, charge, view, waiting.get(_ident(s))) for s in specs]
    findings = [f for item in items for f in item.findings]

    if not items:
        findings.append(
            Finding(
                CHECKLIST,
                "empty",
                Bucket.NEEDS_HUMAN,
                "This charge's checklist is empty, so it can't be complete.",
            )
        )
    amounts = [s.amount_cents for s in specs if s.amount_cents is not None]
    if amounts:
        total = sum(amounts)
        side = compare(total, charge.amount_cents)
        if side > 0:
            findings.append(
                Finding(
                    CHECKLIST,
                    "items_over_charge",
                    Bucket.NEEDS_HUMAN,
                    f"The checklist's amounts add up to {money(total)}, "
                    f"more than the charge's {money(charge.amount_cents)}.",
                    [s.record.id for s in specs if s.record and s.amount_cents is not None],
                )
            )
        elif side < 0:
            findings.append(
                Finding(
                    CHECKLIST,
                    "items_under_charge",
                    Bucket.MISSING_EVIDENCE,
                    f"The checklist's amounts add up to {money(total)} "
                    f"of the charge's {money(charge.amount_cents)}.",
                    [s.record.id for s in specs if s.record and s.amount_cents is not None],
                    expected_by=charge.posting_date,
                )
            )

    if not any(f.failing and f.check == CHECKLIST for f in findings):
        facts = list(
            dict.fromkeys(
                lk.fact.id for item in items for lk in item.links if not item.spec.is_approval
            )
        )
        findings.insert(
            0,
            passed(
                CHECKLIST, "Every item on the checklist is filled, and the amounts add up.", facts
            ),
        )

    entries = [
        ChecklistEntry(
            item_record_id=item.spec.record.id if item.spec.record else None,
            default_item=item.spec.default_key,
            added_by=item.spec.added_by,
            needed=item.spec.needed,
            amount_cents=item.spec.amount_cents,
            period=item.spec.period,
            expected_by=item.spec.expected_by,
            filled=item.filled,
            link_ids=tuple(lk.link.id for lk in item.links),
            removal_waiting_id=item.removal_waiting_id,
            rule_id=item.spec.rule.id if item.spec.rule is not None else None,
        )
        for item in items
    ]
    return ChecklistResult(items, entries, findings)
