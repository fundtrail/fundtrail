# 0024. The demo workspace is built from a seed of files, and a saved read of its past waits for Alex

**Date:** 2026-11-10 · **Status:** Provisional: not yet reviewed by Alex. Builds on [0007](0007-real-app-first.md).

## Context

A new account starts with a demo workspace already loaded with a few National Science Foundation (NSF) grants, at least two of which share a cost ([product.md](../product.md)). The docs leave open how the seed is copied when someone signs up, what the data is, where the clock starts, and what a reset clears.

The hard question is the past. The demo is meant to open in the middle of a grant's life, so two years of charges and documents have already "arrived". Something has to have read them, and the accountant has to have confirmed the grant's terms.

- If the real agent reads them on every sign-up, each new account waits a long time and pays for well over a hundred charges' worth of model calls. It also opens with every term still waiting to be confirmed.
- If the reading is done once and its result copied in, sign-up is instant. But that is a precomputed result, and [0007](0007-real-app-first.md) set "cached model responses and precomputed results" aside until demo shortcuts are decided.

So this file splits in two: what gets built now, which is true to a real app, and one shortcut that is only proposed.

## Decision: built now

- **The seed is a set of files with their arrival dates:** award letters, ledgers and evidence. Loading it into a workspace goes through the app's ordinary paths: the files arrive, the real agent reads them, and the terms wait for confirmation. This path always has to work. Loaded this way, the workspace's clock starts at the seed's first arrival and jumps to the opening date, and the jump is replayed in order ([0023](0023-the-clock.md)). The user sees the opening date at once and the agent catching up, for as long as it takes to read the past.
- **The data.** A few NSF grants, all synthetic. Each example situation in [product.md](../product.md#demo-data-examples) appears as hand-written charges and documents. The rest of each ledger is ordinary charges with ordinary evidence, made by a script from templates, so a grant looks its real size. Every seeded charge has an expected result, written down the way an eval case's is.
- **Where the story sits in time.** The seed's dates put one grant near the end of its period, with more arrivals scheduled after the opening date for the clock to release ([0023](0023-the-clock.md)).
- **Reset is for the demo workspace only.** It stops any agent run in progress, removes everything in the workspace, including files the user uploaded or forwarded, loads the seed again and puts the clock back. A run that was in progress can't write into the fresh copy.
- **A workspace a user creates starts empty, on the real date.**
- **The seed pack for adding a grant from scratch** is a folder of files the user can drop in: an award letter, a ledger, emails, invoices and a receipt photo. Its ledger's later lines are dated ahead of the demo's opening date, so the clock releases them.

## Proposed, not built until Alex decides

This is a demo shortcut under [0007](0007-real-app-first.md), so it's his call.

- **Copy a saved read of the past.** A seeding step would run the app's own agent and checks over the seed's files up to the opening date, once, and save what they wrote. Signing up would copy the files and that saved result. Everything after the opening date would still be read live, while the user watches.
- **Past decisions would belong to a made-up accountant.** The confirmations in the saved result would be authored by a synthetic person, so the history never claims the new user did something they didn't. That needs a change to the rule that only a real signed-in accountant writes confirmations ([contracts.md](../contracts.md)).
- **The saved read would be made again whenever the agent changes,** and one that disagrees with the seed's expected results wouldn't be released.

Without the shortcut, the demo opens while the agent is still catching up on the past, and with the award letters' terms waiting, so the user confirms them first. That's the real flow for a new grant. It isn't the "middle of a grant" opening the product doc describes, and the catch-up is the wait and the cost the shortcut removes.

## Considered and set aside

- **Hand-written records that stand in for the agent's.** They'd drift from what the agent really does.
- **Opening at a grant's first day.** The interesting part, closeout, would be years of clock steps away.
- **Authoring past decisions as the new user.** It puts words in their mouth.

## Consequences

- The seeded demo workspace is built on the ordinary path first. Whether sign-up also copies a saved read waits for Alex.
- Mail already taken in from the app's mailbox isn't taken in again after a reset.
- Whether extra workspaces can be created is one of the scope questions waiting for Alex in [product.md](../product.md#not-decided-yet).

## For review

- The shortcut above: copy a saved read of the past, or have every new account read the seed live.
- If the shortcut is taken, who the seeded past decisions belong to.
