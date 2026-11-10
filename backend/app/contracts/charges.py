"""Charges, and the ledger file they're read from (docs/contracts.md sections 6 and 13).

One charge comes from one ledger line, read by code. The agent never writes charges.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal

from pydantic import Field

from .base import Cents, Id, Model, Text, UtcDatetime


class Charge(Model):
    id: Id
    workspace_id: Id
    grant_id: Id
    # Unique within a grant: each grant is isolated, so two grants in one workspace
    # (two copies of a sample, say) can hold the same line ID as two charges. The
    # same line twice on one grant adds nothing.
    ledger_line_id: Id
    transaction_date: date  # when the cost happened; the checks use this one
    posting_date: (
        date  # when the ledger recorded it; the 60 days for missing evidence count from here
    )
    # When it reached FundTrail; the clock uses this one. For an uploaded ledger
    # file, see LedgerRow.arrival (decision 0023).
    arrived_at: UtcDatetime
    amount_cents: Cents  # negative for a reversal, a transfer out or a credit
    description: str
    account: str  # the ledger's own expense category, as the ledger gives it
    vendor: str | None = None
    reference: str | None = None  # an invoice or document number, as the ledger gives it
    # For a reversal or cost transfer: the ledger_line_id of the line it undoes or
    # moves. A line ID, not a charge ID, because the original may be on another
    # grant or arrive later. It's looked up on this charge's grant only.
    original_line_id: str | None = None
    # The order it was stored in: one number from a sequence the database shares
    # across records, charges and evidence files, so any two can be compared. Never
    # the workspace clock. None until it's stored.
    stored_seq: int | None = None


class LedgerRow(Model):
    """One row of a ledger file: CSV (comma-separated values) or Excel.

    The header row uses these names, in any order.

    An empty cell is a missing value: pass it as None.
    """

    line_id: Text
    transaction_date: date  # YYYY-MM-DD
    posting_date: date  # YYYY-MM-DD
    amount: Decimal = Field(decimal_places=2)  # dollars, negative for credits, for example -1240.00
    description: Text
    account: Text
    vendor: str | None = None
    reference: str | None = None
    original_line_id: str | None = None

    @property
    def amount_cents(self) -> int:
        return int(self.amount * 100)

    def arrival(self, now: datetime) -> datetime:
        """When an uploaded line arrives (decision 0023).

        At 00:00 UTC (Coordinated Universal Time) on its posting date if that's still
        ahead of the workspace's "now", and otherwise now. In a real workspace that
        always means now. In the demo workspace it lets the clock release later lines.
        """
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("the workspace's now is timezone-aware")
        midnight = datetime.combine(self.posting_date, time(), tzinfo=UTC)
        return midnight if midnight > now else now.astimezone(UTC)

    def to_charge(self, *, id: str, workspace_id: str, grant_id: str, now: datetime) -> Charge:
        """The charge this row becomes, uploaded at the workspace's `now`.

        line_id is ledger_line_id, amount is amount_cents, and arrived_at follows
        `arrival`.
        """
        return Charge(
            id=id,
            workspace_id=workspace_id,
            grant_id=grant_id,
            ledger_line_id=self.line_id,
            transaction_date=self.transaction_date,
            posting_date=self.posting_date,
            arrived_at=self.arrival(now),
            amount_cents=self.amount_cents,
            description=self.description,
            account=self.account,
            vendor=self.vendor,
            reference=self.reference,
            original_line_id=self.original_line_id,
        )
