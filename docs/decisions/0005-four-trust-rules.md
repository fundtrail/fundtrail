# 0005. Four simple trust rules

**Date:** 2026-11-07 · **Status:** accepted. Rules 1 and 3 amended by [0009](0009-agent-judges-code-checks.md).

## Context

An earlier draft added more rules: the accountant confirming every interpretation the model made, and tagging every fact as either a quote or an interpretation. That was too strict and too complex for the value it added.

## Decision

1. The model reads and links. Its links between documents are trusted.
2. One automatic check: each value has to appear in its cited passage. For photos and scans, which have no passage, the value has to match its ledger line instead. If the check fails, the charge goes to Needs a human.
3. Code does all rules and all math.
4. The accountant signs off on the packet.

The full wording is in [architecture.md](../architecture.md#trust-rules).

## Consequences

- The eval measures how often the agent's links are wrong. Link confirmation gets added only if that number is bad.
- The interpretation-confirmation and quote-or-interpretation tagging rules are dropped.
