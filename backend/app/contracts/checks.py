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

from pydantic import Field, computed_field, model_validator

from .base import Cents, Id, Model, Text, UtcDatetime
from .buckets import Bucket
from .charges import Charge
from .evidence import EvidenceFile
from .mail import SkippedFile
from .records import Author, Period, Question, Record
from .runs import AgentRun, Trigger
from .signoff import ChargeSnapshot, SignOffSnapshot, SnapshotTotals

# Missing evidence goes on the problem list this many days past the date an
# item was expected. For most items that's the charge's posting date.
MISSING_EVIDENCE_DAYS = 60
# From this many days before the grant's end date, when Berkeley sends its
# first Notice of Expiration, every missing item is flagged, even one not due yet.
CLOSEOUT_WINDOW_DAYS = 90


# Most serious first. A charge's bucket is the most serious among its reasons.
SEVERITY = (
    Bucket.POSSIBLE_CONFLICT,
    Bucket.NEEDS_HUMAN,
    Bucket.MISSING_EVIDENCE,
    Bucket.EVIDENCE_COMPLETE,
)


def most_serious(buckets: Iterable[Bucket]) -> Bucket:
    return min(buckets, key=SEVERITY.index)


def _ready(bucket: Bucket, *, accepted: bool, reversed: bool, snoozed: bool) -> bool:
    if snoozed:
        return False
    return bucket == Bucket.EVIDENCE_COMPLETE or accepted or reversed


class Problem(Model):
    """One problem code found, with text built by code and the records it rests on."""

    check: Id  # the check's stable ID, for example "period_of_performance"
    # Names the problem within the check, stable from run to run, so a reusable
    # note or a snooze can tell "the same problem", for example "after_end_date".
    problem: Id
    text: Text  # built by code
    record_ids: tuple[Id, ...] = ()  # the records it rests on
    # The accepted reason, or the confirmed dispute, that accepts it.
    accepted_by: Id | None = None
    # Issue 83: for the award limit's over_limit problem, the amount over, filled by
    # the checks. An acceptance holds while the amount over is no larger than the
    # amount it accepted. None for every other problem.
    amount_cents: Cents | None = Field(default=None, ge=0)


class Reason(Problem):
    """One reason on a charge. The reasons include the checks that pass, as evidence_complete."""

    bucket: Bucket  # the bucket this reason puts the charge in
    expected_by: date | None = None  # for a missing item: when it's expected
    # A reusable note offered for it: the accepted reason that holds the note.
    offered_note_id: Id | None = None
    # The agent's dispute of this reason, while it waits for the accountant.
    dispute_id: Id | None = None


class ItemSource(StrEnum):
    DEFAULT = "default"  # the ledger account group's default
    # Issue 115: code added it because one of the grant's approval rules applies to
    # the charge. The entry's rule_id names the rule.
    RULE = "rule"
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
    # For an item an approval rule added (added_by "rule"): the approval_rule term's
    # record ID, so the screen can say which rule added it.
    rule_id: Id | None = None

    @model_validator(mode="after")
    def _one_item(self):
        if (self.item_record_id is None) == (self.default_item is None):
            raise ValueError("an entry is exactly one added item or one default")
        code_added = self.added_by in (ItemSource.DEFAULT, ItemSource.RULE)
        if code_added != (self.default_item is not None):
            raise ValueError("items code adds aren't stored and have a key, and only they do")
        if (self.added_by == ItemSource.RULE) != (self.rule_id is not None):
            raise ValueError("an item an approval rule added names the rule, and only it does")
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
    # Decision 0020. The amount that counts once the lines correcting this one are
    # netted against it; None when no correction is netted. See corrections.py.
    net_cents: Cents | None = None
    corrections: tuple[Id, ...] = ()  # the charges netted into this one
    # Fully corrected: the net is zero. Shown as Reversed, off the problem list,
    # counted on its own. It keeps the bucket the checks give it.
    reversed: bool = False

    @model_validator(mode="before")
    @classmethod
    def _ready_is_worked_out(cls, data: object) -> object:
        """`ready` is worked out, never passed in. A stored status that carries it is read
        back with it dropped and worked out again."""
        if isinstance(data, dict) and "ready" in data:
            kept: dict[object, object] = {
                k: v
                for k, v in data.items()  # pyright: ignore[reportUnknownVariableType]
                if k != "ready"
            }
            return kept
        return data  # pyright: ignore[reportUnknownVariableType]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ready(self) -> bool:
        """Ready for closeout (decision 0022): Evidence complete, accepted or fully
        reversed, and not snoozed. The same rule as ready_for_closeout."""
        return _ready(
            self.bucket, accepted=self.accepted, reversed=self.reversed, snoozed=self.snoozed
        )

    @model_validator(mode="after")
    def _bucket_is_most_serious(self):
        if self.reasons and self.bucket != most_serious([r.bucket for r in self.reasons]):
            raise ValueError("a charge's bucket is the most serious bucket among its reasons")
        if self.reversed and self.net_cents != 0:
            raise ValueError("a reversed charge's net is zero")
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
    # problem on the file or charge that triggered each one, or on the thread's
    # charge or record for a run a thread message started, so it reaches the list.
    failed_runs: tuple[AgentRun, ...] = ()
    # Files Gmail or Drive brought that weren't taken in. The checks raise one
    # problem on the grant naming them.
    skipped_files: tuple[SkippedFile, ...] = ()


class ChecksOutput(Model):
    charges: tuple[ChargeStatus, ...]  # one per charge in the input
    records: tuple[RecordStatus, ...]  # each record or file with a problem of its own
    grants: tuple[GrantStatus, ...]  # each grant with a problem of its own
    questions: tuple[OpenQuestion, ...]  # every required question without a current answer
    notes: tuple[GrantNote, ...]


def ready_for_closeout(status: ChargeStatus) -> bool:
    """Decision 0022: Evidence complete, accepted or fully reversed, and not snoozed.

    The same as `status.ready`. The screens and the evidence report count with this.
    """
    return _ready(
        status.bucket, accepted=status.accepted, reversed=status.reversed, snoozed=status.snoozed
    )


def snapshot_of(
    statuses: Iterable[ChargeStatus], charges: Iterable[Charge], problem_rows: Iterable[str]
) -> SignOffSnapshot:
    """What a sign-off stores, and what the grant compares it with later (decision 0022).

    `charges` are the grant's charges and `statuses` their statuses. `problem_rows`
    are the keys of the rows on the grant's problem list.
    """
    statuses = list(statuses)
    charges = list(charges)
    counts: dict[Bucket, int] = {}
    for s in statuses:
        counts[s.bucket] = counts.get(s.bucket, 0) + 1
    return SignOffSnapshot(
        charges=tuple(
            ChargeSnapshot(
                charge_id=s.charge_id, bucket=s.bucket, accepted=s.accepted, reversed=s.reversed
            )
            for s in sorted(statuses, key=lambda s: s.charge_id)
        ),
        problem_rows=tuple(sorted(problem_rows)),
        totals=SnapshotTotals(
            ledger_total_cents=sum(c.amount_cents for c in charges),
            charges_total=len(charges),
            charges_ready=sum(ready_for_closeout(s) for s in statuses),
            accepted=sum(s.accepted for s in statuses),
            reversed=sum(s.reversed for s in statuses),
            bucket_counts=counts,
        ),
    )


class RunChecks(Protocol):
    def __call__(self, checks_input: ChecksInput, /) -> ChecksOutput: ...


def run_checks(checks_input: ChecksInput) -> ChecksOutput:
    """Rerun every check.

    Returns each charge's status, records and files with problems, the grant's
    problems, the open questions and the grant notes.

    Declared here as the interface only. W2 implements it in backend/app/checks/.
    """
    raise NotImplementedError("W2 implements run_checks in backend/app/checks/")
