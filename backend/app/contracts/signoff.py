"""What a sign-off stores so the grant can show what changed since (decision 0022).

Signing off stores the evidence report as a Portable Document Format (PDF) file,
with its checksum and a snapshot of what 0022 counts as a change: each charge's
bucket, whether it's accepted or reversed, the problem list, and the totals. A
later change doesn't undo a sign-off. It shows, and the accountant can sign off
again. A comment or a link that changes no status doesn't count.
"""

from enum import StrEnum

from .base import Cents, Id, Model
from .buckets import Bucket


class ChargeSnapshot(Model):
    charge_id: Id
    bucket: Bucket
    accepted: bool
    reversed: bool


class SnapshotTotals(Model):
    ledger_total_cents: Cents  # the sum of the grant's charges
    charges_total: int
    charges_ready: int  # ready for closeout: checks.ready_for_closeout
    accepted: int
    reversed: int
    bucket_counts: dict[Bucket, int]


class SignOffSnapshot(Model):
    charges: tuple[ChargeSnapshot, ...]
    problem_rows: tuple[Id, ...]  # each problem-list row's key (api.problem_row_key)
    totals: SnapshotTotals


class ChangeKind(StrEnum):
    CHARGE = "charge"  # a charge's bucket, accepted or reversed state changed, or it's new
    PROBLEM_LIST = "problem_list"  # a row came onto the problem list or left it
    TOTAL = "total"  # one of the totals changed


class SnapshotChange(Model):
    kind: ChangeKind
    subject: Id  # the charge ID, the problem row's key, or the total's name
    before: str | None = None  # None when it's new
    after: str | None = None  # None when it's gone


def _charge_state(c: ChargeSnapshot) -> str:
    marks = (
        [c.bucket.value]
        + (["accepted"] if c.accepted else [])
        + (["reversed"] if c.reversed else [])
    )
    return " ".join(marks)


def changes_since(signed: SignOffSnapshot, now: SignOffSnapshot) -> tuple[SnapshotChange, ...]:
    """What changed between the snapshot stored at sign-off and one taken now."""
    changes: list[SnapshotChange] = []
    before = {c.charge_id: c for c in signed.charges}
    after = {c.charge_id: c for c in now.charges}
    for charge_id in sorted(before.keys() | after.keys()):
        b, a = before.get(charge_id), after.get(charge_id)
        b_state = _charge_state(b) if b else None
        a_state = _charge_state(a) if a else None
        if b_state != a_state:
            changes.append(
                SnapshotChange(
                    kind=ChangeKind.CHARGE, subject=charge_id, before=b_state, after=a_state
                )
            )
    rows_before, rows_after = set(signed.problem_rows), set(now.problem_rows)
    for key in sorted(rows_before - rows_after):
        changes.append(
            SnapshotChange(kind=ChangeKind.PROBLEM_LIST, subject=key, before="on the list")
        )
    for key in sorted(rows_after - rows_before):
        changes.append(
            SnapshotChange(kind=ChangeKind.PROBLEM_LIST, subject=key, after="on the list")
        )
    totals_before = signed.totals.model_dump(mode="json")
    totals_after = now.totals.model_dump(mode="json")
    for name in totals_before:
        if totals_before[name] != totals_after[name]:
            changes.append(
                SnapshotChange(
                    kind=ChangeKind.TOTAL,
                    subject=name,
                    before=str(totals_before[name]),
                    after=str(totals_after[name]),
                )
            )
    return tuple(changes)


class SignOffStateName(StrEnum):
    NOT_SIGNED = "not_signed"
    SIGNED = "signed"
    CHANGED = "changed"  # signed, and something changed since


def sign_off_state(signed: SignOffSnapshot | None, now: SignOffSnapshot) -> SignOffStateName:
    if signed is None:
        return SignOffStateName.NOT_SIGNED
    return SignOffStateName.CHANGED if changes_since(signed, now) else SignOffStateName.SIGNED
