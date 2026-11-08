# 0001. A running evidence file per grant

**Date:** 2026-11-06 · **Status:** accepted

## Context

The first build plan reviewed a grant once, at closeout. But the evidence for a grant arrives over years, and rules change along the way through extensions, budget moves and approvals. A one-time review finds problems only when it's too late to fix them.

## Decision

FundTrail keeps a running evidence file for every grant. As evidence arrives, it's connected to the charges, and the whole history gets rechecked. The closeout packet is ready when the grant ends.

For now, the scope is NSF grants only and direct costs only. The MCP server from the first plan is cut.

## Consequences

- The app needs a clock and an arrival date for every item (see [architecture.md](../architecture.md#the-clock)).
- Records are append-only, so history can be shown and replayed.
- Every status change is recorded, along with what triggered it.
- The difference from Ramp: FundTrail uses evidence Ramp never sees, and it rechecks the whole history.
