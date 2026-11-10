# 0019. The build order, and what the first build includes

**Date:** 2026-11-10 · **Status:** accepted. Amends [0014](0014-contracts-are-a-document-first.md).

## Context

[plan.md](../plan.md) had milestones and phases with dates that have passed, and the timeline was set aside. [0014](0014-contracts-are-a-document-first.md) made all of the contract code wait for the UI flow, which would hold up the records, the checks and the agent as well. Several areas of the product haven't been discussed yet, and Grant has made a design system and clickable screens.

## Decision

- **The work goes in this order, with no dates.** The two halves of a stage run at the same time.
  1. The remaining design, alongside the skeleton: the folders, an empty backend and frontend that deploy, the database, and automatic checks on every pull request.
  2. The contracts as code for records, checks and the agent side, alongside the test material: the sample grant redone to follow a real award letter, a first set of eval cases, and the National Science Foundation (NSF) rulebook.
  3. One thin path end to end: a file goes in, and a status shows on a screen.
  4. Everything else, in parallel.
  5. The full seed data and the blind test.
- **The first build includes everything except the optional features** in [product.md](../product.md#scope).
- **Areas that haven't been discussed aren't left out.** A first version of each is built and tracked as provisional, so it's easy to override once it's discussed and the first implementation isn't mistaken for a decision. [plan.md](../plan.md#built-first-discussed-after) lists the provisional areas. Whoever builds one records the choices they made for it in that list, in the same pull request. Each area stays in its doc's "Not decided yet" table too.
- **Parallelize as much as possible.** Inside each stage, the work is split across subagents or separate sessions wherever the pieces don't touch the same files. Shared files (contracts, migrations, docs) have one writer at a time.
- **The docs decide what the app does and what each screen holds.** Grant's design system and clickable screens (pull request 11, under `frontend/design/`) are inspiration for the look and the general layout. Where they differ from the docs, the docs win. Nothing waits on the mockup.

## Considered and set aside

- **A smaller first prototype,** with Gmail and Drive, photos and scans, the clock and the seeded workspace, the evidence report, snooze and reusable notes, and the blind test left for after.
- **Leaving out the areas that haven't been discussed** until they are. They get a provisional first version instead.
- **Waiting for the UI flow before any contract code.** The records, the checks and the agent side don't depend on the screens.

## Consequences

- [plan.md](../plan.md) holds the order, the provisional list and the parallel rule, and no dates.
- The contract code for records, checks and the agent side is written from [contracts.md](../contracts.md) in stage 2. What each screen gets from the server is still to write.
- A provisional area can be mistaken for a decision if its choices aren't recorded. The list in plan.md is the guard.
