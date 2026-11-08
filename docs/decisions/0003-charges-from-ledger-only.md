# 0003. Charges come only from the ledger

**Date:** 2026-11-07 · **Status:** accepted

## Context

The university's general ledger already records everything charged to a grant: card purchases, invoices, payroll, stipends, reimbursements, internal charges and cost transfers. A second source of charges, such as a card feed or manual entry, would overlap with it.

## Decision

- Charges come only from ledger lines, which code reads. The agent never creates charges.
- **Real app:** FundTrail syncs new lines from the university's accounting system automatically, usually every night. Manual upload is a fallback for a system that isn't connected yet.
- **Hackathon build:** each grant gets one upload of its full-history file, as CSV or Excel. The clock releases its lines by posting date.
- Lines are matched by ledger line ID and only ever added. Corrections arrive as new lines.
- There's no card feed and no manual charge entry.

## Consequences

- A receipt that arrives before its ledger line waits, unlinked.
- A real-time card feed stays a later addition (see "Designed to grow" in [product.md](../product.md#scope)).
