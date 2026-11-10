# AddGrant

The clickable "Add a grant" page in the app shell: the four steps from the award letter to the first evidence, using the from-scratch seed pack's letter (SYN-2400042, Coastal Wetlands).

1. **Award letter.** A drop zone. Clicking it drops award_letter.txt.
2. **Terms.** The file row reads, and terms appear one by one as the agent writes them. Each row has its quote and line, with quiet Correct and Reject. Two rows need the accountant: Dr. Jordan Rivera has no email address ("Add email"), and the other budget lines are in an attachment that isn't on file ("Add the budget"). Confirm 7 terms (10 once the budget is added) moves on.
3. **Ledger.** The done line with Undo, then a drop zone. The result: 38 charges added, 1 row skipped with its reason.
4. **Evidence.** The grant's email address to copy and an upload drop zone. The readiness bar fills as 14 files are read. Open the grant ends the flow.

**Hash params, for screenshots:** `#step=1` to `#step=4` opens a step. `&read=partial` stops step 2 mid-read. `&budget=1` adds the approved budget on step 2. `&email=1` adds Dr. Jordan Rivera's email. `&rej=go` rejects a term by key (`go` is Casey Lin). `&up=1` or `&up=reading` sets the ledger result. `&ev=1` or `&ev=partial` sets the evidence read on step 4. `&done=1` shows the finished state. `&t=dark` sets the dark theme.

**Uses:** AppShell, Steps, DropZone (drop zone, file row, results, skipped rows, copy field), TermReview, Field, Button, GrantHeader's readiness bar, and the trail's done line.

Don't: let a check use a term before Confirm, or hide which rows the ledger skipped.
