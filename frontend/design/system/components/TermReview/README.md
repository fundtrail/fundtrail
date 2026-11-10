# TermReview

The terms the agent read from a new award letter, reviewed by the accountant in one pass before any check uses them. Step 2 of adding a grant.

**The consumer provides** the agent's term records for the letter (period of performance, budget line, person, approval rule, other term), each with its citation, plus anything the agent flagged as missing.

- The list sits in an `ft-panel` as `ft-terms ft-terms--review ft-terms--flush`.
- One row per term: kind, value with its quote and location, then quiet actions **Correct** and **Reject** (`ft-overrule`). Rows appear one by one as the agent writes them.
- One main action for the whole set: **Confirm N terms** (`ft-btn--approve ft-btn--main`) in the panel footer (`ft-panel__foot`, sticky to the bottom of the panel). It writes one confirmation for every term not rejected. While the agent is still reading, it is disabled and says "Reading…".
- **Correct** and **Add email** open an inline edit under the value (`ft-inline-edit`: an `ft-input`, a small Save button, and Cancel as `ft-overrule`).
- A rejected row strikes the value through and keeps the quote readable, with **Rejected** and **Undo**. A corrected row says "Edited by you".
- A row that needs the accountant (`is-check`) has the needs-human tint, a one-line note on what is missing and why it matters, and one small button such as **Add email** or **Add the budget**. It does not block confirming.
- Quotes are plain serif here, no highlight: eight yellow marks in a row is noise. The highlight belongs in the viewer.

Don't: put Confirm and Reject buttons on every row, or color the list as a problem. Nothing here is wrong yet; it is waiting.
