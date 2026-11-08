"""Records: the single source of truth.

A record is never edited. A correction is a new record whose replaces_id points
to the old one, and the old one stays. The agent and the accountant both write
records. Every record says who wrote it and when, using the workspace clock.

A fact pulled from a document is a Cited value: the value, the text it was read
from, and a citation to the passage. The agent never writes a status; statuses
come from the checks (see checks.py).
"""

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, Field, model_validator

from .base import Model

# Citations. Locations use the Anthropic API's own names and counting, so the
# agent copies them over unchanged.


class CharLocation(Model):
    """Plain text: character indexes from 0, end exclusive."""

    type: Literal["char_location"] = "char_location"
    start_char_index: int = Field(ge=0)
    end_char_index: int = Field(ge=0)


class PageLocation(Model):
    """A PDF with real text: page numbers from 1, end exclusive."""

    type: Literal["page_location"] = "page_location"
    start_page_number: int = Field(ge=1)
    end_page_number: int = Field(ge=1)


class ContentBlockLocation(Model):
    """A custom content document: block indexes from 0, end exclusive."""

    type: Literal["content_block_location"] = "content_block_location"
    start_block_index: int = Field(ge=0)
    end_block_index: int = Field(ge=0)


class ImageBox(Model):
    """A photo or scan: the box Claude estimated around the quote. It's approximate.

    Fractions of the page's width and height, measured from its top left corner.
    """

    type: Literal["image_box"] = "image_box"
    page: int = Field(default=1, ge=1)  # 1 for a single image
    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


Location = Annotated[
    CharLocation | PageLocation | ContentBlockLocation | ImageBox,
    Field(discriminator="type"),
]


class Citation(Model):
    file_id: str  # the evidence file
    # The API's cited_text, copied as is. The model never types it. None for
    # photos and scans, which the API can't cite.
    passage: str | None
    location: Location

    @model_validator(mode="after")
    def _passage_matches_location(self):
        if (self.passage is None) != isinstance(self.location, ImageBox):
            raise ValueError("an image_box citation has no passage, and every other citation has one")
        return self


T = TypeVar("T")


class Cited(Model, Generic[T]):
    """A value and where it came from."""

    value: T
    # The value exactly as the source writes it, for example "January 31, 2027".
    # Code checks that it appears in the citation's passage (trust rule 2).
    text: str | None = None
    citation: Citation | None = None  # None when a person entered the value

    @model_validator(mode="after")
    def _text_with_citation(self):
        if self.citation is not None and not self.text:
            raise ValueError("a cited value needs the text it was read from")
        return self


class CitedText(Cited[str]):
    pass


class CitedDate(Cited[date]):
    pass


class CitedMoney(Cited[int]):
    """value is in cents."""


# Record kinds.


class RecordKind(StrEnum):
    # Grant terms, from the award letter and amendments
    PERIOD_OF_PERFORMANCE = "period_of_performance"
    BUDGET_LINE = "budget_line"
    PERSON = "person"
    APPROVAL_RULE = "approval_rule"
    # Facts from evidence
    LINK = "link"
    RECEIPT = "receipt"
    APPROVAL = "approval"
    # Written only by a person
    SPLIT = "split"
    CONFIRMATION = "confirmation"
    SIGN_OFF = "sign_off"
    # Either
    RETRACTION = "retraction"


TERM_KINDS = frozenset(
    {RecordKind.PERIOD_OF_PERFORMANCE, RecordKind.BUDGET_LINE, RecordKind.PERSON, RecordKind.APPROVAL_RULE}
)
PERSON_ONLY_KINDS = frozenset({RecordKind.SPLIT, RecordKind.CONFIRMATION, RecordKind.SIGN_OFF})


class _Term(Model):
    # The date the source document gives itself, such as an amendment's date.
    # An amendment isn't a correction: it's a new term, and checks use this
    # date to decide which terms are in force.
    dated: CitedDate | None = None


class PeriodOfPerformance(_Term):
    kind: Literal[RecordKind.PERIOD_OF_PERFORMANCE] = RecordKind.PERIOD_OF_PERFORMANCE
    start: CitedDate | None = None  # an amendment may state only the new end date
    end: CitedDate


class BudgetLine(_Term):
    kind: Literal[RecordKind.BUDGET_LINE] = RecordKind.BUDGET_LINE
    name: CitedText
    amount: CitedMoney


class Person(_Term):
    """Someone named in the award letter, or a known sender the accountant adds."""

    kind: Literal[RecordKind.PERSON] = RecordKind.PERSON
    name: CitedText
    email: CitedText | None = None
    # As the document states it, for example "Program Officer". Code maps it to a role.
    role: CitedText


class ApprovalRule(_Term):
    kind: Literal[RecordKind.APPROVAL_RULE] = RecordKind.APPROVAL_RULE
    applies_to: CitedText  # the budget line or kind of cost, as stated
    approver: CitedText  # who must approve, as stated, for example "Program Officer"
    channel: CitedText | None = None  # how, as stated, for example "Research.gov"


class Link(Model):
    """Links an evidence file to the charge it supports.

    Facts from that file then apply to that charge. A file with no link and no
    term citing it is unlinked, and waits.
    """

    kind: Literal[RecordKind.LINK] = RecordKind.LINK
    file_id: str
    charge_id: str


class Receipt(Model):
    """Facts from a receipt or an invoice."""

    kind: Literal[RecordKind.RECEIPT] = RecordKind.RECEIPT
    vendor: CitedText | None = None
    amount: CitedMoney | None = None
    dated: CitedDate | None = None
    description: CitedText | None = None


class Approval(Model):
    """An approval found in evidence. Code decides the approver's role."""

    kind: Literal[RecordKind.APPROVAL] = RecordKind.APPROVAL
    # The approver's address. For a forwarded email, the original sender's.
    approver_email: CitedText
    approver_name: CitedText | None = None
    approved_on: CitedDate | None = None
    covers: CitedText  # what it approves, as stated
    # The channel the document names, such as "Research.gov". None for a plain email.
    channel: CitedText | None = None


class SplitPart(Model):
    charge_id: str
    units: Decimal = Field(gt=0)


class Split(Model):
    """How one shared cost is split across charges, often on different grants.

    "56 of 96 samples" is two parts, 56 and 40, with unit "samples". Code does the math.
    """

    kind: Literal[RecordKind.SPLIT] = RecordKind.SPLIT
    unit: str = Field(min_length=1)
    parts: list[SplitPart] = Field(min_length=2)
    note: str | None = None


class Confirmation(Model):
    """The accountant confirms term records the agent wrote. Checks use only confirmed terms."""

    kind: Literal[RecordKind.CONFIRMATION] = RecordKind.CONFIRMATION
    record_ids: list[str] = Field(min_length=1)


class SignOff(Model):
    """The accountant signs off on the grant's closeout packet."""

    kind: Literal[RecordKind.SIGN_OFF] = RecordKind.SIGN_OFF
    note: str | None = None


class Retraction(Model):
    """Replaces a record with nothing, for example a wrong link."""

    kind: Literal[RecordKind.RETRACTION] = RecordKind.RETRACTION
    reason: str | None = None


RecordData = Annotated[
    PeriodOfPerformance
    | BudgetLine
    | Person
    | ApprovalRule
    | Link
    | Receipt
    | Approval
    | Split
    | Confirmation
    | SignOff
    | Retraction,
    Field(discriminator="kind"),
]


class Author(StrEnum):
    AGENT = "agent"
    USER = "user"


class Record(Model):
    id: str
    workspace_id: str
    # For a split, the grant it was entered from. Its parts may be on other grants.
    grant_id: str
    author: Author
    author_user_id: str | None = None  # set exactly when author is "user"
    written_at: AwareDatetime  # the workspace clock's "now" when it was written
    replaces_id: str | None = None  # the record this one corrects; the old one stays
    data: RecordData

    @model_validator(mode="after")
    def _rules(self):
        if (self.author == Author.USER) != (self.author_user_id is not None):
            raise ValueError("author_user_id is set exactly when author is 'user'")
        if self.replaces_id == self.id:
            raise ValueError("a record can't replace itself")
        if self.data.kind == RecordKind.RETRACTION and self.replaces_id is None:
            raise ValueError("a retraction must replace a record")
        if self.author == Author.AGENT:
            if self.data.kind in PERSON_ONLY_KINDS:
                raise ValueError(f"only a person writes a {self.data.kind} record")
            for name, value in self.data:
                if isinstance(value, Cited) and value.citation is None:
                    raise ValueError(f"the agent's value '{name}' needs a citation")
        return self


def current_records(records: Iterable[Record]) -> list[Record]:
    """The records nothing replaces, minus retractions.

    Pass only the records visible at the clock's "now".
    """
    records = list(records)
    replaced = {r.replaces_id for r in records if r.replaces_id}
    return [r for r in records if r.id not in replaced and r.data.kind != RecordKind.RETRACTION]


def confirmed_term_ids(records: Iterable[Record]) -> set[str]:
    """IDs of current term records the checks may use.

    A term the agent wrote counts once a current confirmation lists it. A term a
    person wrote needs no confirmation.
    """
    current = current_records(records)
    confirmed = {i for r in current if r.data.kind == RecordKind.CONFIRMATION for i in r.data.record_ids}
    return {r.id for r in current if r.data.kind in TERM_KINDS and (r.author == Author.USER or r.id in confirmed)}
