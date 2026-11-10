"""The checks' interface (docs/contracts.md section 8).

Buckets and checks follow the National Science Foundation (NSF) rules in docs/domain.md.

run_checks is a pure function, with no database and no model inside. W2
implements it in backend/app/checks/ with the signature declared here; callers
import it from there. Code checks six clear-cut rules (five about a charge, one,
the budget, about the grant), and asks the agent questions for what it can't
settle. It reads only confirmed terms.
"""

from collections.abc import Iterable
from datetime import date
from enum import StrEnum
from typing import Protocol

from pydantic import model_validator

from .base import Cents, Id, Model, Text, UtcDatetime
from .charges import Charge
from .evidence import EvidenceFile
from .records import Author, Period, Question, Record
from .runs import AgentRun, Trigger

# Missing evidence goes on the problem list this many days past the date an
# item was expected. For most items that's the charge's posting date.
MISSING_EVIDENCE_DAYS = 60
# From this many days before the grant's end date, when Berkeley sends its
# first Notice of Expiration, every missing item is flagged, even one not due yet.
CLOSEOUT_WINDOW_DAYS = 90


class Bucket(StrEnum):
    EVIDENCE_COMPLETE = "evidence_complete"
    POSSIBLE_CONFLICT = "possible_conflict"
    MISSING_EVIDENCE = "missing_evidence"
    NEEDS_HUMAN = "needs_human"


# Most serious first. A charge's bucket is the most serious among its reasons.
SEVERITY = (
    Bucket.POSSIBLE_CONFLICT,
    Bucket.NEEDS_HUMAN,
    Bucket.MISSING_EVIDENCE,
    Bucket.EVIDENCE_COMPLETE,
)


def most_serious(buckets: Iterable[Bucket]) -> Bucket:
    return min(buckets, key=SEVERITY.index)


class Problem(Model):
    """One problem code found, with text built by code and the records it rests on."""

    check: Id  # the check's stable ID, for example "period_of_performance"
    # Names the problem within the check, stable from run to run, so a reusable
    # note or a snooze can tell "the same problem", for example "after_end_date".
    problem: Id
    text: Text  # built by code
    record_ids: tuple[Id, ...] = ()  # the records it rests on


class Reason(Problem):
    """One reason on a charge. The reasons include the checks that pass, as evidence_complete."""

    bucket: Bucket  # the bucket this reason puts the charge in
    expected_by: date | None = None  # for a missing item: when it's expected
    accepted_by: Id | None = None  # the accepted reason, or the confirmed dispute, that accepts it
    offered_note_id: Id | None = (
        None  # a reusable note offered for it: the accepted reason that holds the note
    )


class ItemSource(StrEnum):
    DEFAULT = "default"
    AGENT = "agent"
    USER = "user"


class ChecklistEntry(Model):
    """One item on a charge's evidence checklist, and whether it's filled."""

    item_record_id: Id | None = None  # an added item
    default_item: Id | None = None  # a default's key
    added_by: ItemSource
    needed: Text
    amount_cents: Cents | None = None
    period: Period | None = None
    expected_by: date | None = None
    filled: bool
    link_ids: tuple[Id, ...] = ()  # the current links that fill it
    removal_waiting_id: Id | None = None  # the agent's removal of it, waiting for the accountant

    @model_validator(mode="after")
    def _one_item(self):
        if (self.item_record_id is None) == (self.default_item is None):
            raise ValueError("an entry is exactly one added item or one default")
        if (self.added_by == ItemSource.DEFAULT) != (self.default_item is not None):
            raise ValueError("default items are added by default, and only they are")
        return self


class ChargeStatus(Model):
    grant_id: Id
    charge_id: Id
    bucket: Bucket  # the bucket the checks give, whether or not the accountant accepted a reason
    reasons: tuple[Reason, ...]  # every reason, passes included
    checklist: tuple[ChecklistEntry, ...]
    flagged: bool  # on the accountant's problem list
    rechecking: bool = False  # the agent is answering again; the bucket keeps its last answer
    accepted: bool = False  # shows as Accepted; never counted as Evidence complete
    snoozed: bool = False  # hidden from the problem list until the snooze ends

    @model_validator(mode="after")
    def _bucket_is_most_serious(self):
        if self.reasons and self.bucket != most_serious([r.bucket for r in self.reasons]):
            raise ValueError("a charge's bucket is the most serious bucket among its reasons")
        return self


class RecordStatus(Model):
    """A record or file with a problem of its own, such as a bill linked over its total."""

    grant_id: Id
    record_id: Id | None = None
    file_id: Id | None = None
    problems: tuple[Problem, ...]
    flagged: bool
    accepted: bool = False
    snoozed: bool = False

    @model_validator(mode="after")
    def _one_subject(self):
        if (self.record_id is None) == (self.file_id is None):
            raise ValueError("a status is about exactly one record or one file")
        return self


class GrantStatus(Model):
    """Problems on the grant itself, such as spending over the award's limit. They're listed."""

    grant_id: Id
    problems: tuple[Problem, ...]
    flagged: bool
    accepted: bool = False
    snoozed: bool = False


class GrantNote(Model):
    """Anything else about the whole grant, such as an overspent budget line. Not a problem."""

    grant_id: Id
    check: Id
    text: Text  # built by code
    record_ids: tuple[Id, ...] = ()


class OpenQuestion(Model):
    """A required question with no current answer, and who answers it."""

    charge_id: Id
    question: Question
    record_id: Id | None = None  # the approval or other_term it's about
    # The agent, or the accountant when they answered before.
    answer_by: Author


class StatusEntry(Model):
    """One row of status history: a status from changed_at on, and what changed it.

    For a change that comes from saving an agent run, the trigger is what started the run.
    """

    changed_at: UtcDatetime  # the workspace clock's "now"
    trigger: Trigger
    status: ChargeStatus | RecordStatus | GrantStatus


class ChecksInput(Model):
    """Everything in one workspace visible at `now`.

    Records include replaced, waiting and rejected ones, in the order they were
    written; the checks apply rules.RecordState themselves.
    """

    now: UtcDatetime
    charges: tuple[Charge, ...]
    files: tuple[EvidenceFile, ...]
    records: tuple[Record, ...]
    # The agent runs that failed after their last retry. The checks raise a
    # problem on the file or charge that triggered each one, so it reaches the
    # problem list.
    failed_runs: tuple[AgentRun, ...] = ()


class ChecksOutput(Model):
    charges: tuple[ChargeStatus, ...]  # one per charge in the input
    records: tuple[RecordStatus, ...]  # each record or file with a problem of its own
    grants: tuple[GrantStatus, ...]  # each grant with a problem of its own
    questions: tuple[OpenQuestion, ...]  # every required question without a current answer
    notes: tuple[GrantNote, ...]


class RunChecks(Protocol):
    def __call__(self, checks_input: ChecksInput, /) -> ChecksOutput: ...


def run_checks(checks_input: ChecksInput) -> ChecksOutput:
    """Rerun every check.

    Returns each charge's status, records and files with problems, the grant's
    problems, the open questions and the grant notes.

    Declared here as the interface only. W2 implements it in backend/app/checks/.
    """
    raise NotImplementedError("W2 implements run_checks in backend/app/checks/")
