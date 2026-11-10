# 0027. A sample is one grant, chosen when adding a grant

**Date:** 2026-11-10 · **Status:** decided by the product owner. Replaces [0024](0024-the-seeded-demo-workspace.md). The items marked "first version" were agreed to be built and judged running, and may change. Builds on [0007](0007-real-app-first.md), [0028](0028-one-clock-per-grant.md) and [0029](0029-workspace-members-and-one-access-check.md).

## Context

[0024](0024-the-seeded-demo-workspace.md) proposed a demo workspace loaded with a few grants at sign-up. That makes the demo a second kind of workspace, with its own clock controls and its own reset, and every new account pays to read a demo it may never open. It also left open who made the past decisions in a demo that opens in the middle of a grant.

Two scenarios set the shape.

- **Someone wants to see closeout in a few minutes.** They add a grant, pick the larger sample, prerun, and open it. The grant's past up to its opening date is already read and decided, and its clock sits at the opening date. From there they step through what's left of the grant.
- **Someone tries something the sample didn't plan for.** They forward a real email of their own to the sample grant, upload a receipt printed with next year's date, and reject a term the sample expected them to confirm. Nothing stops them. The email and the receipt arrive at the sample's "now", the receipt's printed date is used as written, and a few charges land in different buckets. The sample's next ledger line still posts on the day it was going to.

## Decision

- **Adding a grant offers two choices:** your own grant, or a sample. The sample choice has a dropdown with nothing chosen at first and three options:
  - a small sample, read live
  - a larger sample, read live from the start
  - the larger sample, prerun

  The description changes with the choice, and an Open button opens it.
- **A sample is one grant.** It sits in the user's ordinary workspace beside their own grants and is isolated like any grant. There's no demo workspace, and nothing is loaded at sign-up.
- **A sample grant is an ordinary grant** whose "now" is simulated ([0028](0028-one-clock-per-grant.md)) and which has a timeline of scheduled events: ledger lines posting, emails arriving, files appearing in Drive, and uploads. Nothing else about it is special.
- **Nothing is blocked on a sample grant.** The user can upload, email or drop in anything and decide anything. A file arrives at the sample grant's "now". A date printed inside a document is whatever is written there, and the checks use it as written.
- **The timeline doesn't react to the user.** Scheduled events never change with what the user does, and no scheduled event may depend on a decision of the user's. Leaving the expected path only changes which bucket a charge lands in.
- **Gmail and Drive work on a sample grant as on any grant.** A live email that arrives on a sample grant is dated to the simulated time. The stored original is unchanged.
- **Past decisions in the prerun belong to a made-up accountant.** Each workspace has its own: an account named "Sample accountant" that belongs to the workspace, is created with the workspace, and that nobody can sign in as. It's handled as a real user, with no special author kind. It's a member of its workspace ([0029](0029-workspace-members-and-one-access-check.md)).
- **What goes in each sample isn't decided:** the grants, people, amounts, situations and the timeline's events. The product owner settles it.

### First versions

These may change once they're seen running.

- **How the prerun is made.** A seeding step plays the sample's timeline up to its opening date with the real agent. Acting as a sample accountant, it makes the accountant's decisions through the app's ordinary paths, then saves the result. The prerun is made again whenever the agent, the rulebook or the sample changes, and it's released only if it matches the sample's expected results.
- **Opening the prerun** copies the saved grant into the user's workspace and points its past decisions at that workspace's sample accountant. Everything after the opening date is read live.
- **A timeline panel,** on a sample grant's page only. It shows:
  - what just happened, with what the agent did
  - what the clock has stopped on now: an item for the user to deliver, which the clock can deliver instead, and a count of what waits on the problem list, which stays the one place for reviews
  - what's coming up: arrivals, items to deliver, and dates the checks work out, such as a snooze ending

  Its controls are: next event, go to a date (forward only, with everything between played in order), and start over. It plays the timeline and doesn't edit it.
- **Start over** resets that one sample grant.
- **Reading the larger sample live** is limited to one at a time per account.
- **Two tests play each sample's timeline:** one as a user who does nothing, and one as a user who does everything the sample's expected results assume.

## Considered and set aside

- **One demo workspace loaded at sign-up.** A second kind of workspace, and every account pays for it.
- **A sample as its own workspace.** The user would switch workspaces to compare a sample with their own grants, and a workspace would carry special behavior.
- **Restricting a sample grant to its own prepared files.** The user couldn't try the app with their own evidence.
- **Blocking the user from leaving the expected path.** A sample that only works one way isn't the real app.
- **Crediting past decisions to the new user.** It puts words in their mouth.
- **One sample accountant shared by every workspace.** It would be a user outside the workspace writing into it.
- **Shifting a sample's dates to today's date.** The prerun quotes the dates printed in its files, so the dates can't move.

## Consequences

- [0024](0024-the-seeded-demo-workspace.md) is replaced. Its ordinary path for loading a seed survives as the samples read live, and its proposed saved read of the past becomes the prerun.
- [0007](0007-real-app-first.md)'s seeded demo workspace at sign-up no longer holds.
- The rule that only the accountant writes confirmations and the other decisions holds without change, because the sample accountant is a real user and a member of the workspace.
- A sample's dates are the ones printed in its files, so a sample grant's "now" can be far from today's date.
- Each live reading of a sample costs model calls, which is why the larger sample read live is limited to one at a time.
- The contracts add a sample grant's timeline and its items to deliver, and the saved prerun and its copy. Names and fields are open ([contracts.md](../contracts.md#not-decided-yet)).

## For review

The first versions above:

- the seeding step that makes the prerun, and releasing it only when it matches the expected results
- opening the prerun by copying the saved grant
- the timeline panel, its three parts and its controls
- one larger sample read live at a time per account
- start over resetting one sample grant
- the two tests that play each sample's timeline
