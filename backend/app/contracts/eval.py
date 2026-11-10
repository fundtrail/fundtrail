"""The eval answer key (docs/contracts.md section 14).

One JSON file per case, written before the case's documents. How each part is
matched and scored is in that section.
"""

from pydantic import Field

from .base import Cents, Id, Model, Text, UtcDatetime
from .checks import Bucket
from .records import Answer, Question, RecordKind


class ExpectedRecord(Model):
    """A fact or a grant term the agent should read."""

    kind: RecordKind
    file: Text  # the case file it cites
    # Expected values by field path, as strings: dates as YYYY-MM-DD, money in
    # cents, text as written. Fields left out aren't compared.
    fields: dict[str, str]


class ExpectedLink(Model):
    file: Text  # the case file the linked fact was read from
    line_id: Id  # the charge's ledger line ID
    amount_cents: Cents | None = None  # for a bill


class ExpectedBudgetLine(Model):
    line_id: Id
    budget_line: Text  # the budget_line's name as the award letter writes it


class ExpectedAnswer(Model):
    line_id: Id
    question: Question
    about_file: str | None = None  # for covers and unusual_term: the file the approval or term was read from
    answer: Answer


class ExpectedBucket(Model):
    line_id: Id
    at: UtcDatetime  # a clock time after the arrival it follows
    bucket: Bucket


class AnswerKey(Model):
    case: Text
    award_number: str = Field(pattern=r"^SYN-")
    records: list[ExpectedRecord]
    links: list[ExpectedLink]
    budget_lines: list[ExpectedBudgetLine]
    answers: list[ExpectedAnswer]
    buckets: list[ExpectedBucket]
