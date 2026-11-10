# 0018. The agent works from lists of saved facts and opens files when needed

**Date:** 2026-11-10 · **Status:** accepted. Amends [0009](0009-agent-judges-code-checks.md).

## Context

[0009](0009-agent-judges-code-checks.md) has the agent look at anything on the grant with no filtering, and through everything rather than a shortlist. That can't mean reading every file again on every run. A three-year grant can have 2,000 ledger lines and 1,500 documents.

## Decision

- **The agent gets what just arrived in full, and the rest of the grant as lists:** one line per charge and one line per document, built from the facts already read and saved. It can search the lists and open any file in full.
- **Code still hides nothing.** The agent chooses what to look at.
- **The saved facts are the records the agent writes when a file first arrives.** It reads the whole file once, every value carries its quote, and code checks each quote against the file.
- **When the saved facts don't settle a question, the agent opens the file.** It's the same rule as for likely duplicates.
- **A bill gets an optional document number,** such as an invoice or order number. The ledger line often carries it, and it's the strongest match.
- **The agent puts anything else that identifies a document in its description:** names, order numbers, and the project or award number it mentions.

## Considered and set aside

- **Reading every file again on every run.** It doesn't fit a large grant.
- **A shortlist picked by code.** [0009](0009-agent-judges-code-checks.md) set it aside because filtering could drop the charge that's needed. That still holds: the lists cover everything on the grant.

## Consequences

- The saved facts are only as good as the first read. A detail nobody recorded is found only when the file is opened.
- On a small grant nothing changes, because the lists are short.
- The contracts add the bill's document number. Its name is settled with the other newer fields (see [contracts.md](../contracts.md#not-decided-yet)).
- The agent's exact actions and the wording of its prompts are still the builder's, discussed with Alex before building. That includes how the lists are built and searched.
