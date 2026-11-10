# 0019. The build order, and how the build is run

**Date:** 2026-11-10 · **Status:** accepted. Amends [0014](0014-contracts-are-a-document-first.md).

## Context

[plan.md](../plan.md) had milestones and phases with dates that have passed, and the timeline was set aside. [0014](0014-contracts-are-a-document-first.md) made all of the contract code wait for the UI flow, which would hold up the records, the checks and the agent as well. Several areas of the product haven't been discussed yet, and Grant has made a design system and clickable screens. The plan also split the repo between Alex and Grant, with each person reviewing and merging up to three workers' pull requests.

## Decision

- **The work goes in this order, with no dates.** The two halves of a stage run at the same time.
  1. The remaining design, alongside the skeleton: the folders, an empty backend and frontend that deploy, the database, and automatic checks on every pull request.
  2. The contracts as code for records, checks and the agent side, alongside the test material: the sample grant redone to follow a real award letter, a first set of eval cases, and the National Science Foundation (NSF) rulebook.
  3. One thin path end to end: a file goes in, and a status shows on a screen.
  4. Everything else, in parallel.
  5. The full seed data and the blind test.
- **The first build includes everything except the optional features** in [product.md](../product.md#scope).
- **Areas that haven't been discussed aren't left out.** Before one is built, its design is worked through from first principles and written down as a decision file in `docs/decisions/` whose status line says "Provisional: not yet reviewed by Alex". Building follows that file. A provisional file can be overridden when it's reviewed, and a first implementation is never a decision. [plan.md](../plan.md#provisional-areas) lists the provisional areas and links each to its decision file once it's written. A builder who has to make a further choice inside a provisional area says so in the pull request description. Each area stays in its doc's "Not decided yet" table too.
- **Everything is built in this repo by agents,** including the folders that were Grant's. Alex decides the product.
- **The roles.** One session, the main coordinator, holds the design discussion with Alex, and all product questions and decisions flow through it. A build coordinator runs the build. Builders each take one issue in one area. A different agent reviews every pull request. A human assistant walks Alex through the steps only a person can do.
- **A reviewed pull request with passing tests merges straight to main.**
- **Parallelize as much as possible.** Inside each stage, the work is split across separate agents wherever the pieces don't touch the same files. As many builders run at once as reviews and merges can keep up with, with one writer at a time on shared files.
- **The design discussion continues while the build runs.** A new decision goes into the docs first, then to the build coordinator, then to the builder it affects. A change to work that's already merged becomes a new issue.
- **Every agent runs on Opus at medium effort or higher.** The contracts as code, the agent, the checks, the quotes, the eval cases and the reviewer run at high effort or above.
- **The docs decide what the app does and what each screen holds.** Grant's design system and clickable screens (pull request 11) are inspiration for the look and the general layout. Where they differ from the docs, the docs win. Nothing waits on the mockup.

## Considered and set aside

- **A smaller first prototype,** with Gmail and Drive, photos and scans, the clock and the seeded workspace, the evidence report, snooze and reusable notes, and the blind test left for after.
- **Leaving out the areas that haven't been discussed** until they are. Each gets a provisional decision file instead, and is built from it.
- **Waiting for the UI flow before any contract code.** The records, the checks and the agent side don't depend on the screens.
- **Splitting the repo between two people,** each merging their own workers' pull requests, with at most three workers per person.

## Consequences

- [plan.md](../plan.md) holds the order, the list of provisional areas, the parallel rule and how the build is run, and no dates. The workstreams stay as numbered areas of the repo, with no owner. [CLAUDE.md](../../CLAUDE.md) says who does what and holds the working rules.
- The contract code for records, checks and the agent side is written from [contracts.md](../contracts.md) in stage 2. What each screen gets from the server is still to write.
- A provisional decision could be mistaken for a reviewed one. Its status line says which it is.
