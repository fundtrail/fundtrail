"""Charges, and the ledger file they're read from.

One charge is one ledger line, read by code. The agent never writes charges.
"""

from datetime import date
from decimal import Decimal

from pydantic import AwareDatetime, Field

from .base import Model


class Charge(Model):
    id: str
    workspace_id: str
    grant_id: str
    # Unique within a workspace. Syncing or uploading the same line twice adds nothing.
    ledger_line_id: str
    transaction_date: date  # when the cost happened; the checks use this one
    posting_date: date  # when the ledger recorded it
    # When the line reached FundTrail; the clock uses this one. For an uploaded
    # ledger file it's 00:00 UTC on the posting date.
    arrived_at: AwareDatetime
    amount_cents: int  # negative for a reversal or a transfer out
    description: str
    account: str  # the expense account or category, as the ledger names it
    vendor: str | None = None
    reference: str | None = None  # invoice or document number, if the ledger has one
    # For a reversal or cost transfer: the ledger_line_id of the line it undoes or
    # moves. It may sit on another grant in the same workspace, or arrive later,
    # so it's a ledger line ID, not a charge ID.
    original_line_id: str | None = None


class LedgerRow(Model):
    """One row of a ledger file (CSV or Excel). The header row uses these names."""

    line_id: str = Field(min_length=1)
    transaction_date: date  # YYYY-MM-DD
    posting_date: date  # YYYY-MM-DD
    amount: Decimal = Field(decimal_places=2)  # dollars, for example 1240.00 or -1240.00
    description: str = Field(min_length=1)
    account: str = Field(min_length=1)
    vendor: str | None = None
    reference: str | None = None
    original_line_id: str | None = None

    @property
    def amount_cents(self) -> int:
        return int(self.amount * 100)
