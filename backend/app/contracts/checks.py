"""The checks' interface: a pure function from what's visible to each charge's bucket.

No database and no model inside, so the checks can be tested with hand-written records.
"""

from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from .base import Model
from .charges import Charge
from .evidence import EvidenceFile
from .records import Record


class Bucket(StrEnum):
    EVIDENCE_COMPLETE = "evidence_complete"  # every check passes on verified records
    POSSIBLE_CONFLICT = "possible_conflict"  # verified evidence contradicts a rule
    MISSING_EVIDENCE = "missing_evidence"  # something required isn't on file
    NEEDS_HUMAN = "needs_human"  # code can't decide safely


# Most serious first. A charge shows the most serious bucket among its reasons.
SEVERITY = (Bucket.POSSIBLE_CONFLICT, Bucket.NEEDS_HUMAN, Bucket.MISSING_EVIDENCE, Bucket.EVIDENCE_COMPLETE)


class Reason(Model):
    check: str  # stable ID of the check, for example "period_of_performance"
    bucket: Bucket  # where this check puts the charge; a pass is evidence_complete
    text: str  # status text, built by code
    record_ids: list[str] = Field(default_factory=list)  # the records this reason rests on


class ChargeStatus(Model):
    charge_id: str
    bucket: Bucket
    reasons: list[Reason]  # every reason, passes included

    @model_validator(mode="after")
    def _most_serious(self):
        if self.reasons:
            worst = min((r.bucket for r in self.reasons), key=SEVERITY.index)
            if self.bucket != worst:
                raise ValueError(f"bucket is {self.bucket} but the most serious reason is {worst}")
        return self


class TriggerKind(StrEnum):
    RECORD = "record"  # a record was written
    CHARGE = "charge"  # a ledger line arrived
    CLOCK = "clock"  # only time passed


class Trigger(Model):
    kind: TriggerKind
    id: str | None = None  # the record or charge; None for the clock


class StatusEntry(ChargeStatus):
    """One row of a charge's status history: its status from changed_at on."""

    changed_at: AwareDatetime  # the workspace clock's "now"
    trigger: Trigger


class ChecksInput(Model):
    """Everything in one workspace that's visible at the clock's "now".

    The caller filters by arrival and by written_at. Records include replaced
    ones; the checks call current_records themselves.
    """

    now: AwareDatetime
    charges: list[Charge]
    evidence: list[EvidenceFile]
    records: list[Record]


class ChecksOutput(Model):
    statuses: list[ChargeStatus]  # one per charge in the input


def run_checks(checks_input: ChecksInput) -> ChecksOutput:
    """Rerun every check and return every charge's status.

    W2 implements this in backend/app/checks/ with the same signature. Callers
    import it from there.
    """
    raise NotImplementedError("W2 implements run_checks in backend/app/checks/")
