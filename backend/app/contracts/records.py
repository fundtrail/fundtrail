"""Records: everything the agent and the accountant write (docs/contracts.md sections 1 to 5).

A record is never edited. A correction is a new record whose replaces_id points
to the old one, and the old one stays. Every record has the same envelope
(Record) and one kind of data:

- grant terms: period_of_performance, budget_line, person, approval_rule, rate,
  notice, other_term
- facts from evidence: bill, approval, note
- links and answers: link, budget_assignment, judgment
- the evidence checklist: checklist_item, checklist_removal
- the agent's suggestions: dispute, duplicate, correction, remainder
- the accountant only: confirmation, accepted_reason, snooze, sign_off, mail_action
- either: retraction, which replaces a record with nothing

What counts (current records, what waits for the accountant, pointers that
follow a correction) and the write check are in rules.py.
"""

from collections.abc import Callable, Iterator, Sequence
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from .base import Cents, Id, Model, Text, UtcDatetime
from .signoff import SignOffSnapshot

if TYPE_CHECKING:
    from .charges import Charge

# Citations. Locations use the Anthropic API's (application programming
# interface's) own names and counting, so the
# agent copies them over unchanged.


class CharLocation(Model):
    """Plain text and email: character indexes from 0, end exclusive."""

    type: Literal["char_location"] = "char_location"
    start_char_index: int = Field(ge=0)
    end_char_index: int = Field(ge=0)

    @model_validator(mode="after")
    def _order(self):
        if self.end_char_index <= self.start_char_index:
            raise ValueError("end_char_index comes after start_char_index")
        return self


class PageLocation(Model):
    """A PDF (Portable Document Format file) with real text: page numbers from 1, end exclusive."""

    type: Literal["page_location"] = "page_location"
    start_page_number: int = Field(ge=1)
    end_page_number: int = Field(ge=1)

    @model_validator(mode="after")
    def _order(self):
        if self.end_page_number <= self.start_page_number:
            raise ValueError("end_page_number comes after start_page_number")
        return self


class ContentBlockLocation(Model):
    """A custom content document: block indexes from 0, end exclusive."""

    type: Literal["content_block_location"] = "content_block_location"
    start_block_index: int = Field(ge=0)
    end_block_index: int = Field(ge=0)

    @model_validator(mode="after")
    def _order(self):
        if self.end_block_index <= self.start_block_index:
            raise ValueError("end_block_index comes after start_block_index")
        return self


class PageBox(Model):
    """A box on a page, as fractions of the page's width and height from its top left corner."""

    page: int = Field(default=1, ge=1)  # 1 for a single image
    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _inside(self):
        if self.left + self.width > 1 or self.top + self.height > 1:
            raise ValueError("the box has to stay inside the page")
        return self


class ImageBox(PageBox):
    """A photo or a scanned page: a box around the value on the original.

    The agent returns pixels on the image we sent, at a size we control, and
    code scales the box back to the original before saving it here.
    """

    type: Literal["image_box"] = "image_box"


Location = Annotated[
    CharLocation | PageLocation | ContentBlockLocation | ImageBox,
    Field(discriminator="type"),
]


class CharRange(Model):
    """A range of characters in a text file's stored text: from 0, end exclusive."""

    start_char_index: int = Field(ge=0)
    end_char_index: int = Field(ge=0)

    @model_validator(mode="after")
    def _order(self):
        if self.end_char_index <= self.start_char_index:
            raise ValueError("end_char_index comes after start_char_index")
        return self


class Match(StrEnum):
    """How a citation was matched against its file, once, when the record was saved."""

    # The passage is in the file as cited. For an image box: the second look saw the same value.
    EXACT = "exact"
    CLOSE = "close"  # a PDF passage found on its page by a close match
    NOT_FOUND = "not_found"  # couldn't be placed: the value is unconfirmed


FOUND = frozenset({Match.EXACT, Match.CLOSE})


class Citation(Model):
    """A place in an evidence file. It's what gets highlighted when the user opens it."""

    file_id: Id
    # The API's cited text, copied as is. The agent never types it. None for an
    # image box: photos and scans have no passage.
    passage: str | None
    location: Location
    # Filled in by the server when it matches the citation against the file.
    # The write check refuses a citation that hasn't been matched.
    match: Match | None = None
    # Where the highlight goes. The passage stays exactly what the API returned,
    # but the highlight is ours. For a PDF: boxes on the page, found once when the
    # record is saved. For text and email: one or more character ranges inside the
    # passage, such as one per line where the value stands on its own.
    highlight: tuple[PageBox, ...] | tuple[CharRange, ...] | None = None

    @model_validator(mode="after")
    def _shape(self):
        is_box = isinstance(self.location, ImageBox)
        if is_box != (self.passage is None):
            raise ValueError(
                "an image_box citation has no passage, and every other citation has one"
            )
        if self.passage == "":
            raise ValueError("a passage can't be empty")
        for part in self.highlight or ():
            if isinstance(part, PageBox) and not isinstance(self.location, PageLocation):
                raise ValueError("a highlight's boxes are for a PDF citation (page_location)")
            if isinstance(part, CharRange):
                location = self.location
                if not isinstance(location, CharLocation):
                    raise ValueError("a highlight's character ranges are for a text citation")
                inside = (
                    location.start_char_index <= part.start_char_index
                    and part.end_char_index <= location.end_char_index
                )
                if not inside:
                    raise ValueError("a highlight's character ranges are inside the passage")
        return self


# Cited values.


class Cited[T](Model):
    """A value read from a document, or typed by the accountant.

    The agent always cites, unless it marks the value `uncited`: read from the
    document, but with no citation to show for it. The mark is valid only with
    no citation. An uncited value is always unconfirmed, until the accountant
    confirms the record it's in or types the value. A value the accountant
    enters has no citation.
    """

    value: T
    # The value exactly as the document writes it, for example "January 31, 2027".
    # It has to appear in the citation's passage (trust rule 2).
    text: str | None = None
    citation: Citation | None = None
    uncited: bool = False

    @model_validator(mode="after")
    def _text_with_citation(self):
        if self.citation is not None and not self.text:
            raise ValueError("a cited value needs the text it was read from")
        if self.uncited and self.citation is not None:
            raise ValueError("a value marked uncited has no citation")
        return self


class CitedText(Cited[str]):
    pass


class CitedDate(Cited[date]):
    pass


class CitedMoney(Cited[Cents]):
    """value is in cents, negative for a credit."""


class CitedDecimal(Cited[Decimal]):
    """A number such as a quantity or a rate.

    A rate's value is what multiplies a quantity into cents: a percent as a
    fraction (36.6% is 0.366, applied to an amount in cents), and a dollar rate
    in cents per unit ($100 a day is 10000, applied to a number of days).
    """


class Period(Model):
    """A stretch of time, both days included."""

    start: date
    end: date

    @model_validator(mode="after")
    def _order(self):
        if self.end < self.start:
            raise ValueError("a period ends on or after its start")
        return self


class CitedPeriod(Model):
    """A period a document states, such as the months an effort report covers."""

    start: CitedDate
    end: CitedDate

    @model_validator(mode="after")
    def _order(self):
        if self.end.value < self.start.value:
            raise ValueError("a period ends on or after its start")
        return self


# Record kinds.


class RecordKind(StrEnum):
    # Grant terms
    PERIOD_OF_PERFORMANCE = "period_of_performance"
    BUDGET_LINE = "budget_line"
    PERSON = "person"
    APPROVAL_RULE = "approval_rule"
    RATE = "rate"
    NOTICE = "notice"
    OTHER_TERM = "other_term"
    # Facts from evidence
    BILL = "bill"
    APPROVAL = "approval"
    NOTE = "note"
    # Links and answers
    LINK = "link"
    BUDGET_ASSIGNMENT = "budget_assignment"
    JUDGMENT = "judgment"
    # The evidence checklist
    CHECKLIST_ITEM = "checklist_item"
    CHECKLIST_REMOVAL = "checklist_removal"
    # The agent's suggestions
    DISPUTE = "dispute"
    DUPLICATE = "duplicate"
    CORRECTION = "correction"
    REMAINDER = "remainder"
    # The accountant only
    CONFIRMATION = "confirmation"
    ACCEPTED_REASON = "accepted_reason"
    SNOOZE = "snooze"
    SIGN_OFF = "sign_off"
    MAIL_ACTION = "mail_action"
    # Either
    RETRACTION = "retraction"


TERM_KINDS = frozenset(
    {
        RecordKind.PERIOD_OF_PERFORMANCE,
        RecordKind.BUDGET_LINE,
        RecordKind.PERSON,
        RecordKind.APPROVAL_RULE,
        RecordKind.RATE,
        RecordKind.NOTICE,
        RecordKind.OTHER_TERM,
    }
)
FACT_KINDS = frozenset(
    {RecordKind.BILL, RecordKind.APPROVAL, RecordKind.NOTE}
)  # what a link points to
ACCOUNTANT_KINDS = frozenset(
    {
        RecordKind.CONFIRMATION,
        RecordKind.ACCEPTED_REASON,
        RecordKind.SNOOZE,
        RecordKind.SIGN_OFF,
        RecordKind.MAIL_ACTION,
    }
)


# Grant terms. Each comes from the award letter, an amendment or a program
# solicitation added to the grant as a source.


class _Term(Model):
    # The date the document gives itself, such as an amendment's date. An
    # amendment isn't a correction: it's a new term, and the checks use this
    # date to decide which terms are in force.
    dated: CitedDate


class PeriodOfPerformance(_Term):
    kind: Literal[RecordKind.PERIOD_OF_PERFORMANCE] = RecordKind.PERIOD_OF_PERFORMANCE
    start: CitedDate | None = None  # an amendment may state only the new end date
    end: CitedDate


class BudgetCategory(StrEnum):
    """The National Science Foundation's (NSF's) standard budget categories.

    Other Direct Costs contains its six sub-lines, each a category of its own.
    The sub-lines of Participant Support Costs (stipends, travel, subsistence,
    other) and of Travel (domestic, international) are budget lines of their
    own, with their amounts, and their category is their parent's.
    """

    SENIOR_PERSONNEL = "senior_personnel"
    OTHER_PERSONNEL = "other_personnel"
    FRINGE_BENEFITS = "fringe_benefits"
    EQUIPMENT = "equipment"
    TRAVEL = "travel"
    PARTICIPANT_SUPPORT = "participant_support"
    OTHER_DIRECT_COSTS = "other_direct_costs"
    MATERIALS_AND_SUPPLIES = "materials_and_supplies"
    PUBLICATION = "publication"
    CONSULTANT_SERVICES = "consultant_services"
    COMPUTER_SERVICES = "computer_services"
    SUBAWARDS = "subawards"
    OTHER_DIRECT_COSTS_OTHER = "other_direct_costs_other"  # "Other", the sixth sub-line


# The category each sub-line sits inside.
CATEGORY_PARENT: dict[BudgetCategory, BudgetCategory] = {
    sub: BudgetCategory.OTHER_DIRECT_COSTS
    for sub in (
        BudgetCategory.MATERIALS_AND_SUPPLIES,
        BudgetCategory.PUBLICATION,
        BudgetCategory.CONSULTANT_SERVICES,
        BudgetCategory.COMPUTER_SERVICES,
        BudgetCategory.SUBAWARDS,
        BudgetCategory.OTHER_DIRECT_COSTS_OTHER,
    )
}


def categories_match(a: BudgetCategory, b: BudgetCategory) -> bool:
    """Whether two categories match: the same, or one contains the other."""
    return a == b or CATEGORY_PARENT.get(a) == b or CATEGORY_PARENT.get(b) == a


class BudgetLine(_Term):
    """One line or sub-line of the budget the notice prints, named as NSF prints it.

    Code compares categories, never names.
    """

    kind: Literal[RecordKind.BUDGET_LINE] = RecordKind.BUDGET_LINE
    name: CitedText
    amount: CitedMoney
    category: BudgetCategory  # read by the agent with the line, and confirmed with it


class Person(_Term):
    """Someone named in the award letter, or a known sender the accountant adds."""

    kind: Literal[RecordKind.PERSON] = RecordKind.PERSON
    name: CitedText
    email: CitedText | None = None
    role: CitedText  # as the document states it, for example "Program Officer"


class ApprovalScope(StrEnum):
    """What an approval rule applies to in its category."""

    EVERY_CHARGE = "every_charge"  # every charge in the category
    # Only money moved out of the category: the ledger files a charge under it while
    # its assigned budget line is elsewhere, such as a laptop on a participant
    # support account. A charge both sides agree is in the category isn't covered.
    MOVED_OUT = "moved_out"


class CitedScope(Cited[ApprovalScope]):
    """An approval rule's scope, read from the clause's own words, for example
    "may not be diverted ... to other categories of expense" for moved_out."""


class ApprovalRule(_Term):
    kind: Literal[RecordKind.APPROVAL_RULE] = RecordKind.APPROVAL_RULE
    applies_to: CitedText  # the budget line or kind of cost, as stated
    approver: CitedText  # who must approve, as stated, for example "Program Officer"
    channel: CitedText | None = None  # how, as stated, for example "Research.gov"
    # What the rule applies to, confirmed by the accountant with the term. None when
    # the clause doesn't say clearly: the agent then flags the term and doesn't pick.
    scope: CitedScope | None = None


class Rate(_Term):
    """A rate that applies across the grant, such as a fringe benefit rate."""

    kind: Literal[RecordKind.RATE] = RecordKind.RATE
    name: CitedText
    rate: CitedDecimal


class Notice(_Term):
    """An award notice's amendment number, type and amounts.

    Every NSF notice is an amendment with a number and a type, and every notice
    the agent reads gets one of these, whether or not it adds money. A notice
    that prints no amendment number gets none.
    """

    kind: Literal[RecordKind.NOTICE] = RecordKind.NOTICE
    amendment_number: CitedText  # for example "000" for the new project
    amendment_type: CitedText  # for example "New Project", "Increment" or "No Cost Extensions"
    # "Amount Obligated by this Amendment": what it adds.
    obligated_by_amendment: CitedMoney | None = None
    # "Total Amount Obligated to Date": the award's limit.
    obligated_to_date: CitedMoney | None = None
    # The award number and the project title as the notice prints them (issue 118).
    # Once the notice counts, the platform copies them onto the grant's award_number
    # and title: see rules.award_number_and_title.
    award_number: CitedText | None = None
    title: CitedText | None = None


class OtherTerm(_Term):
    """Anything an award letter or amendment says that no other kind holds.

    For example a principal investigator (PI) on leave.

    It's in force from its own date on, and the agent reads any dates inside its statement.
    """

    kind: Literal[RecordKind.OTHER_TERM] = RecordKind.OTHER_TERM
    label: Text  # a plain short name, for example "PI on leave"
    statement: CitedText


# Facts from evidence.


class BillItem(Model):
    description: CitedText
    amount: CitedMoney


class Bill(Model):
    """Any document that bills for a cost.

    An invoice, a receipt, a card slip, a credit memo or a usage statement.

    A credit has a negative total.
    """

    kind: Literal[RecordKind.BILL] = RecordKind.BILL
    total: CitedMoney
    vendor: CitedText | None = None
    dated: CitedDate | None = None
    # Anything else that identifies the document goes here: names, order numbers,
    # and the project or award number it mentions.
    description: CitedText | None = None
    document_number: CitedText | None = (
        None  # the invoice or order number, often on the ledger line too
    )
    items: tuple[BillItem, ...] = ()


class Approval(Model):
    """An approval found in evidence. Code decides the approver's role from the grant's people."""

    kind: Literal[RecordKind.APPROVAL] = RecordKind.APPROVAL
    approver_email: CitedText  # for a forwarded email, the original sender's
    covers: CitedText  # what it approves, as stated
    approver_name: CitedText | None = None
    approved_on: CitedDate | None = None
    channel: CitedText | None = None  # the channel the document names, such as "Research.gov"


class Note(Model):
    """Evidence that supports or explains a charge without billing or approving it.

    For example a payment notice, an appointment letter, an effort report.
    """

    kind: Literal[RecordKind.NOTE] = RecordKind.NOTE
    label: Text  # a plain short name
    statement: CitedText
    period: CitedPeriod | None = None  # the stretch of time the document covers, when it states one


# Links and answers.


class ShareBasis(Model):
    """A share of a bill, such as "56 of the 96 samples are for this grant" (decision 0021).

    The worked-out amount is `total` times `share` over `out_of`. The agent cites all
    three. The accountant may type them, with the basis in `note`, and typed values
    count as confirmed.
    """

    share: CitedDecimal  # for example 56
    out_of: CitedDecimal  # for example 96
    total: CitedMoney  # the bill's total, for example $10,000
    note: str | None = None  # the basis in the accountant's words, when they type the share

    @model_validator(mode="after")
    def _positive(self):
        if self.out_of.value <= 0 or self.share.value < 0 or self.share.value > self.out_of.value:
            raise ValueError("a share is between 0 and the whole, and the whole is more than 0")
        return self

    def amount(self) -> Decimal:
        """The worked-out amount in cents, not rounded."""
        return Decimal(self.total.value) * self.share.value / self.out_of.value

    def matches(self, cents: int) -> bool:
        """Whether an amount matches the worked-out share to within one cent (0021), since
        a three-way split can't divide evenly."""
        return abs(self.amount() - cents) <= 1


class Link(Model):
    """Ties a fact to a charge.

    A bill link means "pays for", an approval link "approves", and a note link
    "supports" or "explains". The part is the place in the record's own file
    that pertains to this charge; for a whole bill it's the total's citation.
    A link names the checklist item it fills by at most one of item_record_id
    (an added checklist_item) or default_item (a default's key).
    """

    kind: Literal[RecordKind.LINK] = RecordKind.LINK
    record_id: Id  # the bill, approval or note
    charge_id: Id
    # Only when the item it fills carries an amount. Negative for a credit.
    amount_cents: Cents | None = None
    part: Citation | None = None  # the agent always gives one
    item_record_id: Id | None = None
    default_item: Id | None = None
    reason: str | None = None  # one line on why they match
    # Decision 0021: what a link for part of a bill rests on. At most one: a line on
    # the bill that states the part, or a share with its cited basis.
    stated_amount: CitedMoney | None = None
    share: ShareBasis | None = None

    @model_validator(mode="after")
    def _one_item(self):
        if self.item_record_id is not None and self.default_item is not None:
            raise ValueError("a link fills at most one checklist item")
        if self.stated_amount is not None and self.share is not None:
            raise ValueError("a link's part rests on a stated amount or a share, not both")
        return self


class BudgetAssignment(Model):
    """Which budget line a charge belongs to. A charge has at most one current assignment."""

    kind: Literal[RecordKind.BUDGET_ASSIGNMENT] = RecordKind.BUDGET_ASSIGNMENT
    charge_id: Id
    record_id: Id  # the budget_line term
    reason: Text  # one line on why


class Question(StrEnum):
    ALLOWABLE = "allowable"  # Is this cost necessary and reasonable, and is it for this project?
    COVERS = "covers"  # Does this approval cover this charge?
    UNUSUAL_TERM = "unusual_term"  # Does this term change anything for this charge?
    FLAG = "flag"  # the agent's own question, for anything no other question covers


class Answer(StrEnum):
    SUPPORTS = "supports"  # passes
    CONTRADICTS = "contradicts"  # Possible conflict
    UNSURE = "unsure"  # Needs a human


class Judgment(Model):
    """An answer to one question, with the reasoning and quotes behind it.

    allowable is about a charge. covers and unusual_term are about a charge and
    a record: the approval, or the other_term. A flag is about a charge, a
    record, or a file that has no record, or more than one of these.
    """

    kind: Literal[RecordKind.JUDGMENT] = RecordKind.JUDGMENT
    charge_id: Id | None = None
    question: Question
    record_id: Id | None = None
    file_id: Id | None = None
    text: Text  # the question as asked; for a flag, the agent's own question
    answer: Answer
    reasoning: Text
    rule: str | None = None  # the ID of the rulebook rule the answer used
    quotes: tuple[Citation, ...] = ()
    rests_on: tuple[Id, ...] = ()  # the record IDs the answer depends on

    @model_validator(mode="after")
    def _subject(self):
        if self.question == Question.FLAG:
            if self.charge_id is None and self.record_id is None and self.file_id is None:
                raise ValueError("a flag is about a charge, a record or a file")
            return self
        if self.charge_id is None:
            raise ValueError(f"a {self.question} question is about a charge")
        if self.file_id is not None:
            raise ValueError(f"a {self.question} question isn't about a file")
        about_a_record = self.question in (Question.COVERS, Question.UNUSUAL_TERM)
        if about_a_record and self.record_id is None:
            raise ValueError(f"a {self.question} question names the record it's about")
        if not about_a_record and self.record_id is not None:
            raise ValueError(f"a {self.question} question isn't about a record")
        return self


# The evidence checklist. Default items aren't stored: code works them out each
# time from the charge (see DefaultItem). Added items and removals are records.


class RateMath(Model):
    """An amount that comes from a rate: a quantity times a rate, both cited, re-checked by code.

    The rate is cited from a file on the grant, or it's a confirmed rate term.
    """

    quantity: CitedDecimal
    rate: CitedDecimal | None = None
    rate_id: Id | None = None  # a rate term

    @model_validator(mode="after")
    def _one_rate(self):
        if (self.rate is None) == (self.rate_id is None):
            raise ValueError("the rate is either cited or a rate term, not both")
        return self


class ChecklistItem(Model):
    """An item someone added to a charge's checklist. Who added it is the record's author."""

    kind: Literal[RecordKind.CHECKLIST_ITEM] = RecordKind.CHECKLIST_ITEM
    charge_id: Id
    needed: Text  # what's needed, for example "Airfare receipt"
    # The amount the bills linked to it add up to, or the amount from the rate.
    amount_cents: Cents | None = None
    rate: RateMath | None = None
    period: Period | None = None  # the period the linked document's own period has to cover
    expected_by: date | None = None  # it isn't late before then
    # Set when the agent recognized something on NSF's standing list of what
    # needs its approval: the entry it recognized. It makes this an NSF approval item.
    nsf_standing_list: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _rate_gives_amount(self):
        if self.rate is not None and self.amount_cents is None:
            raise ValueError("an item with a rate carries the amount the rate gives")
        return self


class ChecklistRemoval(Model):
    """Removes one item from a charge's checklist: an added item, or a default."""

    kind: Literal[RecordKind.CHECKLIST_REMOVAL] = RecordKind.CHECKLIST_REMOVAL
    charge_id: Id
    item_record_id: Id | None = None
    default_item: Id | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _one_item(self):
        if (self.item_record_id is None) == (self.default_item is None):
            raise ValueError("a removal names exactly one item")
        return self


class DefaultItem(Model):
    """One of a charge's default checklist items, worked out each time and never stored.

    The checks (W2) own the table of account groups and their defaults. A link
    or a removal names a default by its key, which is stable for that charge.
    """

    key: Id  # for example "bill" or "usage_statement"
    needed: Text
    amount_cents: Cents | None = (
        None  # for example the charge's amount, for "a bill that adds up to the charge"
    )
    period: Period | None = None
    expected_by: date | None = None


# What the write check calls to get a charge's default items. W2 provides it.
DefaultItems = Callable[["Charge", Sequence["Record"]], Sequence[DefaultItem]]


# The agent's suggestions. Both wait for the accountant.


class Dispute(Model):
    """The agent thinks one of code's checks is wrong for a charge."""

    kind: Literal[RecordKind.DISPUTE] = RecordKind.DISPUTE
    charge_id: Id
    check: Id  # the check's stable ID, for example "period_of_performance"
    reasoning: Text
    quotes: tuple[Citation, ...] = Field(min_length=1)


class Duplicate(Model):
    """A copy of a file already on the grant, such as a photo and a PDF of the same invoice."""

    kind: Literal[RecordKind.DUPLICATE] = RecordKind.DUPLICATE
    copy_file_id: Id
    original_file_id: Id
    reason: str | None = None

    @model_validator(mode="after")
    def _two_files(self):
        if self.copy_file_id == self.original_file_id:
            raise ValueError("a file can't be a copy of itself")
        return self


class Correction(Model):
    """Which ledger line a correcting line corrects, when the ledger names none (decision 0020).

    The agent's waits for the accountant, because it changes how another charge is
    judged. Netting starts only once it counts.
    """

    kind: Literal[RecordKind.CORRECTION] = RecordKind.CORRECTION
    charge_id: Id  # the correcting line
    corrects_line_id: Id  # the ledger line ID it corrects
    reason: Text
    quotes: tuple[Citation, ...] = ()


class Remainder(Model):
    """The rest of a bill belongs to another award (decision 0021).

    About the bill, not a charge. The agent's waits for the accountant. Once it
    counts, the bill's remainder isn't "money nobody charged".
    """

    kind: Literal[RecordKind.REMAINDER] = RecordKind.REMAINDER
    record_id: Id  # the bill
    other_award: CitedText  # the award the passage names
    reason: Text
    quotes: tuple[Citation, ...] = ()


# The accountant only.


class Decision(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class Confirmation(Model):
    """Confirms or rejects the agent's records that wait.

    It also confirms a record with a value nobody could confirm in its file.

    The latest decision on a record wins, and a rejected record never counts.
    """

    kind: Literal[RecordKind.CONFIRMATION] = RecordKind.CONFIRMATION
    record_ids: tuple[Id, ...] = Field(min_length=1)
    decision: Decision = Decision.CONFIRMED


# The award limit's problem (issue 83): the budget check's over_limit, on the grant.
# The only reason an accepted reason may carry an amount for.
OVER_LIMIT_CHECK = "budget"
OVER_LIMIT_PROBLEM = "over_limit"


class ReasonRef(Model):
    """Names one reason: the check's stable ID, and the problem within it that code names."""

    check: Id
    problem: Id


class _Subject(Model):
    """What an accepted reason or a snooze is about: at most one of a charge, a record or a file.

    None of them means it's about the grant itself.
    """

    charge_id: Id | None = None
    record_id: Id | None = None
    file_id: Id | None = None

    @model_validator(mode="after")
    def _one_subject(self):
        if sum(x is not None for x in (self.charge_id, self.record_id, self.file_id)) > 1:
            raise ValueError("it's about at most one charge, record or file")
        return self


class AcceptedReason(_Subject):
    """The accountant accepts one reason, with a note. It covers the problem as it stood."""

    kind: Literal[RecordKind.ACCEPTED_REASON] = RecordKind.ACCEPTED_REASON
    reason: ReasonRef
    note: Text
    reusable: bool = False  # False is a one-off note
    # When accepting a note offered on a similar charge: the accepted reason whose
    # note this reuses. reusable then says whether the note's amount limit rises.
    reuses_id: Id | None = None
    # The records the reason rested on when accepted.
    rests_on: tuple[Id, ...] = ()
    # Issue 83: for the award limit's over_limit problem, the amount over when it was
    # accepted, copied from the problem. The problem comes back when the amount over
    # grows larger, naming both. None for every other reason.
    amount_cents: Cents | None = Field(default=None, ge=0)


class Snooze(_Subject):
    """Hides a problem from the list until a date. The checks still say it isn't done."""

    kind: Literal[RecordKind.SNOOZE] = RecordKind.SNOOZE
    until: date
    note: Text
    # The reasons it covered, so a new one brings it back.
    reasons: tuple[ReasonRef, ...] = Field(min_length=1)


class SignOff(Model):
    """The accountant signs off on the grant's evidence report (decision 0022).

    The accountant sends only the note. The server stores the report and fills in
    where it's stored, its checksum and the snapshot of what counts as a change.
    """

    kind: Literal[RecordKind.SIGN_OFF] = RecordKind.SIGN_OFF
    note: str | None = None
    report_path: Text  # the stored PDF, in private storage; never made again
    report_sha256: Text
    snapshot: SignOffSnapshot


class MailAction(StrEnum):
    LET_IN = "let_in"  # the message arrives at that moment, as evidence files
    DISMISS = "dismiss"  # it stays stored and unread


class MailDecision(Model):
    """The accountant lets in or dismisses one held message (decision 0025).

    Adding the sender as known is a `person` term instead.
    """

    kind: Literal[RecordKind.MAIL_ACTION] = RecordKind.MAIL_ACTION
    held_mail_id: Id
    action: MailAction


class Retraction(Model):
    """Replaces a record with nothing. It's also how an accepted reason is reopened,
    a duplicate mark undone, and a reusable note withdrawn."""

    kind: Literal[RecordKind.RETRACTION] = RecordKind.RETRACTION
    reason: str | None = None


RecordData = Annotated[
    PeriodOfPerformance
    | BudgetLine
    | Person
    | ApprovalRule
    | Rate
    | Notice
    | OtherTerm
    | Bill
    | Approval
    | Note
    | Link
    | BudgetAssignment
    | Judgment
    | ChecklistItem
    | ChecklistRemoval
    | Dispute
    | Duplicate
    | Correction
    | Remainder
    | Confirmation
    | AcceptedReason
    | Snooze
    | SignOff
    | MailDecision
    | Retraction,
    Field(discriminator="kind"),
]


class Author(StrEnum):
    AGENT = "agent"
    USER = "user"


def cited_values(model: BaseModel, prefix: str = "") -> Iterator[tuple[str, Cited[object]]]:
    """Every cited value inside a record's data, with its path, for example "items[0].amount"."""
    for name, value in model:
        path = f"{prefix}{name}"
        if isinstance(value, Cited):
            yield path, value
        elif isinstance(value, BaseModel) and not isinstance(value, Citation):
            yield from cited_values(value, f"{path}.")
        elif isinstance(value, tuple):
            for i, item in enumerate(value):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
                if isinstance(item, Cited):
                    yield f"{path}[{i}]", item
                elif isinstance(item, BaseModel) and not isinstance(item, Citation):
                    yield from cited_values(item, f"{path}[{i}].")


def citations(model: BaseModel) -> Iterator[Citation]:
    """Every citation in a record's data: its values', a link's part, an answer's quotes."""
    for _, value in model:
        if isinstance(value, Citation):
            yield value
        elif isinstance(value, BaseModel):
            yield from citations(value)
        elif isinstance(value, tuple):
            for item in value:  # pyright: ignore[reportUnknownVariableType]
                if isinstance(item, Citation):
                    yield item
                elif isinstance(item, BaseModel):
                    yield from citations(item)


class Record(Model):
    id: Id
    workspace_id: Id
    # For now each grant is isolated: a record's charge, and the records and files
    # it points to, are on this same grant.
    grant_id: Id
    author: Author
    author_user_id: Id | None = None  # set exactly when author is "user"
    written_at: UtcDatetime  # the workspace clock's "now" when it was written
    replaces_id: Id | None = None  # the record this one corrects or retracts; the old one stays
    # The thread message whose run wrote this record. Every record the agent writes
    # in a run a thread message started waits for the accountant, whatever its kind.
    # Set only on the agent's records; the write check makes the run set it.
    thread_message_id: Id | None = None
    # The order it was stored in: one number from a sequence the database shares
    # across records, charges and evidence files, so any two can be compared. Never
    # the workspace clock. None until it's stored.
    stored_seq: int | None = None
    # On the agent's records only: the read point of the run that wrote it
    # (AgentRun.read_through_seq), set when the run saves it. Anything stored
    # during the run isn't new evidence for that run's answers.
    read_through_seq: int | None = None
    data: RecordData

    @property
    def kind(self) -> RecordKind:
        return self.data.kind

    @property
    def charge_id(self) -> str | None:
        """The charge the record is about. A column the database generates from data."""
        return getattr(self.data, "charge_id", None)

    @property
    def record_id(self) -> str | None:
        """The record it points to. A column the database generates from data."""
        return getattr(self.data, "record_id", None)

    @model_validator(mode="after")
    def _rules(self):
        if (self.author == Author.USER) != (self.author_user_id is not None):
            raise ValueError("author_user_id is set exactly when author is 'user'")
        if self.replaces_id == self.id:
            raise ValueError("a record can't replace itself")
        if self.data.kind == RecordKind.RETRACTION and self.replaces_id is None:
            raise ValueError("a retraction names the record it replaces")
        if self.author == Author.USER and self.read_through_seq is not None:
            raise ValueError("only the agent's records carry their run's read point")
        if self.author == Author.USER and self.thread_message_id is not None:
            raise ValueError("only the agent's records carry the thread message of their run")
        if self.author == Author.AGENT:
            if self.data.kind in ACCOUNTANT_KINDS:
                raise ValueError(f"only the accountant writes a {self.data.kind} record")
            for path, value in cited_values(self.data):
                if value.citation is None and not value.uncited:
                    raise ValueError(
                        f"the agent's value '{path}' needs a citation, or is marked uncited"
                    )
            if isinstance(self.data, Link) and self.data.part is None:
                raise ValueError("the agent's link needs a part")
            data = self.data
            if (
                isinstance(data, Judgment)
                and data.question == Question.FLAG
                and data.answer != Answer.UNSURE
            ):
                raise ValueError("the agent's flag is always unsure")
        return self
