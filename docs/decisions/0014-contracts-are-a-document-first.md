# 0014. The contracts are a document until the design is settled

**Date:** 2026-11-10 · **Status:** accepted

## Context

The contracts were written as code early, on November 7 to 9: record models, the checks' interface, API bodies, a database migration, a sample grant and its tests. [contracts.md](../contracts.md) said "the code is the truth" and explained it.

That code matched the design through [0009](0009-agent-judges-code-checks.md). The design review then produced [0010](0010-agent-suggests-accountant-decides.md) to [0013](0013-stack-additions-and-repo-structure.md), so the code fell behind the docs. A new session told that the code is the truth would build against a design that had already changed. The contract changes also can't be finished yet, because what each screen gets from the server depends on a UI flow that hasn't been discussed.

Alex's direction: no code until the design is settled, and a new session builds from the docs.

## Decision

- **[contracts.md](../contracts.md) is the source of truth for the contracts.** It describes them as designed, with the changes from 0010 to 0013 folded in.
- **The contract code is removed:** the models, the migration, the sample grant's files, its tests and the Python setup. The repo holds only the docs.
- **The contract code gets written from the document,** once the UI flow is settled. From then on the code is the truth again and the document explains it.

## Considered and set aside

- **Keeping the code and updating it later.** It's tested and would save some work. But until then it contradicts the docs, and most of it would be rewritten anyway: the changes touch the records, the rules for what waits, the statuses and every screen-facing body.
- **Updating the code now.** The screen-facing half would be a guess.

## Consequences

- Nothing runs. [CLAUDE.md](../../CLAUDE.md#running-things) says so.
- Prose is less exact than code. The rebuilt contracts may differ from the earlier ones in small ways, such as exact field names. Where a name matters, contracts.md gives it in `code style`.
- The sample grant is described in [contracts.md](../contracts.md#15-the-sample-grant) in enough detail to rebuild it: its terms, its two ledger lines, what arrives when, and the expected buckets.
- The earlier code stays in the repo's history. Commit `77483ae` is the last one that has it, under `backend/app/contracts/` and `supabase/migrations/`. It's a reference for whoever writes the new contract code, not a starting point to build against as is.
