"""The checks' interface: a pure function from what's visible to each charge's bucket.

Code checks the clear-cut rules itself: dates against the period in force, the
link sums, whether evidence is linked, the approver's role and channel, budget
room, and that every quote appears in its passage. For what code can't settle,
it asks questions (records.Question), and the stored answers (judgments) feed
back in. There's no database and no model inside, so the checks can be tested
with hand-written records.
"""

from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from .base import Model
from .charges import Charge
from .evidence import EvidenceFile
from .records import Author, Question, Record

# Charges that are only under-covered stay off the problem list until this many
# days before the grant's end date, when Berkeley sends its first Notice of
# Expiration. Receipts with money never charged are listed on the grant from then on.
CLOSEOUT_WINDOW_DAYS = 90


class Bucket(StrEnum):
    EVIDENCE_COMPLETE = "evidence_complete"  # every check passes on verified records
    POSSIBLE_CONFLICT = "possible_conflict"  # verified evidence contradicts a rule
    MISSING_EVIDENCE = "missing_evidence"  # something required isn't on file
    NEEDS_HUMAN = "needs_human"  # code can't decide safely, or the agent is unsure


# Most serious first. A charge shows the most serious bucket among its reasons.
SEVERITY = (Bucket.POSSIBLE_CONFLICT, Bucket.NEEDS_HUMAN, Bucket.MISSING_EVIDENCE, Bucket.EVIDENCE_COMPLETE)


class Reason(Model):
    check: str  # stable ID of the check, for example "period_of_performance" or "charge_sum"
    bucket: Bucket  # where this check puts the charge; a pass is evidence_complete
    text: str  # status text, built by code. A judgment's own reasoning is shown from the judgment record.
    record_ids: list[str] = Field(default_factory=list)  # the records this reason rests on


class ChargeStatus(Model):
    charge_id: str
    bucket: Bucket
    reasons: list[Reason]  # every reason, passes included
    # On the accountant's problem list. Always for Possible conflict and Needs a
    # human. For Missing evidence, only from CLOSEOUT_WINDOW_DAYS before the end date.
    flagged: bool

    @model_validator(mode="after")
    def _consistent(self):
        if self.reasons:
            worst = min((r.bucket for r in self.reasons), key=SEVERITY.index)
            if self.bucket != worst:
                raise ValueError(f"bucket is {self.bucket} but the most serious reason is {worst}")
        if self.bucket in (Bucket.POSSIBLE_CONFLICT, Bucket.NEEDS_HUMAN) and not self.flagged:
            raise ValueError(f"a {self.bucket} charge is always flagged")
        if self.bucket == Bucket.EVIDENCE_COMPLETE and self.flagged:
            raise ValueError("an evidence_complete charge isn't flagged")
        return self


class OpenQuestion(Model):
    """A question code requires about a charge that has no current answer.

    An agent run can't finish while one is open for the agent. Unanswered, it
    puts the charge in Needs a human.
    """

    charge_id: str
    question: Question
    record_id: str | None = None  # the approval or other_term it's about
    # The agent, unless the accountant answered this question before and new
    # evidence has arrived since: then it goes back to the accountant.
    answer_by: Author


class GrantNote(Model):
    """Something about the grant as a whole rather than one charge.

    For example, at closeout: "Invoice 2050: $5,000 never charged. Paid another
    way, or charged to another grant?"
    """

    grant_id: str
    check: str
    text: str  # built by code
    record_ids: list[str] = Field(default_factory=list)


class TriggerKind(StrEnum):
    RECORD = "record"  # a record was written
    CHARGE = "charge"  # a ledger line arrived
    FILE = "file"  # an evidence file arrived
    CLOCK = "clock"  # only time passed, for example into the closeout window


class Trigger(Model):
    kind: TriggerKind
    id: str | None = None  # the record, charge or file; None for the clock


class StatusEntry(ChargeStatus):
    """One row of a charge's status history: its status from changed_at on."""

    changed_at: AwareDatetime  # the workspace clock's "now"
    trigger: Trigger


class ChecksInput(Model):
    """Everything in one workspace that's visible at the clock's "now".

    The caller filters by arrival and by written_at. Records include replaced,
    waiting and rejected ones; the checks call current_records themselves.
    """

    now: AwareDatetime
    charges: list[Charge]
    evidence: list[EvidenceFile]
    records: list[Record]


class ChecksOutput(Model):
    statuses: list[ChargeStatus]  # one per charge in the input
    questions: list[OpenQuestion]  # every required question without a current answer
    grant_notes: list[GrantNote]


def run_checks(checks_input: ChecksInput) -> ChecksOutput:
    """Rerun every check and return every charge's status, the open questions and the grant notes.

    W2 implements this in backend/app/checks/ with the same signature. Callers
    import it from there.
    """
    raise NotImplementedError("W2 implements run_checks in backend/app/checks/")
