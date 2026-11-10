"""What accepting one of the agent's waiting records changes, worded by code (issue 114).

Wording that tells the accountant what a decision will change comes from code, not
from each screen, like status text and `history_line`. The API puts it on each
`SuggestionView`, and the evidence report can use the same words. It's pure.

A change has a title (what accepting does, in one line), and when the record
replaces one, what's in force now and what the agent suggests instead. The agent's
own reason stays on the record.
"""

from collections.abc import Iterable

from app.checks.text import day, money
from app.contracts.api import SuggestionChange
from app.contracts.charges import Charge
from app.contracts.checks import ChecklistEntry
from app.contracts.evidence import EvidenceFile
from app.contracts.records import (
    Answer,
    Approval,
    ApprovalRule,
    Bill,
    BudgetAssignment,
    BudgetLine,
    ChecklistItem,
    ChecklistRemoval,
    Correction,
    Dispute,
    Duplicate,
    Judgment,
    Link,
    Note,
    Notice,
    OtherTerm,
    PeriodOfPerformance,
    Person,
    Question,
    Rate,
    Record,
    RecordKind,
    Remainder,
    citations,
)

KIND_LABELS = {
    RecordKind.PERIOD_OF_PERFORMANCE: "period of performance",
    RecordKind.BUDGET_LINE: "budget line",
    RecordKind.PERSON: "person",
    RecordKind.APPROVAL_RULE: "approval rule",
    RecordKind.RATE: "rate",
    RecordKind.NOTICE: "funding notice",
    RecordKind.OTHER_TERM: "other term",
    RecordKind.BILL: "bill",
    RecordKind.APPROVAL: "approval",
    RecordKind.NOTE: "note",
    RecordKind.LINK: "link",
    RecordKind.BUDGET_ASSIGNMENT: "budget line assignment",
    RecordKind.JUDGMENT: "answer",
    RecordKind.CHECKLIST_ITEM: "checklist item",
    RecordKind.CHECKLIST_REMOVAL: "checklist removal",
    RecordKind.DISPUTE: "dispute",
    RecordKind.DUPLICATE: "duplicate mark",
    RecordKind.CORRECTION: "correction",
    RecordKind.REMAINDER: "remainder",
}

ANSWER_LABELS = {
    Answer.SUPPORTS: "Supports",
    Answer.CONTRADICTS: "Contradicts",
    Answer.UNSURE: "Unsure",
}
QUESTION_LABELS = {
    Question.ALLOWABLE: "Allowable",
    Question.COVERS: "Covers",
    Question.UNUSUAL_TERM: "Unusual term",
    Question.FLAG: "the agent's flag",
}


class _Lookup:
    def __init__(
        self,
        records: Iterable[Record],
        files: Iterable[EvidenceFile],
        charges: Iterable[Charge],
        checklist: Iterable[ChecklistEntry],
    ):
        self.records = {r.id: r for r in records}
        self.files = {f.id: f for f in files}
        self.charges = {c.id: c for c in charges}
        self.checklist = list(checklist)

    def line(self, charge_id: str | None) -> str:
        charge = self.charges.get(charge_id or "")
        return f"ledger line {charge.ledger_line_id}" if charge else "a charge"

    def name(self, record: Record | None) -> str:
        """A record by its kind and its file, for example "bill, invoice_1001.txt"."""
        if record is None:
            return "a record"
        kind = KIND_LABELS.get(record.kind, record.kind.value.replace("_", " "))
        file_id = next((c.file_id for c in citations(record.data)), None)
        file = self.files.get(file_id or "")
        return f"{kind}, {file.name}" if file else kind


def _summary(record: Record, look: _Lookup) -> str:
    """One record in a few words, for "now" and "suggested"."""
    data = record.data
    if isinstance(data, Judgment):
        return ANSWER_LABELS[data.answer]
    if isinstance(data, Link):
        target = look.name(look.records.get(data.record_id))
        to = f"{target} for {look.line(data.charge_id)}"
        return to if data.amount_cents is None else f"{to}, {money(data.amount_cents)}"
    if isinstance(data, BudgetAssignment):
        line = look.records.get(data.record_id)
        return (
            line.data.name.value if line and isinstance(line.data, BudgetLine) else "a budget line"
        )
    if isinstance(data, PeriodOfPerformance):
        end = day(data.end.value)
        return f"{day(data.start.value)} to {end}" if data.start else f"ends {end}"
    if isinstance(data, ChecklistItem):
        return data.needed
    if isinstance(data, Bill):
        return f"{look.name(record)}, {money(data.total.value)}"
    # Terms and facts by what they say, so a correction's two sides read differently.
    if isinstance(data, BudgetLine):
        return f"{data.name.value}: {money(data.amount.value)}"
    if isinstance(data, Person):
        email = f", {data.email.value}" if data.email else ""
        return f"{data.name.value}, {data.role.value}{email}"
    if isinstance(data, ApprovalRule):
        via = f", through {data.channel.value}" if data.channel else ""
        return f"{data.applies_to.value}: approved by {data.approver.value}{via}"
    if isinstance(data, Rate):
        return f"{data.name.value}: {data.rate.text or data.rate.value}"
    if isinstance(data, Notice):
        parts = [f"amendment {data.amendment_number.value}, {data.amendment_type.value}"]
        if data.obligated_to_date:
            parts.append(f"total obligated {money(data.obligated_to_date.value)}")
        return ", ".join(parts)
    if isinstance(data, OtherTerm | Note):
        return f"{data.label}: {data.statement.value}"
    if isinstance(data, Approval):
        return f"approval from {data.approver_email.value} for {data.covers.value}"
    return look.name(record)


def _item_needed(data: ChecklistRemoval, look: _Lookup, record_id: str) -> str:
    entry = next((e for e in look.checklist if e.removal_waiting_id == record_id), None)
    if entry is not None:
        return entry.needed
    item = look.records.get(data.item_record_id or "")
    if item is not None and isinstance(item.data, ChecklistItem):
        return item.data.needed
    return data.default_item or "an item"


def suggestion_change(
    record: Record,
    replaces: Record | None = None,
    *,
    records: Iterable[Record] = (),
    files: Iterable[EvidenceFile] = (),
    charges: Iterable[Charge] = (),
    checklist: Iterable[ChecklistEntry] = (),
) -> SuggestionChange:
    """What accepting one of the agent's waiting records changes.

    `records`, `files` and `charges` let it name what the record points to;
    `checklist` is the charge's checklist, which names a default item a removal
    names by its key.
    """
    look = _Lookup(records, files, charges, checklist)
    data = record.data
    if isinstance(data, ChecklistRemoval):
        return SuggestionChange(
            title=f"Remove “{_item_needed(data, look, record.id)}” from the checklist of "
            f"{look.line(data.charge_id)}"
        )
    if record.kind == RecordKind.RETRACTION:
        if replaces is not None and isinstance(replaces.data, Judgment):
            if replaces.data.question == Question.FLAG:
                return SuggestionChange(title="Withdraw the agent's flag", now=replaces.data.text)
        what = KIND_LABELS.get(replaces.kind, "record") if replaces else "record"
        return SuggestionChange(
            title=f"Withdraw the {what}",
            now=_summary(replaces, look) if replaces else None,
        )
    if isinstance(data, Duplicate):
        copy = look.files.get(data.copy_file_id)
        original = look.files.get(data.original_file_id)
        return SuggestionChange(
            title=f"Mark {copy.name if copy else 'a file'} as a copy of "
            f"{original.name if original else 'another file'}"
        )
    if isinstance(data, Dispute):
        return SuggestionChange(
            title=f"Accept the agent's dispute of the {data.check.replace('_', ' ')} check "
            f"on {look.line(data.charge_id)}, with its reasoning as the note"
        )
    if isinstance(data, Correction):
        title = (
            f"Count {look.line(data.charge_id)} as correcting ledger line {data.corrects_line_id}"
        )
        line = look.charges.get(data.charge_id)
        # Ledger line IDs are unique per grant (ruling 56), so the line it corrects is
        # looked up among the suggestion's own grant's charges only.
        corrected = next(
            (
                c
                for c in look.charges.values()
                if c.grant_id == record.grant_id and c.ledger_line_id == data.corrects_line_id
            ),
            None,
        )
        # Decision 0020: a line nets into the one it corrects only when the signs are
        # opposite; a line that adds money stands on its own.
        if line and corrected and line.amount_cents * corrected.amount_cents < 0:
            title += ", and net the two"
        return SuggestionChange(title=title)
    if isinstance(data, Remainder):
        bill = look.records.get(data.record_id)
        file_id = next((c.file_id for c in citations(bill.data)), None) if bill else None
        file = look.files.get(file_id or "")
        named = f"the bill in {file.name}" if file else "the bill"
        return SuggestionChange(
            title=f"Record that the rest of {named} belongs to award {data.other_award.value}"
        )
    if isinstance(data, Judgment) and replaces is not None:
        question = QUESTION_LABELS[data.question]
        return SuggestionChange(
            title=f"Change the {question} answer on {look.line(data.charge_id)}",
            now=_summary(replaces, look),
            suggested=_summary(record, look),
        )
    if replaces is not None:
        kind = KIND_LABELS.get(record.kind, record.kind.value)
        return SuggestionChange(
            title=f"Change the {kind}",
            now=_summary(replaces, look),
            suggested=_summary(record, look),
        )
    if isinstance(data, Link):
        return SuggestionChange(
            title=f"Add a link for {look.line(data.charge_id)}", suggested=_summary(record, look)
        )
    if isinstance(data, Judgment):
        if data.question == Question.FLAG:
            return SuggestionChange(title="Raise the agent's flag", suggested=data.text)
        return SuggestionChange(
            title=f"Answer {QUESTION_LABELS[data.question]} on {look.line(data.charge_id)}",
            suggested=_summary(record, look),
        )
    kind = KIND_LABELS.get(record.kind, record.kind.value)
    return SuggestionChange(title=f"Add the {kind}", suggested=_summary(record, look))
