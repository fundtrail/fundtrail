"""Records: everything the agent and the accountant write.

A record is never edited. A correction is a new record whose replaces_id points
to the old one, and the old one stays. Every record says who wrote it and when,
using the workspace clock.

Kinds, by what they hold:
- grant terms, read from the award letter and amendments: period_of_performance,
  budget_line, person, approval_rule, other_term
- facts read from evidence: receipt, approval, note
- link: ties a fact to the charge it pays for, approves or explains
- judgment: an answer to one question about one charge
- written only by the accountant: confirmation, sign_off
- retraction: replaces a record with nothing

Some of the agent's records count only once the accountant confirms them: its
grant terms, and any record that replaces an existing one (a suggested fix).
The one exception is a judgment replacing the agent's own earlier judgment.
See effective_records().
"""

from collections.abc import Iterable, Iterator, Sequence
from datetime import date
from enum import StrEnum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from .base import Model
from .charges import Charge

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
    """A photo or scan: the box the agent estimated around the quote. It's approximate.

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
    """A place in an evidence file: what gets highlighted when the user opens it."""

    file_id: str
    # The API's cited_text, copied as is. The agent never types it. None for
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
    # It has to appear in the citation's passage (trust rule 2).
    text: str | None = None
    citation: Citation | None = None  # None when the accountant entered the value

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
    """value is in cents, negative for a credit."""


# Record kinds.


class RecordKind(StrEnum):
    # Grant terms
    PERIOD_OF_PERFORMANCE = "period_of_performance"
    BUDGET_LINE = "budget_line"
    PERSON = "person"
    APPROVAL_RULE = "approval_rule"
    OTHER_TERM = "other_term"
    # Facts from evidence
    RECEIPT = "receipt"
    APPROVAL = "approval"
    NOTE = "note"
    # Links and answers
    LINK = "link"
    JUDGMENT = "judgment"
    # Written only by the accountant
    CONFIRMATION = "confirmation"
    SIGN_OFF = "sign_off"
    # Either
    RETRACTION = "retraction"


TERM_KINDS = frozenset(
    {
        RecordKind.PERIOD_OF_PERFORMANCE,
        RecordKind.BUDGET_LINE,
        RecordKind.PERSON,
        RecordKind.APPROVAL_RULE,
        RecordKind.OTHER_TERM,
    }
)
FACT_KINDS = frozenset({RecordKind.RECEIPT, RecordKind.APPROVAL, RecordKind.NOTE})  # what a link points to
MONEY_KINDS = frozenset({RecordKind.RECEIPT})  # a link to one of these carries an amount
PERSON_ONLY_KINDS = frozenset({RecordKind.CONFIRMATION, RecordKind.SIGN_OFF})


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


class OtherTerm(_Term):
    """Anything an award letter or amendment says that no other term kind holds.

    For example a principal investigator on leave with an acting one named, a
    subaward added, or pre-award costs authorized. It's in force from its own
    date on, and the agent reads any dates inside the statement.
    """

    kind: Literal[RecordKind.OTHER_TERM] = RecordKind.OTHER_TERM
    label: str = Field(min_length=1)  # a short name, for example "PI on leave"
    statement: CitedText


class ReceiptItem(Model):
    description: CitedText
    amount: CitedMoney


class Receipt(Model):
    """Facts from a receipt, an invoice or a credit memo. A credit has a negative total."""

    kind: Literal[RecordKind.RECEIPT] = RecordKind.RECEIPT
    vendor: CitedText | None = None
    total: CitedMoney
    dated: CitedDate | None = None
    description: CitedText | None = None
    items: list[ReceiptItem] = Field(default_factory=list)  # when the receipt is itemized


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


class Note(Model):
    """Evidence that explains a charge without billing or approving it.

    For example a payment notice: "payment X covered invoice A and $1,000 of invoice B".
    """

    kind: Literal[RecordKind.NOTE] = RecordKind.NOTE
    label: str = Field(min_length=1)
    statement: CitedText


class Link(Model):
    """Ties a fact to a charge.

    A receipt link means "pays for" and carries an amount: how much of the
    receipt this charge uses. An approval link means "approves" and a note link
    means "explains"; neither has an amount. The part is the place in the
    record's own file that pertains to this charge, highlighted when the user
    opens it. For a whole receipt it's the total's citation.
    """

    kind: Literal[RecordKind.LINK] = RecordKind.LINK
    record_id: str  # the receipt, approval or note
    charge_id: str
    amount_cents: int | None = None  # receipts only; negative for a credit
    part: Citation | None = None  # the agent always gives one
    reason: str | None = None  # one line on why they match


class Question(StrEnum):
    ALLOWABLE = "allowable"  # Is this cost necessary and reasonable, and is it for this project?
    COVERS = "covers"  # Does this approval cover this charge?
    UNUSUAL_TERM = "unusual_term"  # Does this other_term change anything for this charge?
    FLAG = "flag"  # the agent's own question, for anything no other question covers


QUESTIONS_ABOUT_A_RECORD = frozenset({Question.COVERS, Question.UNUSUAL_TERM})


class Answer(StrEnum):
    SUPPORTS = "supports"  # the question passes
    CONTRADICTS = "contradicts"  # Possible conflict
    UNSURE = "unsure"  # Needs a human


class Judgment(Model):
    """An answer to one question about one charge, with the reasoning behind it.

    Code asks the questions; the agent or the accountant answers. The reasoning
    is shown in the app and the evidence report, labeled with who wrote it.
    """

    kind: Literal[RecordKind.JUDGMENT] = RecordKind.JUDGMENT
    charge_id: str
    question: Question
    record_id: str | None = None  # the approval (covers) or the other_term (unusual_term)
    text: str = Field(min_length=1)  # the question as asked; for a flag, the agent's own question
    answer: Answer
    reasoning: str = Field(min_length=1)
    quotes: list[Citation] = Field(default_factory=list)
    rests_on: list[str] = Field(default_factory=list)  # IDs of the records the answer depends on

    @model_validator(mode="after")
    def _shape(self):
        if self.question in QUESTIONS_ABOUT_A_RECORD and self.record_id is None:
            raise ValueError(f"a {self.question} question names the record it's about")
        if self.question == Question.FLAG and self.answer != Answer.UNSURE:
            raise ValueError("a flag's answer is unsure: it can only send a charge to the accountant")
        return self


class Decision(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class Confirmation(Model):
    """The accountant confirms or rejects records that wait for them.

    That's the agent's grant terms and its suggested fixes. The latest decision
    on a record wins.
    """

    kind: Literal[RecordKind.CONFIRMATION] = RecordKind.CONFIRMATION
    record_ids: list[str] = Field(min_length=1)
    decision: Decision = Decision.CONFIRMED


class SignOff(Model):
    """The accountant signs off on the grant's evidence report."""

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
    | OtherTerm
    | Receipt
    | Approval
    | Note
    | Link
    | Judgment
    | Confirmation
    | SignOff
    | Retraction,
    Field(discriminator="kind"),
]


class Author(StrEnum):
    AGENT = "agent"
    USER = "user"


def cited_values(model: BaseModel, prefix: str = "") -> Iterator[tuple[str, Cited]]:
    """Every cited value inside a record's data, with its path, for example "items[0].amount"."""
    for name, value in model:
        path = f"{prefix}{name}"
        if isinstance(value, Cited):
            yield path, value
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, Cited):
                    yield f"{path}[{i}]", item
                elif isinstance(item, BaseModel) and not isinstance(item, Citation):
                    yield from cited_values(item, f"{path}[{i}].")


class Record(Model):
    id: str
    workspace_id: str
    # For a link or a judgment, the grant it was written on. Its charge may be on
    # another grant in the same workspace.
    grant_id: str
    author: Author
    author_user_id: str | None = None  # set exactly when author is "user"
    written_at: AwareDatetime  # the workspace clock's "now" when it was written
    replaces_id: str | None = None  # the record this one corrects; the old one stays
    data: RecordData

    @property
    def charge_id(self) -> str | None:
        """The charge a link or judgment is about. A real column in the database."""
        return getattr(self.data, "charge_id", None)

    @property
    def record_id(self) -> str | None:
        """The record a link or judgment points to. A real column in the database."""
        return getattr(self.data, "record_id", None)

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
                raise ValueError(f"only the accountant writes a {self.data.kind} record")
            for path, value in cited_values(self.data):
                if value.citation is None:
                    raise ValueError(f"the agent's value '{path}' needs a citation")
            if isinstance(self.data, Link) and self.data.part is None:
                raise ValueError("the agent's link needs a part")
        return self


# What counts. Pass only the records visible at the clock's "now".


def needs_confirmation(record: Record) -> bool:
    """Whether a record counts only once the accountant confirms it."""
    if record.author != Author.AGENT:
        return False
    if record.data.kind in TERM_KINDS:
        return True
    return record.replaces_id is not None and record.data.kind != RecordKind.JUDGMENT


def decisions(records: Iterable[Record]) -> dict[str, Decision]:
    """The accountant's latest decision on each record, from their current confirmations."""
    by_user = [r for r in records if r.author == Author.USER]
    replaced = {r.replaces_id for r in by_user if r.replaces_id}
    latest: dict[str, Decision] = {}
    for r in sorted(by_user, key=lambda r: r.written_at):
        if r.id not in replaced and isinstance(r.data, Confirmation):
            for record_id in r.data.record_ids:
                latest[record_id] = r.data.decision
    return latest


def effective_records(records: Iterable[Record]) -> list[Record]:
    """The records that count: all except the agent's records still waiting for, or rejected by, the accountant."""
    records = list(records)
    decided = decisions(records)
    return [r for r in records if not needs_confirmation(r) or decided.get(r.id) == Decision.CONFIRMED]


def current_records(records: Iterable[Record]) -> list[Record]:
    """Effective records that no effective record replaces, minus retractions."""
    effective = effective_records(records)
    replaced = {r.replaces_id for r in effective if r.replaces_id}
    return [r for r in effective if r.id not in replaced and r.data.kind != RecordKind.RETRACTION]


def waiting_records(records: Iterable[Record]) -> list[Record]:
    """The agent's records waiting for the accountant: unconfirmed terms and suggested fixes."""
    records = list(records)
    decided = decisions(records)
    return [r for r in records if needs_confirmation(r) and r.id not in decided]


def _files_cited(record: Record) -> set[str]:
    return {v.citation.file_id for _, v in cited_values(record.data) if v.citation}


def check_new_record(new: Record, records: Sequence[Record], charges: Sequence[Charge]) -> list[str]:
    """Problems with a record about to be written, as plain sentences. Empty means it can be saved.

    The backend runs this on every write, and the agent sees the problems so it
    can fix them. `records` is everything already written in the workspace, and
    `charges` every charge in it.
    """
    problems: list[str] = []
    by_id = {r.id: r for r in records}
    current = {r.id for r in current_records(records)}
    charge_ids = {c.id for c in charges}

    def current_record(record_id: str, what: str) -> Record | None:
        if record_id not in by_id:
            problems.append(f"{what} {record_id} doesn't exist")
            return None
        if record_id not in current:
            problems.append(f"{what} {record_id} isn't current: it was replaced, retracted or not confirmed")
            return None
        return by_id[record_id]

    if new.id in by_id:
        problems.append(f"the ID {new.id} is already used")

    for path, value in cited_values(new.data):
        passage = value.citation.passage if value.citation else None
        if passage is not None and value.text and value.text not in passage:
            problems.append(f"the passage for '{path}' doesn't contain '{value.text}'")

    if new.replaces_id:
        target = current_record(new.replaces_id, "the replaced record")
        if target is not None:
            if new.author == Author.AGENT and target.author == Author.USER:
                problems.append("the agent can't replace the accountant's records")
            if new.data.kind not in (target.data.kind, RecordKind.RETRACTION):
                problems.append(f"a {new.data.kind} can't replace a {target.data.kind}")

    data = new.data
    if isinstance(data, Link):
        if data.charge_id not in charge_ids:
            problems.append(f"charge {data.charge_id} doesn't exist")
        fact = current_record(data.record_id, "the linked record")
        if fact is not None:
            if fact.data.kind not in FACT_KINDS:
                problems.append(f"a link points to a receipt, approval or note, not a {fact.data.kind}")
            elif fact.data.kind in MONEY_KINDS and data.amount_cents is None:
                problems.append(f"a link to a {fact.data.kind} needs an amount")
            elif fact.data.kind not in MONEY_KINDS and data.amount_cents is not None:
                problems.append(f"a link to a {fact.data.kind} has no amount")
            files = _files_cited(fact)
            if data.part is not None and files and data.part.file_id not in files:
                problems.append("the link's part has to be in the linked record's own file")
    elif isinstance(data, Judgment):
        if data.charge_id not in charge_ids:
            problems.append(f"charge {data.charge_id} doesn't exist")
        if data.record_id is not None:
            about = current_record(data.record_id, "the record the question is about")
            expected = {Question.COVERS: RecordKind.APPROVAL, Question.UNUSUAL_TERM: RecordKind.OTHER_TERM}
            want = expected.get(data.question)
            if about is not None and want is not None and about.data.kind != want:
                problems.append(f"a {data.question} question is about a {want}, not a {about.data.kind}")
        missing = [i for i in data.rests_on if i not in by_id]
        if missing:
            problems.append(f"the answer rests on records that don't exist: {', '.join(missing)}")
    elif isinstance(data, Confirmation):
        for record_id in data.record_ids:
            if record_id not in by_id:
                problems.append(f"record {record_id} doesn't exist")
            elif not needs_confirmation(by_id[record_id]):
                problems.append(f"record {record_id} doesn't wait for confirmation")

    return problems
