# 0002. The agent writes cited records, and code decides every status

**Date:** 2026-11-06 · **Status:** superseded by [0009](0009-agent-judges-code-checks.md)

## Context

If the model decides whether a charge is fine, its mistakes are hard to see, test or explain to an auditor.

## Decision

The agent reads evidence and writes records, each with its citation. Code runs every check and computes every status. Code also writes every status explanation. The agent never writes a status.

## Consequences

- The checks can be tested without the model, using hand-written records.
- The eval scores the agent and the checks separately (see [eval.md](../eval.md)).
- Every status can be traced back to its records, and every record to its source passage.
