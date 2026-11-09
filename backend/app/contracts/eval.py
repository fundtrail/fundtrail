"""The eval answer key: what the agent should write, and each expense's bucket over time.

One JSON file per case, written before the case's documents. How each part is
matched and scored is described in docs/contracts.md.
"""

from pydantic import AwareDatetime, Field

from .base import Model
from .checks import Bucket
from .records import Answer, Question, RecordKind


class ExpectedRecord(Model):
    """A fact or a grant term the agent should read."""

    kind: RecordKind
    file: str  # the case file it cites
    # Expected values by field path: dates as YYYY-MM-DD, money in cents, text as
    # written. Fields left out aren't compared.
    fields: dict[str, str]


class ExpectedLink(Model):
    file: str  # the case file the linked fact was read from
    line_id: str  # the ledger line ID of the charge
    amount_cents: int | None = None  # for a receipt: how much of it this charge uses


class ExpectedAnswer(Model):
    line_id: str
    question: Question
    about_file: str | None = None  # for covers and unusual_term: the file the approval or term was read from
    answer: Answer


class ExpectedBucket(Model):
    line_id: str  # ledger line ID
    at: AwareDatetime  # a clock time after the arrival this bucket follows
    bucket: Bucket


class AnswerKey(Model):
    case: str
    award_number: str = Field(pattern=r"^SYN-")
    records: list[ExpectedRecord]
    links: list[ExpectedLink]
    answers: list[ExpectedAnswer]
    buckets: list[ExpectedBucket]
