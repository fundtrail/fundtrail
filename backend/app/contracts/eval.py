"""The eval answer key: what the agent should write, and each expense's bucket over time.

One JSON file per case, written before the case's documents. How a record is
matched is described in docs/contracts.md.
"""

from pydantic import AwareDatetime, Field

from .base import Model
from .checks import Bucket
from .records import RecordKind


class ExpectedRecord(Model):
    kind: RecordKind
    file: str  # the case file the record cites; for a link, the file it links
    # Expected values by field name: dates as YYYY-MM-DD, money in cents, text as
    # written. For a link: {"charge": "<ledger line ID>"}. Fields left out aren't compared.
    fields: dict[str, str]


class ExpectedBucket(Model):
    line_id: str  # ledger line ID
    at: AwareDatetime  # a clock time after the arrival this bucket follows
    bucket: Bucket


class AnswerKey(Model):
    case: str
    award_number: str = Field(pattern=r"^SYN-")
    records: list[ExpectedRecord]
    buckets: list[ExpectedBucket]
