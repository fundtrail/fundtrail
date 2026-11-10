"""What build_report takes: everything already worked out by someone else."""

from pydantic import Field, model_validator

from app.contracts.base import Id, Model, UtcDatetime
from app.contracts.charges import Charge
from app.contracts.checks import ChecksOutput, StatusEntry
from app.contracts.evidence import EvidenceFile
from app.contracts.records import Record, SignOff
from app.contracts.workspaces import Grant, User

from .pending import ChargeLedgerState, HeldMessage, TermsInForce


class ReportInputs(Model):
    """One grant's evidence file at the workspace's "now", and the checks' output for it.

    The caller (W4's draft route and sign-off) gathers these. For a draft,
    sign_off is None. For a sign-off, it's the sign_off record being written,
    and now is its written_at.
    """

    grant: Grant
    now: UtcDatetime  # the workspace clock's "now" (decision 0023)
    preparer: User  # the accountant: one person per workspace for now
    charges: tuple[Charge, ...]
    files: tuple[EvidenceFile, ...]
    # Every record visible at now, in the order written, including replaced,
    # waiting and rejected ones. What counts comes from rules.RecordState.
    records: tuple[Record, ...]
    checks: ChecksOutput  # run_checks at now
    history: tuple[StatusEntry, ...] = ()  # the grant's status history up to now
    terms: TermsInForce = TermsInForce()
    ledger: tuple[ChargeLedgerState, ...]  # one per charge
    held_mail: tuple[HeldMessage, ...] = ()
    sign_off: Record | None = None
    # The rulebook's rule titles by rule ID, so an answer prints its rule's title (W1).
    rule_titles: dict[Id, str] = Field(default_factory=dict)
    # The text of plain-text and email files by file ID, so a quote prints its line number.
    file_texts: dict[Id, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self):
        charge_ids = {c.id for c in self.charges}
        if {s.charge_id for s in self.checks.charges} != charge_ids:
            raise ValueError("the checks' output has one status per charge")
        if {s.charge_id for s in self.ledger} != charge_ids:
            raise ValueError("ledger has one entry per charge")
        if self.sign_off is not None:
            if not isinstance(self.sign_off.data, SignOff):
                raise ValueError("sign_off is a sign_off record")
            if self.sign_off.written_at != self.now:
                raise ValueError("a signed report is built at the sign-off's own time")
        grant = self.grant.id
        everything = (*self.charges, *self.files, *self.records)
        if self.sign_off is not None:
            everything += (self.sign_off,)
        if any(x.grant_id != grant for x in everything):
            raise ValueError("every charge, file and record belongs to the grant")
        return self
