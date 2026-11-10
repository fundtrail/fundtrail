# 0007. Build a real app first, and decide the demo later

**Date:** 2026-11-07 · **Status:** accepted. Amended by [0027](0027-sample-grants.md) (no demo workspace is loaded at sign-up: a sample is one grant, chosen when adding a grant) and [0028](0028-one-clock-per-grant.md) (the clock belongs to each grant, not each workspace). [0027](0027-sample-grants.md) is the demo decision this file left open: precomputed results are used in the prerun sample only, never on a real grant or in the read-live samples.

## Context

The alternative was a scripted demo: one fixed scenario, with cached model responses and precomputed results. That's faster to fake, but it isn't a product, and it would break the moment a judge tried something new.

## Decision

- FundTrail is a multi-grant platform. Users sign in with Google, and a workspace holds many grants.
- A new account starts with a seeded demo workspace, and users can create more workspaces.
- It's built as a real app that works live, with no response cache.
- How we demo it gets decided later.
- Limits such as "accountant is the only user" and "NSF only" are for now. The design must leave room to grow.

## Consequences

- Every run calls Claude live, including eval runs.
- The clock is a real feature of each workspace, not a demo trick.
- Demo shortcuts, if we need any, get decided separately and must not change how the app works.
