"""What build_report takes: everything already worked out by someone else."""

from datetime import date

from pydantic import Field, model_validator

from app.contracts.api import BudgetView, TermView
from app.contracts.base import Id, Model, UtcDatetime
from app.contracts.charges import Charge
from app.contracts.checks import ChecksOutput, StatusEntry
from app.contracts.evidence import EvidenceFile
from app.contracts.mail import HeldMail
from app.contracts.records import Record
from app.contracts.threads import ThreadMessage
from app.contracts.workspaces import Grant, User


class Signing(Model):
    """The sign-off being made, as the report prints it.

    The report is built before the sign_off record is written, because that
    record carries the stored report's path and checksum. So W4 passes who signs,
    when, and the note the accountant sent (SignOffInput.note).
    """

    author_user_id: Id
    signed_at: UtcDatetime  # the workspace's "now" at the sign-off
    note: str | None = None


class ReportInputs(Model):
    """One grant's evidence file at the workspace's "now", and the checks' output for it.

    The caller (W4's draft route and sign-off) gathers these. For a draft,
    sign_off is None. For a sign-off, it's the sign-off being made, and now is
    its signed_at.
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
    # The grant page's terms (GrantDetail.terms); the report prints those that count.
    terms: tuple[TermView, ...] = ()
    budget: BudgetView | None = None  # the grant page's budget figures (GrantDetail.budget)
    end_date: date | None = None  # the end date in force (GrantSummary.end_date)
    # Mail still held at now: W4 keeps the messages for which rules.still_held is true.
    held_mail: tuple[HeldMail, ...] = ()
    # The grant's thread messages, so a history entry a message triggered reads as on screen.
    thread_messages: tuple[ThreadMessage, ...] = ()
    sign_off: Signing | None = None
    # The rulebook's rule titles by rule ID, so an answer prints its rule's title (W1).
    rule_titles: dict[Id, str] = Field(default_factory=dict)
    # The text of plain-text and email files by file ID, so a quote prints its line number.
    file_texts: dict[Id, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self):
        charge_ids = {c.id for c in self.charges}
        if {s.charge_id for s in self.checks.charges} != charge_ids:
            raise ValueError("the checks' output has one status per charge")
        if self.sign_off is not None:
            if self.sign_off.signed_at != self.now:
                raise ValueError("a signed report is built at the sign-off's own time")
            if self.sign_off.author_user_id != self.preparer.id:
                raise ValueError("the sign-off is the preparer's: one person per workspace")
        grant = self.grant.id
        everything = (*self.charges, *self.files, *self.records, *self.held_mail)
        if any(x.grant_id != grant for x in everything):
            raise ValueError("every charge, file, record and held message belongs to the grant")
        return self
