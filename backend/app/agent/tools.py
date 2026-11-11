"""The agent's tools: looking (read-only) and writing (each through the write check, staged).

The model never sets a status, never marks its own record as in force and never writes the
accountant's kinds. Which writes wait is worked out by the contract code from the record, so no
tool has a "take effect" switch. Inputs are validated with pydantic here instead of the API's
strict tool mode, and a bad input goes back to the model as a tool error.

A cited value names the label of an `@label: value` line the model wrote earlier in the run; a
value read from a photo or a scan gives a pixel box instead (see citations.py).
"""

import json
import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .adapter import (
    QUESTION_TEXT,
    Answer,
    ApprovalScope,
    Author,
    BenefitGroup,
    BudgetCategory,
    Question,
    Record,
    RecordKind,
    ThreadMessage,
    applies_to_is_matchable,
    citation_of,
    likely_duplicates,
    uncited_value,
)
from .citations import (
    CitationProblem,
    image_box,
    money_sign_agrees,
    parse_date,
    parse_decimal,
    parse_money,
    parse_quantity,
    parse_rate,
    resolve_citation,
    sign_is_doubtful,
)
from .context import REPEAT_LIMIT, RunContext
from .desk import (
    charge_in_full,
    charge_lines,
    document_lines,
    money,
    record_in_full,
    record_summary,
    search_lines,
)
from .fields import FACT_FIELDS, TERM_FIELDS
from .files import CantOpen, open_file, reading_now


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Shared input pieces.


class Box(_In):
    """A box around a value on a photo or scan, in pixels on the image we sent."""

    file_id: str
    page: int = 1
    left: float
    top: float
    right: float
    bottom: float


class Value(_In):
    """One value of a record. Cite it with a label, or for a photo or scan, a box and its text."""

    field: str = Field(
        description='Its path in the record, such as "total", "items[0].amount", "period.start".'
    )
    label: str | None = Field(None, description="The label of the @label line that cites it.")
    value: str | int | float | None = Field(
        None,
        description=(
            "The normalized value: cents as an integer for money, YYYY-MM-DD for a date, a "
            "decimal for a quantity or rate (a percent as a fraction, a dollar rate in cents per "
            "unit). Leave it "
            "out for text."
        ),
    )
    text: str | None = Field(
        None, description="For a box only: the value exactly as the image shows it."
    )
    box: Box | None = None


class Quote(_In):
    """A passage an answer rests on: a label you wrote, or a saved record's cited value."""

    label: str | None = None
    record_id: str | None = None
    field: str | None = Field(
        None, description='With record_id: the cited value, for example "total".'
    )


# Writing inputs.


class WriteFact(_In):
    kind: Literal["bill", "approval", "note"]
    values: list[Value]
    label: str | None = Field(None, description="A note's plain short name.")
    replaces_id: str | None = Field(
        None, description="A correction of one of your own facts. It waits."
    )


class WriteTerm(_In):
    kind: Literal[
        "period_of_performance",
        "budget_line",
        "person",
        "approval_rule",
        "rate",
        "notice",
        "other_term",
    ]
    values: list[Value]
    category: BudgetCategory | None = Field(None, description="A budget_line's NSF category.")
    label: str | None = Field(None, description="An other_term's plain short name.")
    replaces_id: str | None = None


class LinkIn(_In):
    record_id: str = Field(description="The bill, approval or note.")
    charge_id: str
    amount_cents: int | None = Field(
        None, description="Only when the checklist item it fills carries an amount."
    )
    part: Quote | None = Field(
        None,
        description="The place in the record's file for this charge. Defaults to the bill's total.",
    )
    item_record_id: str | None = None
    default_item: str | None = None
    reason: str | None = None
    replaces_id: str | None = Field(None, description="A fix to an existing link. It waits.")


class AssignBudgetLine(_In):
    charge_id: str
    budget_line_id: str
    reason: str


class RateIn(_In):
    quantity: Value
    rate: Value | None = None
    rate_id: str | None = None


class PeriodIn(_In):
    start: date
    end: date


class AddChecklistItem(_In):
    charge_id: str
    needed: str
    amount_cents: int | None = None
    rate: RateIn | None = None
    period: PeriodIn | None = None
    expected_by: date | None = None
    nsf_standing_list: str | None = Field(
        None, description="The entry on NSF's standing list of what needs its approval."
    )
    reason: str | None = None


class RemoveChecklistItem(_In):
    charge_id: str
    item_record_id: str | None = None
    default_item: str | None = None
    reason: str


class AnswerIn(_In):
    charge_id: str
    question: Literal["allowable", "covers", "unusual_term"]
    record_id: str | None = Field(
        None, description="For covers, the approval; for unusual_term, the term."
    )
    answer: Answer
    reasoning: str
    rule: str | None = Field(None, description="The rulebook ID of the rule the answer used.")
    quotes: list[Quote] = Field(default_factory=list[Quote])
    rests_on: list[str] = Field(default_factory=list[str])


class FlagIn(_In):
    charge_id: str | None = None
    record_id: str | None = None
    file_id: str | None = None
    question: str = Field(description="Your own question, for the accountant to settle.")
    reasoning: str
    rule: str | None = None
    quotes: list[Quote] = Field(default_factory=list[Quote])
    rests_on: list[str] = Field(default_factory=list[str])


class Retract(_In):
    replaces_id: str = Field(description="Your own flag or fact, or any link. It waits.")
    reason: str


class DisputeIn(_In):
    charge_id: str
    check: str = Field(description="The check's stable ID, as the failing reason names it.")
    reasoning: str
    quotes: list[Quote] = Field(min_length=1)


class MarkDuplicate(_In):
    copy_file_id: str
    original_file_id: str
    reason: str | None = None


class PostMessage(_In):
    charge_id: str | None = None
    record_id: str | None = None
    text: str


class Finish(_In):
    summary: str = Field(description="One line on what the run did.")


# Looking inputs.


class Page(_In):
    offset: int = 0
    limit: int = Field(200, le=500)


class Search(_In):
    query: str


class ChargeRef(_In):
    charge_id: str


class RecordRef(_In):
    record_id: str


class FileRef(_In):
    file_id: str


# Building cited values.

MONEY_FIELDS = {"total", "amount", "obligated_by_amendment", "obligated_to_date"}
DATE_FIELDS = {"dated", "approved_on", "start", "end", "effective_from", "effective_to"}
DECIMAL_FIELDS = {"rate", "quantity"}
# A category the model names from the clause's own words, with the clause cited.
CATEGORY_FIELDS: dict[str, frozenset[str]] = {
    "scope": frozenset(scope.value for scope in ApprovalScope),
}
# A benefit rate's employee group (ruling 61): the model names the group, and the cited text is
# the rate agreement's own name for it. Only a rate's applies_to; an approval rule's is text.
BENEFIT_GROUPS = frozenset(group.value for group in BenefitGroup)
_PATH = re.compile(r"([A-Za-z_]+)(?:\[(\d+)\])?")


class WriteProblem(Exception):
    pass


def _leaf(path: str) -> str:
    return path.split(".")[-1].split("[")[0]


def _set_path(data: dict[str, Any], path: str, value: Any) -> None:
    target: Any = data
    parts = path.split(".")
    for n, part in enumerate(parts):
        m = _PATH.fullmatch(part)
        if not m:
            raise WriteProblem(f"'{path}' isn't a field path")
        name, index = m.group(1), m.group(2)
        last = n == len(parts) - 1
        if index is None:
            if last:
                target[name] = value
            else:
                target = target.setdefault(name, {})
        else:
            items = target.setdefault(name, [])
            i = int(index)
            while len(items) <= i:
                items.append({})
            if last:
                items[i] = value
            else:
                target = items[i]


def _normalize(
    field: str,
    raw: str | int | float | None,
    text: str,
    kind: str | None = None,
    percent: bool = False,
) -> Any:
    """The value for a field, derived from its own text (trust rules 2 and 3).

    Money, dates, rates and quantities are read from the text as the document writes it, and a
    normalized value the model gives has to equal what code reads. Text that can't be read as
    its kind of value is refused, never taken on the model's word. A text field's value is its
    text. `kind` is the record's kind, for a field whose type depends on it. `percent` says a
    bare number in a rate is a percent: a benefit rate agreement prints its rates in a column
    headed "RATE(%)", so "15.00" there is 15%.
    """
    given = None if raw is None else str(raw).strip()
    leaf = _leaf(field)
    if kind == "rate" and leaf == "applies_to":
        if given not in BENEFIT_GROUPS:
            raise WriteProblem(
                f"{field}: give the employee group as one of {', '.join(sorted(BENEFIT_GROUPS))}, "
                f"cited from the rate agreement's own name for it ('{text}'). If it's none of "
                "these, leave applies_to out and flag the term"
            )
        return given
    if leaf in MONEY_FIELDS:
        derived = parse_money(text)
        if derived is None:
            raise WriteProblem(f"{field}: '{text}' can't be read as an amount of money")
        if given is not None and given != str(derived):
            raise WriteProblem(
                f"{field}: {given} cents doesn't match its text '{text}' ({derived} cents)"
            )
        return derived
    if leaf in DATE_FIELDS:
        parsed = parse_date(text)
        if parsed is None and leaf == "effective_to":
            raise WriteProblem(
                f"{field}: '{text}' isn't a date. A rate with no end date, such as one in effect "
                "'Until Amended', leaves effective_to out"
            )
        if parsed is None:
            raise WriteProblem(f"{field}: '{text}' can't be read as a date")
        if given is not None and given != parsed.isoformat():
            raise WriteProblem(f"{field}: {given} doesn't match its text '{text}' ({parsed})")
        return parsed.isoformat()
    if leaf in CATEGORY_FIELDS:
        # A category the clause's own words show, such as an approval rule's scope: the model
        # names it, and the cited text is the clause that shows it (the main coordinator's
        # ruling). A clause that doesn't make it clear gets a flag, not a pick.
        allowed = CATEGORY_FIELDS[leaf]
        if given not in allowed:
            raise WriteProblem(
                f"{field}: give one of {', '.join(sorted(allowed))}, as the clause '{text}' shows "
                "it, or leave it out and flag the term when the clause doesn't make it clear"
            )
        return given
    if leaf in DECIMAL_FIELDS:
        number = parse_rate(text) if leaf == "rate" else parse_quantity(text)
        if number is None:
            raise WriteProblem(f"{field}: '{text}' can't be read as a {leaf}")
        if leaf == "rate" and percent and parse_decimal(text.strip()) == number:
            number = number / 100  # a bare number in a benefit rate's percent column
        if given is not None:
            claimed = parse_decimal(given)
            if claimed is None or claimed != number:
                raise WriteProblem(f"{field}: {given} doesn't match its text '{text}' ({number})")
        return str(number)
    if given is not None and given != text:
        raise WriteProblem(
            f"{field}: a text value is the text as the document writes it, '{text}', not '{given}'"
        )
    return text


def cited(
    ctx: RunContext, v: Value, kind: str | None = None, percent: bool = False
) -> dict[str, Any] | None:
    """One cited value for a record, or None when an uncited value is left out."""
    if v.box is not None:
        if not v.text:
            raise WriteProblem(f"{v.field}: a boxed value needs its text as the image shows it")
        image = ctx.images.get(v.box.file_id)
        if image is None:
            raise WriteProblem(
                f"{v.field}: file {v.box.file_id} wasn't sent as an image in this run"
            )
        try:
            location = image_box(image, v.box.left, v.box.top, v.box.right, v.box.bottom)
        except CitationProblem as error:
            raise WriteProblem(f"{v.field}: {error}") from error
        location["page"] = v.box.page
        citation: dict[str, Any] = {"file_id": v.box.file_id, "passage": None, "location": location}
        look = ctx.inputs.second_look
        citation["match"] = (
            "exact" if look is not None and look(v.box.file_id, location, v.text) else "not_found"
        )
        value = _normalize(v.field, v.value, v.text, kind, percent)
        return {"value": value, "text": v.text, "citation": citation}
    if not v.label:
        raise WriteProblem(
            f"{v.field}: name the @label line that cites it, or give a box for a photo or scan"
        )
    line = ctx.labels.get(v.label)
    if line is None:
        raise WriteProblem(
            f"{v.field}: no line '@{v.label}: ...' was written in this run. Write the label lines "
            "in a "
            "message of their own, with no tool call, then write the record"
        )
    value = _normalize(v.field, v.value, line.text, kind, percent)
    if not line.citations:
        key = (v.field, line.text)
        ctx.uncited_refusals[key] += 1
        if ctx.uncited_refusals[key] < REPEAT_LIMIT:
            raise WriteProblem(
                f"{v.field}: '{line.text}' came back with no citation. Write its @label line again "
                "citing "
                "the file, leave the value out, or flag the file"
            )
        ctx.log_event("uncited_accepted", field=v.field, text=line.text)
        return uncited_value(value, line.text)
    try:
        citation = resolve_citation(line.text, line.citations, ctx.documents)
    except CitationProblem as error:
        raise WriteProblem(f"{v.field}: {error}") from error
    passage = citation.get("passage")
    money = _leaf(v.field) in MONEY_FIELDS
    if money and passage and not money_sign_agrees(value, passage, line.text):
        # Code's reading of the money and the quote finder's reading of the page disagree on
        # the sign (PR 105's review): neither is taken on trust.
        raise WriteProblem(
            f"{v.field}: '{line.text}' reads as {value} cents, but the file signs that amount the "
            "other way. Cite the amount with the sign the file gives it"
        )
    return {"value": value, "text": line.text, "citation": citation}


def quote(ctx: RunContext, q: Quote) -> dict[str, Any]:
    """A citation for an answer or a link's part: a label's, or one reused from a saved record."""
    if q.label:
        line = ctx.labels.get(q.label)
        if line is None or not line.citations:
            raise WriteProblem(f"quote: no cited line '@{q.label}: ...' was written in this run")
        try:
            return resolve_citation(line.text, line.citations, ctx.documents)
        except CitationProblem as error:
            raise WriteProblem(f"quote: {error}") from error
    if q.record_id and q.field:
        r = ctx.state().current_version(q.record_id)
        citation = citation_of(r, q.field) if r is not None else None
        if citation is None:
            raise WriteProblem(
                f"quote: record {q.record_id} has no current cited value '{q.field}'"
            )
        return citation.model_dump(mode="json", exclude_none=True)
    raise WriteProblem("quote: give a label, or a record_id and a field")


def _values(ctx: RunContext, values: list[Value], kind: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    problems: list[str] = []
    # A rate with an employee group is a benefit rate, whose bare numbers are percents.
    percent = kind == "rate" and any(_leaf(v.field) == "applies_to" for v in values)
    for v in values:
        try:
            c = cited(ctx, v, kind, percent)
        except WriteProblem as error:
            problems.append(str(error))
            continue
        if c is not None:
            _set_path(data, v.field, c)
    if problems:
        raise WriteProblem(" ".join(p.rstrip(".") + "." for p in problems))
    return data


# Results.


def _saved(
    ctx: RunContext, data: dict[str, Any], replaces_id: str | None = None, tool: str = ""
) -> tuple[str, bool]:
    staged, problems = ctx.stage(data, replaces_id)
    if staged is None:
        return ctx.note_problems(tool, problems), True
    r = staged.record
    note = "It waits for the accountant." if staged.waits else "It takes effect."
    unconfirmed = ctx.state().unconfirmed_values(r)
    if unconfirmed:
        note += " Unconfirmed values (not matched in the file): " + ", ".join(unconfirmed) + "."
    ctx.log_event("staged", record=r)
    return f"Saved as {r.id}. {note}", False


# Handlers.


def t_write_fact(ctx: RunContext, a: WriteFact) -> tuple[str, bool]:
    data = {"kind": a.kind, **_values(ctx, a.values, a.kind)}
    if a.label is not None:
        data["label"] = a.label
    text, error = _saved(ctx, data, a.replaces_id, "write_fact")
    if error or a.kind != "bill":
        return text, error
    new = ctx.staged[-1].record
    if bill_sign_is_doubtful(new):
        text += (
            " The sign of its total can be read either way in the file (a dash with a space "
            'before the amount). Say what you read the sign from, such as "credit memo", '
            '"refund" or "amount due", in the reason of each link to this bill.'
        )
    finder = ctx.inputs.likely_duplicates or likely_duplicates
    state = ctx.state()
    ids = finder(new, state.records, ctx.inputs.files)
    dupes = [state.by_id[i] for i in ids if i in state.by_id]
    if dupes:
        text += " Bills on file that look like the same one, compare before linking: " + "; ".join(
            record_summary(r) for r in dupes
        )
    return text, False


def t_write_term(ctx: RunContext, a: WriteTerm) -> tuple[str, bool]:
    data: dict[str, Any] = {"kind": a.kind, **_values(ctx, a.values, a.kind)}
    if a.category is not None:
        data["category"] = a.category.value
    if a.label is not None:
        data["label"] = a.label
    note = ""
    if a.kind == "approval_rule" and "applies_to" in data:
        note = _check_applies_to(ctx, data["applies_to"]["text"])
    text, error = _saved(ctx, data, a.replaces_id, "write_term")
    return (text + note, error) if not error else (text, error)


def _check_applies_to(ctx: RunContext, applies_to: str) -> str:
    """An approval rule's applies_to has to name what code can match (issue #117).

    Refused twice with the reason; on the third try it's saved, since an approval rule code
    can't match still sends every charge to the accountant, and the agent is told to flag it.
    """
    i = ctx.inputs
    if applies_to_is_matchable(applies_to, ctx.records, i.files, i.grant.id):
        return ""
    key = ("applies_to", applies_to)
    ctx.uncited_refusals[key] += 1
    if ctx.uncited_refusals[key] < REPEAT_LIMIT:
        raise WriteProblem(
            f"applies_to: code can't match '{applies_to}' to one of the grant's budget lines or "
            "NSF's budget categories. Cite the narrowest words that name the budget line or "
            "category, as printed, such as 'Participant Support Costs' inside 'Funds budgeted "
            "for Participant Support Costs may not be diverted ...'; the clause stays the "
            "citation. If the clause names something narrower than any line or category, such "
            "as one kind of travel, don't widen it to the line: write it as it is and flag the "
            "term"
        )
    return (
        f" Code can't match '{applies_to}' to a budget line or category, so every charge will "
        "go to the accountant for this rule: flag the term saying so."
    )


MAIN_FIELD = {RecordKind.BILL: "total", RecordKind.APPROVAL: "covers", RecordKind.NOTE: "statement"}


def bill_sign_is_doubtful(record: Record) -> bool:
    """Whether a bill's total has a sign that its file lets be read either way."""
    data = record.data
    total = getattr(data, "total", None) if record.kind == RecordKind.BILL else None
    if total is None or total.citation is None or total.citation.passage is None:
        return False
    return sign_is_doubtful(total.citation.passage, total.text or "")


def t_link(ctx: RunContext, a: LinkIn) -> tuple[str, bool]:
    fact = ctx.state().current_version(a.record_id)
    if fact is not None and bill_sign_is_doubtful(fact) and not (a.reason or "").strip():
        raise WriteProblem(
            f"the sign of bill {fact.id}'s total can be read either way in its file, so the "
            'link\'s reason has to say what you read the sign from, such as "credit memo", '
            '"refund" or "amount due"'
        )
    if a.part is not None:
        part = quote(ctx, a.part)
    else:
        main = MAIN_FIELD.get(fact.kind) if fact is not None else None
        citation = citation_of(fact, main) if fact is not None and main else None
        if citation is None:
            raise WriteProblem(
                "give the link's part: there's no current bill, approval or note with that ID "
                "to take it from"
            )
        part = citation.model_dump(mode="json", exclude_none=True)
    data: dict[str, Any] = {
        "kind": "link",
        "record_id": a.record_id,
        "charge_id": a.charge_id,
        "part": part,
    }
    for name in ("amount_cents", "item_record_id", "default_item", "reason"):
        if getattr(a, name) is not None:
            data[name] = getattr(a, name)
    return _saved(ctx, data, a.replaces_id, "link")


def t_assign_budget_line(ctx: RunContext, a: AssignBudgetLine) -> tuple[str, bool]:
    current = [
        r
        for r in ctx.state().current()
        if r.kind == RecordKind.BUDGET_ASSIGNMENT and r.charge_id == a.charge_id
    ]
    data = {
        "kind": "budget_assignment",
        "charge_id": a.charge_id,
        "record_id": a.budget_line_id,
        "reason": a.reason,
    }
    return _saved(ctx, data, current[-1].id if current else None, "assign_budget_line")


def t_add_checklist_item(ctx: RunContext, a: AddChecklistItem) -> tuple[str, bool]:
    data: dict[str, Any] = {"kind": "checklist_item", "charge_id": a.charge_id, "needed": a.needed}
    if a.rate is not None:
        rate: dict[str, Any] = {
            "quantity": _values(ctx, [a.rate.quantity.model_copy(update={"field": "quantity"})])[
                "quantity"
            ]
        }
        if a.rate.rate is not None:
            rate["rate"] = _values(ctx, [a.rate.rate.model_copy(update={"field": "rate"})])["rate"]
        if a.rate.rate_id is not None:
            rate["rate_id"] = a.rate.rate_id
        data["rate"] = rate
    for name in ("amount_cents", "expected_by", "nsf_standing_list", "reason"):
        value = getattr(a, name)
        if value is not None:
            data[name] = value.isoformat() if isinstance(value, date) else value
    if a.period is not None:
        data["period"] = {"start": a.period.start.isoformat(), "end": a.period.end.isoformat()}
    if a.rate is not None and a.amount_cents is not None:
        quantity = Decimal(data["rate"]["quantity"]["value"])
        rate_value = data["rate"].get("rate", {}).get("value")
        product = int((quantity * Decimal(rate_value or 0)).to_integral_value())
        if rate_value is not None and product != a.amount_cents:
            raise WriteProblem(
                f"the amount {money(a.amount_cents)} isn't the quantity times the rate "
                f"({quantity} x {rate_value} = {money(product)})"
            )
    return _saved(ctx, data, None, "add_checklist_item")


def t_remove_checklist_item(ctx: RunContext, a: RemoveChecklistItem) -> tuple[str, bool]:
    data: dict[str, Any] = {
        "kind": "checklist_removal",
        "charge_id": a.charge_id,
        "reason": a.reason,
    }
    if a.item_record_id is not None:
        data["item_record_id"] = a.item_record_id
    if a.default_item is not None:
        data["default_item"] = a.default_item
    return _saved(ctx, data, None, "remove_checklist_item")


def _rule(ctx: RunContext, rule: str | None) -> None:
    if rule is not None and rule not in ctx.rulebook.ids:
        raise WriteProblem(f"'{rule}' isn't a rule ID in the {ctx.rulebook.funder} rulebook")


def _judgment_key(r: Record) -> tuple[Any, ...]:
    d = r.data
    return (
        getattr(d, "question", None),
        getattr(d, "charge_id", None),
        getattr(d, "record_id", None),
    )


# The rulebook's rule for costs after the end date, which the agent cites only in a dispute of
# code's date check (issue #119).
PERIOD_DISPUTE_RULE = "NSF-POST-END-COMMITMENTS"
PERIOD_IS_CODES = (
    "the charge's date against the period of performance is code's own check, and its bucket "
    "follows the period in force when the accountant confirms it. Answer on the cost itself; if "
    "a document shows the date check is wrong for this charge, such as an order placed before "
    "the end date, dispute the check (period_of_performance) with that quote"
)


def _not_on_the_period(ctx: RunContext, rule: str | None, rests_on: list[str]) -> None:
    """An Allowable answer doesn't rest on the period of performance (issue #119), and no
    answer or flag cites the rule kept for a dispute of the date check."""
    if rule == PERIOD_DISPUTE_RULE:
        raise WriteProblem(
            f"{PERIOD_DISPUTE_RULE} is for a dispute of the date check: {PERIOD_IS_CODES}"
        )
    state = ctx.state()
    periods = [
        i
        for i in rests_on
        if (r := state.by_id.get(i)) is not None and r.kind == RecordKind.PERIOD_OF_PERFORMANCE
    ]
    if periods:
        raise WriteProblem(
            f"this rests on the period of performance ({', '.join(periods)}): {PERIOD_IS_CODES}"
        )


def t_answer(ctx: RunContext, a: AnswerIn) -> tuple[str, bool]:
    _rule(ctx, a.rule)
    if a.question == "allowable":
        # Only Allowable: a Covers answer on a pre-award approval keeps its start date.
        _not_on_the_period(ctx, a.rule, a.rests_on)
    question = Question(a.question)
    key = (question, a.charge_id, a.record_id)
    state = ctx.state()
    current = [
        r for r in state.current() if r.kind == RecordKind.JUDGMENT and _judgment_key(r) == key
    ]
    asked = {(q.question, q.charge_id, q.record_id) for q in ctx.checks().questions}
    if key not in asked and not current:
        raise WriteProblem(
            "code hasn't asked this question about this charge, and you can only answer questions "
            "code "
            "asks. Raise anything else with flag"
        )
    data = {
        "kind": "judgment",
        "charge_id": a.charge_id,
        "question": question.value,
        "text": QUESTION_TEXT[question],
        "answer": a.answer.value,
        "reasoning": a.reasoning,
        "quotes": [quote(ctx, q) for q in a.quotes],
        "rests_on": a.rests_on,
    }
    if a.record_id is not None:
        data["record_id"] = a.record_id
    if a.rule is not None:
        data["rule"] = a.rule
    return _saved(ctx, data, current[-1].id if current else None, "answer")


def t_flag(ctx: RunContext, a: FlagIn) -> tuple[str, bool]:
    _rule(ctx, a.rule)
    if a.rule == PERIOD_DISPUTE_RULE:
        # The purchase-close-to-the-end-date flag (NSF-END-DATE-PURCHASES, decision 0015) and
        # any other flag may rest on the period; only the dispute rule is kept for disputes.
        _not_on_the_period(ctx, a.rule, [])
    data: dict[str, Any] = {
        "kind": "judgment",
        "question": "flag",
        "text": a.question,
        "answer": "unsure",
        "reasoning": a.reasoning,
        "quotes": [quote(ctx, q) for q in a.quotes],
        "rests_on": a.rests_on,
    }
    for name in ("charge_id", "record_id", "file_id", "rule"):
        if getattr(a, name) is not None:
            data[name] = getattr(a, name)
    return _saved(ctx, data, None, "flag")


def t_retract(ctx: RunContext, a: Retract) -> tuple[str, bool]:
    return _saved(ctx, {"kind": "retraction", "reason": a.reason}, a.replaces_id, "retract")


def t_dispute(ctx: RunContext, a: DisputeIn) -> tuple[str, bool]:
    data = {
        "kind": "dispute",
        "charge_id": a.charge_id,
        "check": a.check,
        "reasoning": a.reasoning,
        "quotes": [quote(ctx, q) for q in a.quotes],
    }
    return _saved(ctx, data, None, "dispute")


def t_mark_duplicate(ctx: RunContext, a: MarkDuplicate) -> tuple[str, bool]:
    data: dict[str, Any] = {
        "kind": "duplicate",
        "copy_file_id": a.copy_file_id,
        "original_file_id": a.original_file_id,
    }
    if a.reason:
        data["reason"] = a.reason
    return _saved(ctx, data, None, "mark_duplicate")


def t_post_message(ctx: RunContext, a: PostMessage) -> tuple[str, bool]:
    try:
        message = ThreadMessage(
            id=ctx.inputs.new_id(),
            workspace_id=ctx.inputs.grant.workspace_id,
            grant_id=ctx.inputs.grant.id,
            charge_id=a.charge_id,
            record_id=a.record_id,
            author=Author.AGENT,
            run_id=ctx.inputs.run_id,
            text=a.text,
            written_at=ctx.inputs.now,
        )
    except ValidationError as error:
        raise WriteProblem(str(error.errors()[0]["msg"]).removeprefix("Value error, ")) from error
    if a.charge_id and not any(c.id == a.charge_id for c in ctx.inputs.charges):
        raise WriteProblem(f"charge {a.charge_id} doesn't exist")
    if a.record_id and a.record_id not in ctx.state().by_id:
        raise WriteProblem(f"record {a.record_id} doesn't exist")
    ctx.messages_out.append(message)
    return "Posted. It's shown only if the run saves.", False


def t_list_charges(ctx: RunContext, a: Page) -> tuple[str, bool]:
    lines = charge_lines(ctx, a.offset, a.limit)
    return (
        f"Charges {a.offset + 1} to {a.offset + len(lines)} of {len(ctx.inputs.charges)}:\n"
        + "\n".join(lines),
        False,
    )


def t_list_documents(ctx: RunContext, a: Page) -> tuple[str, bool]:
    lines = document_lines(ctx, a.offset, a.limit)
    return (
        f"Documents {a.offset + 1} to {a.offset + len(lines)} of {len(ctx.inputs.files)}:\n"
        + "\n".join(lines),
        False,
    )


def t_search(ctx: RunContext, a: Search) -> tuple[str, bool]:
    lines = search_lines(ctx, a.query)
    return (
        f"{len(lines)} matching lines:\n" + "\n".join(lines[:200])
    ) if lines else "Nothing matches.", False


def t_get_charge(ctx: RunContext, a: ChargeRef) -> tuple[str, bool]:
    c = next((x for x in ctx.inputs.charges if x.id == a.charge_id), None)
    if c is None:
        return f"Charge {a.charge_id} doesn't exist.", True
    return charge_in_full(ctx, c), False


def t_get_record(ctx: RunContext, a: RecordRef) -> tuple[str, bool]:
    r = ctx.state().by_id.get(a.record_id)
    if r is None:
        return f"Record {a.record_id} doesn't exist.", True
    return record_in_full(ctx, r), False


def t_open_file(ctx: RunContext, a: FileRef) -> tuple[list[dict[str, Any]] | str, bool]:
    f = next((x for x in ctx.inputs.files if x.id == a.file_id), None)
    if f is None:
        return f"File {a.file_id} doesn't exist.", True
    try:
        opened = open_file(f, ctx.inputs.read_file(f), reading_now(ctx.inputs, f))
    except CantOpen as error:
        return str(error), True
    if opened.document is not None:
        ctx.documents.append(opened.document)
    if opened.image is not None:
        ctx.images[f.id] = opened.image
    return opened.blocks, False


Handler = Callable[[RunContext, Any], tuple[Any, bool]]

TOOLS: dict[str, tuple[type[_In], Handler, str]] = {
    "list_charges": (Page, t_list_charges, "One line per charge on the grant, a page at a time."),
    "list_documents": (
        Page,
        t_list_documents,
        "One line per document on the grant with its saved facts, a page at a time.",
    ),
    "search": (
        Search,
        t_search,
        "Keyword search over the charge and document lines. Every word has to match.",
    ),
    "get_charge": (
        ChargeRef,
        t_get_charge,
        "One charge in full: checklist, failing checks, records about it, thread.",
    ),
    "get_record": (
        RecordRef,
        t_get_record,
        "One record in full, with what it replaced and what replaced it.",
    ),
    "open_file": (
        FileRef,
        t_open_file,
        "Open a whole file. Text, email and PDFs come back as citable documents; photos as images.",
    ),
    "write_fact": (
        WriteFact,
        t_write_fact,
        "Write a bill, approval or note read from a file. Each value names its field and the "
        "@label line that cites it. The fields of each kind:\n" + FACT_FIELDS,
    ),
    "write_term": (
        WriteTerm,
        t_write_term,
        "Write a grant term read from an award notice, amendment or solicitation. Every term "
        "waits for the accountant. Each value names its field and the @label line that cites "
        "it. Every term's dated is the date the document gives itself, such as an amendment's "
        "date. A budget_line's name is the line's name as printed, without its letter or "
        "number. A condition that says who must approve what is one approval_rule, with its "
        "channel when stated; its applies_to is the narrowest words that name the budget line "
        'or NSF category, as printed ("Participant Support Costs", not "Funds budgeted for '
        'Participant Support Costs"), cited from the clause; when the clause names something '
        "narrower than any line, don't widen it: flag the term. other_term holds only what no "
        "other kind holds. The fields of "
        "each kind:\n" + TERM_FIELDS,
    ),
    "link": (
        LinkIn,
        t_link,
        "Link a bill, approval or note to a charge, filling one checklist item.",
    ),
    "assign_budget_line": (
        AssignBudgetLine,
        t_assign_budget_line,
        "Say which budget_line term a charge belongs to.",
    ),
    "add_checklist_item": (
        AddChecklistItem,
        t_add_checklist_item,
        "Add an item to a charge's evidence checklist.",
    ),
    "remove_checklist_item": (
        RemoveChecklistItem,
        t_remove_checklist_item,
        "Suggest removing a checklist item. It waits.",
    ),
    "answer": (
        AnswerIn,
        t_answer,
        "Answer a question code asked about a charge: supports, contradicts or unsure.",
    ),
    "flag": (
        FlagIn,
        t_flag,
        "Raise your own question on a charge, record or file. It's always unsure.",
    ),
    "retract": (
        Retract,
        t_retract,
        "Suggest withdrawing a link, or one of your own flags or facts. It waits.",
    ),
    "dispute": (
        DisputeIn,
        t_dispute,
        "Dispute one of code's checks on a charge, with reasoning and a quote. It waits.",
    ),
    "mark_duplicate": (
        MarkDuplicate,
        t_mark_duplicate,
        "Mark a file as a copy of one already on the grant. It waits.",
    ),
    "post_message": (
        PostMessage,
        t_post_message,
        "Post a message on a charge's or a record's thread.",
    ),
    "finish": (Finish, lambda ctx, a: ("", False), "End the run with a one-line summary."),
}


def _inline(schema: dict[str, Any]) -> dict[str, Any]:
    """The JSON schema with its $defs inlined, and pydantic's titles dropped."""
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(dict(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items() if k != "title"}  # pyright: ignore[reportUnknownVariableType]
        if isinstance(node, list):
            return [walk(x) for x in node]  # pyright: ignore[reportUnknownVariableType]
        return node

    return walk(schema)


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": description,
            "input_schema": _inline(model.model_json_schema()),
        }
        for name, (model, _, description) in TOOLS.items()
    ]


# The fields the accountant reads as the agent's own words (#275).
PROSE_FIELDS = ("reasoning", "reason", "question", "text", "needed", "label")
_SHORTEST_ID = 6  # shorter IDs (none in practice) could match ordinary words


def ids_in_prose(ctx: RunContext, args: BaseModel) -> str | None:
    """A problem when a field the accountant reads names a record, file or charge by its ID.

    An ID means nothing to the accountant ("I've filed a correction (rec-afbc6f36)"). Only the
    IDs this run knows are matched, so a ledger line number such as L-1958-0004, which the
    accountant does know, passes.
    """
    known = {r.id for r in ctx.records}
    known |= {f.id for f in ctx.inputs.files} | {c.id for c in ctx.inputs.charges}
    known = {i for i in known if len(i) >= _SHORTEST_ID}
    found: list[str] = []
    for field in PROSE_FIELDS:
        value = getattr(args, field, None)
        if not isinstance(value, str):
            continue
        named = sorted(i for i in known if i in value)
        if named:
            found.append(f"{field} ({', '.join(named)})")
    if not found:
        return None
    return (
        "The accountant reads " + "; ".join(found) + ", where an ID means nothing to them. Name "
        'each record or file by what it is, such as "the invoice from Example Lab Supply Co.", '
        '"the award letter" or "my earlier link to this charge". IDs go only in the fields that '
        "take them, such as record_id, rests_on and quotes"
    )


def run_tool(ctx: RunContext, name: str, raw_input: Any) -> tuple[Any, bool]:
    """Run one tool call. Returns the tool result's content and whether it's an error."""
    entry = TOOLS.get(name)
    if entry is None:
        return f"There's no tool named {name}.", True
    model, handler, _ = entry
    try:
        args = model.model_validate(raw_input)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()
        )
        return f"The input doesn't fit the tool: {details}", True
    problem = ids_in_prose(ctx, args)
    if problem is not None:
        return ctx.note_problems(name, [problem]), True
    try:
        return handler(ctx, args)
    except WriteProblem as error:
        return ctx.note_problems(name, [str(error)]), True


def dump(value: Any) -> str:
    return json.dumps(value, default=str)
