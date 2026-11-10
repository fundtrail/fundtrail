# 0028. Each grant has one clock, and nothing else asks for the time

**Date:** 2026-11-10 · **Status:** accepted. Amends [0023](0023-the-clock.md): the clock belongs to a grant, not a workspace, and a live email on a sample grant is dated to the simulated time, where 0023 kept its real sent date.

## Context

[0023](0023-the-clock.md) gave every workspace a "now" and set aside a clock per grant, because the workspace home and a cost shared by two grants seemed to need one "now". [0027](0027-sample-grants.md) changes the ground under that. A sample is one grant in the user's ordinary workspace, so one workspace now holds grants on different times.

- **Two grants, two times.** The user's own grant runs on today's date. The larger sample, opened beside it, sits at a simulated date months before today. A note the accountant writes on their own grant has to carry today's date, and a confirmation on the sample has to carry the sample's date. A workspace clock can't give both.
- **One stray call.** A check asks the computer for today's date to decide whether a bill is 60 days late. On a real grant that works. On a sample grant it compares the sample's posting dates with the real date, and every charge looks late. The bug is invisible on a real grant, so it would ship.

## Decision

- **One clock per grant.** One place answers what time it is for a grant. A real grant's clock gives the real time. A sample grant's clock gives its simulated "now".
- **Apart from the machine's own uses below, nothing asks the system for the time,** and nothing branches on whether a grant is a sample. The code gets the simulated time right by being standard and centralized, not by special cases.
- **What goes through the clock:** arrivals, the date on every record and message, a run's date, what "today" means to the checks, the dating of live email and Drive files on a sample grant, status history, report and sign-off dates, and every date a screen shows.
- **What stays on real time,** because it belongs to the machine: the order records were stored in, background timers, logs, and sign-in expiry.
- **A check in continuous integration (CI)** fails new code that reads the system time anywhere else.
- **The clock belongs to a grant, not to a workspace.**
- **A live email on a sample grant is dated to the simulated time.** The stored original is unchanged. This amends [0023](0023-the-clock.md), which kept the email's real sent date.
- **The rest of [0023](0023-the-clock.md) stays as it is, provisional, and is read per grant:** each item's two dates, the arrival rules, a jump played in order, and a status that time alone changes. 0023's controls and reset for the demo workspace are replaced by a sample grant's timeline panel and start over ([0027](0027-sample-grants.md), first versions).

## Considered and set aside

- **A clock per workspace,** as in [0023](0023-the-clock.md). A workspace now holds real grants and sample grants side by side.
- **Letting each part of the code read the system time and adjust for samples.** One forgotten call puts a sample on the wrong date, and nothing on a real grant shows it.
- **Keeping a live email's real sent date on a sample grant,** as in [0023](0023-the-clock.md). A live approval would look months late.
- **Running stored order, timers, logs and sign-in expiry on a grant's clock.** They belong to the machine, and a simulated jump would reorder storage or end sign-ins.

## Consequences

- A cost shared by two grants doesn't need one "now": each grant is isolated for now, and each copy of the invoice is read on its own grant's clock ([0021](0021-a-cost-shared-by-two-grants.md)).
- Screens that show several grants show each grant's dates from its own clock.
- The contracts move the clock's routes and fields from the workspace to the grant. Names and fields are open ([contracts.md](../contracts.md#not-decided-yet)).
- Code that asks a workspace for its "now" changes to ask the grant.
- How the CI check recognizes a read of the system time is the builder's choice.
