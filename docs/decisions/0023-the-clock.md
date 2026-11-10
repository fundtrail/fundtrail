# 0023. Every workspace has a "now", and only the demo workspace can move it

**Date:** 2026-11-10 · **Status:** Provisional: not yet reviewed by Alex. Builds on [0007](0007-real-app-first.md). Amended by [0028](0028-one-clock-per-grant.md) (the clock belongs to a grant, not a workspace, and a live email on a sample grant is dated to the simulated time) and [0027](0027-sample-grants.md) (the demo workspace's controls and reset become a sample grant's timeline panel and start over).

## Context

A grant runs for years, and many rules depend on time: evidence flagged 60 days late, the 90-day closeout window, snoozes ending, a bill nobody charged. To show that in minutes, a workspace has a clock ([architecture.md](../architecture.md#the-clock)). The docs settle that each item has its own date and an arrival date, that an item counts once it has arrived, and that the clock only moves forward. They leave open the controls, what happens when the clock passes several arrivals, how time alone changes a status, and when an uploaded ledger line "arrives".

They also seem to disagree: the clock is "a real feature of each workspace", yet workspaces that users create "run on the real date".

## Decision

- **One idea removes the disagreement.** Every workspace has a "now", and every rule asks the workspace for it, never the computer's clock. In a workspace a user creates, "now" is the real time and nobody can move it. In the demo workspace, "now" is simulated and the user moves it. Nothing else in the app differs between the two.
- **Two controls, in the demo workspace only:** go to the next arrival, and go forward to a chosen date. There's no going back. Reset starts the workspace over.
- **Seeded items are stored from the start with an arrival date in the future.** They stay invisible until "now" reaches it. In a real workspace everything has already arrived, so everything is visible.
- **A jump is replayed in order.** If the clock moves past three arrivals, the agent handles them one at a time in arrival order, and each run works as of its own item's arrival time. The agent's work on those arrivals comes out the same as if the clock had stepped through them one by one. The screen shows the new date at once and that the agent is catching up. Anything the accountant writes while it catches up is stamped with the workspace's "now", the date the clock moved to. A question in a thread asked during the catch-up is answered once the catch-up is done, so the agent never answers with arrivals it hasn't read. This is the one case where a question doesn't go ahead of queued runs.
- **Time alone can change a status, and that needs no agent.** Code works the statuses out again when a record changes, as today, and also when time moves: when the demo clock moves, and once a day in a real workspace. A change that time caused is recorded in the status history on the day the rule was crossed, such as the sixtieth day, even when the clock jumped past it. The agent's one review of a grant when its closeout window opens is queued the same way.
- **When something arrives:**
  - A ledger line arrives at 00:00 UTC on its posting date if that's still ahead of "now", and otherwise now. In a real workspace that always means now. In the demo workspace it lets the clock release a ledger's later lines.
  - Anything uploaded, emailed or found in Drive arrives now, whatever date the document carries. The checks still use the document's own date.
- **Checking Gmail and Drive runs on real time.** What it brings in arrives at the workspace's "now".

## Considered and set aside

- **A clock per grant.** The workspace home and a cost shared by two grants need one "now".
- **Letting the clock go back.** Records are never edited, and ones written "later" would have to be hidden.
- **Handling a jump's arrivals all at once, as of the new date.** The order would vary from run to run, and something that arrived first could look older than the agent's answer about something later.
- **A simulated clock in any workspace.** Nothing needs it yet.

## Consequences

- [contracts.md](../contracts.md) says a ledger line always arrives at the start of its posting date. That changes to the rule above.
- A long jump takes as long as the agent needs for every arrival in between.
- The eval plays a case's arrivals the same way, so its answer key's times mean the same thing.
- A live email in the demo workspace arrives at the simulated "now" but carries its real sent date, which can be months later. The checks use that date as written, so a live approval can look late. The demo's own stories use seeded files.

## For review

The calls most likely to change: replaying a jump in order, which is slower but repeatable, and a real workspace's ledger lines arriving when they're uploaded.
