"""The eval answer key (docs/contracts.md section 14, decision 0026).

One JSON (JavaScript Object Notation) file per case, written before the case's
documents. How each part is matched and scored is in that section; the scoring
of the parts decision 0026 adds is W3's. Every list 0026 adds defaults to empty,
so a key written before it stays valid.
"""

from typing import Literal

from pydantic import Field

from .base import Cents, Id, Model, Text, UtcDatetime
from .buckets import Bucket
from .records import Answer, Question, RecordKind


class ExpectedRecord(Model):
    """A fact or a grant term the agent should read."""

    kind: RecordKind
    file: Text  # the case file it cites
    # Expected values by field path, as strings: dates as YYYY-MM-DD, money in
    # cents, text as written. Fields left out aren't compared.
    fields: dict[str, str]
    # Decision 0026: the field paths whose values shouldn't be found in the file.
    unconfirmed: tuple[str, ...] = ()


class ExpectedLink(Model):
    file: Text  # the case file the linked fact was read from
    line_id: Id  # the charge's ledger line ID, on the case's grant
    amount_cents: Cents | None = None  # for a bill


class ExpectedBudgetLine(Model):
    line_id: Id
    budget_line: Text  # the budget_line's name as the award letter writes it


class ExpectedAnswer(Model):
    line_id: Id
    question: Question
    # For covers and unusual_term: the file the approval or term was read from.
    about_file: str | None = None
    answer: Answer


class ExpectedBucket(Model):
    line_id: Id
    at: UtcDatetime  # a clock time after the arrival it follows
    # Decision 0026: a fully reversed charge is expected as "reversed", counted on its
    # own and never as Evidence complete. An accepted charge expects the bucket it kept.
    bucket: Bucket | Literal["reversed"]


class ExpectedFailingChecks(Model):
    """Which checks fail for a charge at a time (decision 0026, item 2)."""

    line_id: Id
    at: UtcDatetime
    checks: tuple[Id, ...]  # the checks' stable IDs; empty when none fails


class ExpectedChecklistItem(Model):
    """A checklist item the agent should add to a charge (decision 0026, item 6)."""

    line_id: Id
    # Expected values of the checklist_item's fields, as strings like a record's.
    fields: dict[str, str]


class ExpectedSuggestion(Model):
    """A suggestion the agent should make: a fix, a dispute, a duplicate mark, and so on."""

    kind: RecordKind  # the kind of the waiting record, for example dispute or correction
    line_id: Id | None = None  # the charge it touches, when it touches one
    file: str | None = None  # the case file it's about, when it's about one
    fields: dict[str, str] = Field(default_factory=dict[str, str])


class AnswerKey(Model):
    case: Text
    award_number: str = Field(pattern=r"^SYN-")
    records: tuple[ExpectedRecord, ...]
    links: tuple[ExpectedLink, ...]
    budget_lines: tuple[ExpectedBudgetLine, ...]
    answers: tuple[ExpectedAnswer, ...]
    buckets: tuple[ExpectedBucket, ...]
    failing_checks: tuple[ExpectedFailingChecks, ...] = ()
    checklist_items: tuple[ExpectedChecklistItem, ...] = ()
    suggestions: tuple[ExpectedSuggestion, ...] = ()
