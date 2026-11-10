"""The accountant's decisions on reasons and problems, and the problem list.

See contracts.md sections 5 and 8.


- An accepted reason covers the problem as it stood: the same check and problem
  on the same subject, while every record it rested on is still current and the
  reason rests on nothing new.
- A confirmed dispute accepts the disputed check's failing reasons, with the
  agent's reasoning as the note, while they rest on nothing written after the
  confirmation.
- A reusable note applies on its own to a later charge inside three limits: the
  same check and problem, the same ledger account and vendor, and an amount no
  larger than the largest accepted under the note. With the same check, problem
  and account but outside the vendor or amount limit, the note is offered.
- A snooze hides the problems it names until its date. A problem it doesn't name
  brings the subject back. Every snooze ends when the closeout window opens; one
  set inside the window lasts at most to the grant's end date.
- Flagged: Possible conflict and Needs a human right away; Missing evidence 60
  days past the date the item was expected, from the closeout window on, or right
  away for a missing approval. Accepted reasons don't flag, and snoozing hides.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.checks.findings import Finding
from app.checks.text import norm
from app.checks.view import GrantView
from app.contracts.charges import Charge
from app.contracts.checks import CLOSEOUT_WINDOW_DAYS, MISSING_EVIDENCE_DAYS, Bucket
from app.contracts.records import AcceptedReason, Decision, Dispute, Record, Snooze


def _later(charge: Charge, note: Record) -> bool:
    """Whether a charge is "a later charge" than a reusable note (call 36, ruling 3).

    It arrived after the note was written, or at the same time and was stored after it.
    The demo clock stands still between moves, so equal times are common. Unknown
    stored order isn't "after".
    """
    if charge.arrived_at != note.written_at:
        return charge.arrived_at > note.written_at
    return (
        charge.stored_seq is not None
        and note.stored_seq is not None
        and charge.stored_seq > note.stored_seq
    )


@dataclass(frozen=True)
class SubjectKey:
    charge_id: str | None = None
    record_id: str | None = None
    file_id: str | None = None  # all None: the grant itself


def _key_of(data: AcceptedReason | Snooze) -> SubjectKey:
    return SubjectKey(data.charge_id, data.record_id, data.file_id)


@dataclass
class Marked:
    """A finding with what the accountant decided about it."""

    finding: Finding
    accepted_by: str | None = None
    offered_note_id: str | None = None


class Decisions:
    def __init__(self, view: GrantView, now: datetime):
        self.view = view
        self.now = now
        self.accepted = [r for r in view.current if isinstance(r.data, AcceptedReason)]
        self.snoozes = [r for r in view.current if isinstance(r.data, Snooze)]
        self.charges = {c.id: c for c in view.charges}
        self.notes = [
            r
            for r in self.accepted
            if isinstance(r.data, AcceptedReason)
            and r.data.reusable
            and r.data.reuses_id is None
            and r.data.charge_id in self.charges
        ]
        self.confirmed_disputes = [
            r
            for r in view.current
            if isinstance(r.data, Dispute) and view.state.decision(r.id) == Decision.CONFIRMED
        ]

    # Accepting.

    def _stood(self, rests_on: Sequence[str], finding: Finding) -> bool:
        if not all(self.view.state.is_current(r) for r in rests_on):
            return False
        return set(finding.record_ids) <= set(rests_on)

    def _direct(self, subject: SubjectKey, finding: Finding) -> str | None:
        for r in reversed(self.accepted):
            data = r.data
            assert isinstance(data, AcceptedReason)
            if _key_of(data) != subject:
                continue
            if (data.reason.check, data.reason.problem) != (finding.check, finding.problem):
                continue
            if self._stood(data.rests_on, finding):
                return r.id
        return None

    def _dispute(self, charge_id: str, finding: Finding) -> str | None:
        for r in self.confirmed_disputes:
            data = r.data
            assert isinstance(data, Dispute)
            if data.charge_id != charge_id or data.check != finding.check:
                continue
            confirmation = self.view.state.decided_by(r.id)
            if confirmation is None:
                continue
            at = self.view.pos[confirmation.id]
            written_before = all(
                rid in self.view.pos and self.view.pos[rid] < at
                for rid in finding.record_ids
                if rid != r.id
            )
            if written_before:
                return r.id
        return None

    def limit(self, note: Record) -> int:
        """The largest amount accepted under a reusable note: its own charge's, raised by
        acceptances of the offer as "this and similar charges"."""
        data = note.data
        assert isinstance(data, AcceptedReason) and data.charge_id is not None
        amounts = [abs(self.charges[data.charge_id].amount_cents)]
        for r in self.accepted:
            d = r.data
            assert isinstance(d, AcceptedReason)
            if d.reuses_id == note.id and d.reusable and d.charge_id in self.charges:
                amounts.append(abs(self.charges[d.charge_id].amount_cents))
        return max(amounts)

    def _reusable(self, charge: Charge, finding: Finding) -> tuple[str | None, str | None]:
        offered: str | None = None
        for note in reversed(self.notes):
            data = note.data
            assert isinstance(data, AcceptedReason) and data.charge_id is not None
            if data.charge_id == charge.id:
                continue
            if (data.reason.check, data.reason.problem) != (finding.check, finding.problem):
                continue
            noted = self.charges[data.charge_id]
            if noted.account != charge.account or not _later(charge, note):
                continue
            same_vendor = (
                charge.vendor is not None
                and noted.vendor is not None
                and norm(charge.vendor) == norm(noted.vendor)
            )
            if same_vendor and abs(charge.amount_cents) <= self.limit(note):
                return note.id, None
            offered = offered or note.id
        return None, offered

    def mark_charge(self, charge: Charge, findings: list[Finding]) -> list[Marked]:
        out: list[Marked] = []
        subject = SubjectKey(charge_id=charge.id)
        for f in findings:
            m = Marked(f)
            if f.failing:
                m.accepted_by = self._direct(subject, f) or self._dispute(charge.id, f)
                if m.accepted_by is None:
                    m.accepted_by, m.offered_note_id = self._reusable(charge, f)
            out.append(m)
        return out

    def mark_other(self, subject: SubjectKey, findings: list[Finding]) -> list[Marked]:
        return [
            Marked(f, accepted_by=self._direct(subject, f) if f.failing else None) for f in findings
        ]

    # Flagging and snoozing.

    def window_opens(self) -> date | None:
        p = self.view.period
        return (
            p.end - timedelta(days=CLOSEOUT_WINDOW_DAYS)
            if p is not None and not p.disagree
            else None
        )

    def due(self, finding: Finding, posting_date: date | None = None) -> bool:
        """Whether a finding goes on the problem list now, before acceptances and snoozes."""
        if finding.shown_on_term:
            return False  # the term's own row, or the grant's, stands for it
        if finding.bucket in (Bucket.POSSIBLE_CONFLICT, Bucket.NEEDS_HUMAN):
            return True
        if finding.bucket != Bucket.MISSING_EVIDENCE:
            return False
        today = self.now.date()
        expected = finding.expected_by or posting_date or today
        window = self.window_opens()
        return (
            finding.flag_now
            or today >= expected + timedelta(days=MISSING_EVIDENCE_DAYS)
            or (window is not None and today >= window)
        )

    def _active(self, snooze: Record) -> bool:
        data = snooze.data
        assert isinstance(data, Snooze)
        until = data.until
        window = self.window_opens()
        p = self.view.period
        if window is not None and p is not None:
            if snooze.written_at.date() < window:
                until = min(until, window)
            else:
                until = min(until, p.end + timedelta(days=1))
        return self.now.date() < until

    def snoozed(self, subject: SubjectKey, flagging: list[Marked]) -> bool:
        active = [r for r in self.snoozes if _key_of(r.data) == subject and self._active(r)]  # type: ignore[arg-type]
        if not active:
            return False
        covered: set[tuple[str, str]] = set()
        for r in active:
            assert isinstance(r.data, Snooze)
            covered |= {(x.check, x.problem) for x in r.data.reasons}
        return all((m.finding.check, m.finding.problem) in covered for m in flagging)
