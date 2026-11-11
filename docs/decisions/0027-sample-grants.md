# 0027. A sample is one grant, chosen when adding a grant

**Date:** 2026-11-10 · **Status:** accepted. Supersedes [0024](0024-the-seeded-demo-workspace.md). The items under "First versions", including the twelfth highlight, the next highlight control and what the small sample holds, were agreed to be built and judged running, and may change. What goes in the samples was decided on 2026-11-10, except the grants' people, amounts and dates. Builds on [0007](0007-real-app-first.md), [0023](0023-the-clock.md), [0028](0028-one-clock-per-grant.md) and [0029](0029-workspace-members-and-one-access-check.md).

## Context

[0024](0024-the-seeded-demo-workspace.md) proposed a demo workspace loaded with a few grants at sign-up, opening partway through a grant with a saved read of its past. That makes the demo a second kind of workspace, with its own clock controls and its own reset, and every new account pays to read a demo it may never open. It also left open who made the past decisions.

Two scenarios set the shape.

- **Someone wants to see closeout in a few minutes.** They add a grant, pick the larger sample, prerun, and open it at the start of its timeline. They go to a date past the grant's end and skip the human steps. The agent's work was done ahead of time, so they don't wait for it, and the panel shows which decisions the sample accountant made on the way.
- **Someone tries something the sample didn't plan for.** They forward a real email of their own to the sample grant, upload a receipt printed with next year's date, and reject a term the sample expected them to confirm. Nothing stops them. The email and the receipt arrive at the sample's "now", the receipt's printed date is used as written, and the agent works live from there. The sample's next ledger line still posts on the day it was going to.

## Decision

- **Adding a grant offers two choices:** your own grant, or a sample. The sample choice has a dropdown with nothing chosen at first and three options:
  - a small sample, read live
  - a larger sample, read live from the start
  - the larger sample, prerun

  The description changes with the choice, and an Open button opens it.
- **A sample is one grant.** It sits in the user's ordinary workspace beside their own grants and is isolated like any grant. There's no demo workspace, and nothing is loaded at sign-up.
- **A sample grant is an ordinary grant** whose "now" is simulated ([0028](0028-one-clock-per-grant.md)) and which has a timeline of scheduled events, such as ledger lines posting, emails arriving, files appearing in Drive, and uploads. Nothing else about it is special.
- **Every sample opens at the start of its timeline** and plays the same events, in all three choices.
- **Read live:** the agent works on each arrival as the clock reaches it.
- **Prerun:** the agent's work was done ahead of time, so the user doesn't wait for it. It isn't a grant that opens partway through with a saved past.
- **On both, the user can move to a chosen date,** closeout included, with the human steps skipped.
- **Nothing is blocked on a sample grant.** The user can upload, email or drop in anything and decide anything. A file arrives at the sample grant's "now". A date printed inside a document is whatever is written there, and the checks use it as written.
- **The timeline doesn't react to the user.** Scheduled events never change with what the user does, and no scheduled event may depend on a decision of the user's. Leaving the expected path changes what the app finds, never what the timeline delivers or when.
- **Gmail and Drive work on a sample grant as on any grant.** A live email that arrives on a sample grant is dated to the simulated time. The stored original is unchanged.
- **A made-up accountant makes the skipped decisions.** Each workspace has its own: an account named "Sample accountant" that belongs to the workspace, is created with the workspace, and that nobody can sign in as. It's handled as a real user, with no special author kind. It's a member of its workspace ([0029](0029-workspace-members-and-one-access-check.md)).
- **What goes in the samples** was decided on 2026-11-10, below. The grants' people, amounts and dates aren't decided yet. The product owner settles them.

### What goes in the samples

The product owner's brief: the sample shows the app's features, especially hard cases handled well. There are many events, and only a few are highlighted, chosen so that together they show the app's parts without repeating.

- **All three choices stay:** the larger sample prerun, the small sample read live, and the larger sample read live.
- **The larger sample is one grant of about 30 charges,** running its whole life, from the award letter to sign-off. Most charges are ordinary and clear on their own. Benefit lines sit beside salary lines and clear with them. They aren't a highlight ([0030](0030-benefit-charges.md)).
- **Its highlights:**
  1. The award letter arrives. The agent proposes the terms, each tied to its passage, and they're confirmed.
  2. An invoice arrives by email before its ledger line exists. It waits, then links when the line posts.
  3. A receipt photo that's the user's to deliver, by upload, email or Drive.
  4. An invoice shared with another award. An email gives this grant's share, and code checks the arithmetic. The agent's suggestion about the rest waits for the accountant.
  5. The professor's own conference fee on participant support, with her own "approved" email. It stays Possible conflict.
  6. A charge dated after the end date. An extension dated before the old end date turns up in Drive. The charge clears once the extension is confirmed.
  7. A vendor's email from an unknown address is held until it's let in. It holds a cost that isn't allowed, and a correcting ledger line later moves the charge off the grant.
  8. The budget. Spending goes over on a line and on the award's total. The accountant accepts it with a note, and a later notice that adds money raises the limit.
  9. Closeout: the closeout review, sign-off with one item open and a note, and the evidence report.
  10. The same invoice arrives twice, in different files, and is caught as a likely duplicate.
  11. One effort report clears several salary lines at once.
- **No scheduled event shows** snoozes and late flags, a note covering future charges, fixing a term the agent misread, or a cost before the start date.

### First versions

These may change once they're seen running.

- **Skipping the human steps.** "Next event" and "go to a date" each offer to skip the human steps. Then the workspace's sample accountant makes the decisions the sample's expected results assume, through the app's ordinary paths, as their author. Anything off that script is left for the user.
- **Read live with skipping** takes as long as the agent needs for everything in between.
- **How the prerun is made.** It saves the whole expected run-through: the sample's timeline played from its first event to its last with the real agent, while a sample accountant makes the scripted decisions through the app's ordinary paths. It's made again whenever the agent, the rulebook or the sample changes, and it's released only if it matches the sample's expected results.
- **When a saved result is used.** Only while the grant is still on that run-through: every accountant decision so far is the sample accountant's scripted one, none missing and none the user's own. Then moving the clock loads the saved result up to that point at once, copied in with the workspace's sample accountant as author.
- **Once the user makes a decision of their own,** saved results no longer apply as a whole. The agent works live from there, reusing a saved reading of a file where that reading doesn't depend on the grant's state.
- **The small sample** is read live only. It holds highlights 1 to 3.
- **A twelfth highlight** in the larger sample: a bill whose amount doesn't match its charge.
- **One larger read-live sample works at a time.** While one of a user's larger read-live samples has agent runs queued or running from a move of its clock, moving the clock of another is refused, with a line naming the one that's still working. Opening a sample or starting one over is never refused.
- **A timeline panel,** on a sample grant's page only. It shows:
  - what just happened
  - what the clock has stopped on now: an item for the user to deliver, which the clock can deliver instead, and a count of what waits on the problem list
  - what's coming up: arrivals and items to deliver

  Its controls are: next event, next highlight, go to a date (forward only), and start over. Next highlight moves to the next highlight with the human steps skipped. Moving forward plays everything between in order, as [0023](0023-the-clock.md) proposes. The panel plays the timeline and doesn't edit it. It marks a result loaded from the prerun as such, and shows which decisions the sample accountant made.

  Proposed details, kept for review: what the agent did on each event, under "what just happened"; the problem list staying the one place for reviews; and dates the checks work out under "coming up", such as a snooze ending.
- **Start over** resets that one sample grant.
- **Two tests play each sample's timeline:** one as a user who does nothing, and one as a user who does everything the sample's expected results assume.

## Considered and set aside

- **One demo workspace loaded at sign-up.** A second kind of workspace, and every account pays for it.
- **A sample as its own workspace.** The user would switch workspaces to compare a sample with their own grants, and a workspace would carry special behavior.
- **A prerun that opens partway through the grant with a saved past.** The user would miss the grant's start, and the three choices would no longer play the same events.
- **Restricting a sample grant to its own prepared files.** The user couldn't try the app with their own evidence.
- **Blocking the user from leaving the expected path.** A sample that only works one way isn't the real app.
- **Crediting skipped decisions to the new user.** It puts words in their mouth.
- **One sample accountant shared by every workspace.** It would be a user outside the workspace writing into it.
- **Shifting a sample's dates to today's date.** The prerun's saved readings quote the dates printed in its files, so the dates can't move.

## Consequences

- [0024](0024-the-seeded-demo-workspace.md) is superseded. Its ordinary path for loading a seed survives as the read-live choices. Its saved read of the past is set aside: what's saved now is the whole expected run-through, used only while the grant stays on it.
- [0007](0007-real-app-first.md) set cached and precomputed results aside until the demo was decided. This is that decision, for the prerun choice only. The prerun is made by the real agent through the app's ordinary paths. Nothing precomputed is used on a real grant or in the read-live choices.
- [0007](0007-real-app-first.md)'s seeded demo workspace at sign-up no longer holds.
- The rule that only the accountant writes confirmations and the other decisions holds without change, because the sample accountant is a real user and a member of the workspace.
- A sample's dates are the ones printed in its files, so a sample grant's "now" can be far from today's date.
- Each live reading of a sample costs model calls, which is why the larger sample read live is limited.
- The contracts add a sample grant's timeline and its items to deliver, the saved prerun and how it's loaded, and the sample accountant's user record. Names and fields are open ([contracts.md](../contracts.md#not-decided-yet)).

## For review

The first versions above:

- skipping the human steps, with the sample accountant making the scripted decisions
- read live with skipping taking as long as the agent needs
- how the prerun is made, and releasing it only when it matches the expected results
- using a saved result only while the grant is on the run-through, and loading it at once
- working live after the user's own decision, reusing saved readings of files that don't depend on the grant's state
- the small sample being read live only, and holding highlights 1 to 3
- the twelfth highlight, a bill whose amount doesn't match its charge
- the next highlight control on the timeline panel
- one larger read-live sample working at a time: moving another's clock is refused, with a line naming the one still working, while opening or starting over is never refused
- the timeline panel, its three parts, its controls, and how it marks prerun results and the sample accountant's decisions
- the proposed panel details: what the agent did on each event, the problem list staying the one place for reviews, and dates the checks work out under "coming up"
- start over resetting one sample grant
- the two tests that play each sample's timeline
