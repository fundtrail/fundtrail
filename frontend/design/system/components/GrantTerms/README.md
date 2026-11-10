# GrantTerms

The grant's terms after setup: what code checks charges against now, what changed them, what waits for the accountant, and the grant's standing notes. **A proposal:** PR 6 (not merged yet) lists the screens for confirming terms, the problem list, the checklist and the thread as not decided. This page follows PR 6: the agent's suggestions wait in each charge's review thread, not here.

**Layout.** The grant header (caption, title, readiness), then the split: the list on the left, the selected term on the right.
- **Waiting for you** comes first: new terms from an award letter or amendment. Each is also a record on the problem list ("Term to confirm"), so it can be decided from either place. Empty, it says so in one line and points to the charge threads for suggestions.
- **In force:** the terms checks use now, grouped as Dates, Budget lines (with charged and left), People and roles, Approval rules and Other terms. Each shows its quote and location; the quote opens the viewer at that fact.
- **Replaced or rejected:** kept for the record, struck through, and never used by a check.
- **Standing notes:** each note the accountant made standing when accepting a problem: what it excuses (problem, ledger account, vendor), who wrote it and when, the charges it covers, and Withdraw, which brings those charges back to the problem list. Empty by default. Where standing notes live is open in PR 6 ("the grant page lists each standing note"); this page is a proposal for it.

**The selected term** shows its state, its source, what it does (which check uses it and on how many charges; budget room for a budget line; the charges where a person or a rule matters), and its history with who did each step (Agent or You).

**Deciding.** Confirm and Reject work like the Demo's: the term moves, the readiness and the sidebar counts update, and an inline done line offers Undo for 8 seconds. Confirming amendment 01 moves the award letter's end date to Replaced.

**Counts follow PR 6's problem list.** Missing evidence is listed 60 days past the posting date, or 90 days before the end date in force, whichever comes first, so L-1015 (posted Jan 16, 2026) is listed from Mar 17, 2026 whatever the end date. A term waiting is a record row on the list. At `#at=apr10`: 6 on the problem list (L-1002, L-0981, L-1010, L-1019, L-1015 and the term) and 46 ready. Confirm: 4 and 47. Reject: 5 and 46. Undo restores 6 and 46.

**States, by hash:** default is Apr 12, 2026, nothing waiting, no standing notes. `#at=apr10` is Apr 10, with amendment 01's new end date waiting (Next arrival then moves the clock to Apr 12). `#state=notes` shows one example standing note: Example Cloud Storage bills a card and sends no invoice. It covers no charges: the grant's three storage charges from that vendor (L-0366, L-0556, L-0670, found in the report data) each have an invoice, so none has the note's problem. `#sel=<key>` selects a term (`end-new`, `end-old`, `line-0` to `line-2`, `pi`, `po`, `go`, `rule`). `#t=dark`.

**Built from data.** The page is generated from a template by the design system tooling: budget amounts, charge counts per line and the storage charges come from the report data, never typed by hand. Quotes come from the award letter and amendment 01 exactly as the viewer shows them. The standing notes list uses `FTProblems.standingNotesHtml` from the problem list module.

Don't: let a replaced or rejected term look usable, confirm a term without showing its source, or put the agent's suggestions back on this page.

**Layout.** The same two scrolls as the grant page and Charges: below the grant header, the list and the selected item fill the screen and scroll on their own, and the sidebar stays full height with the clock and Account in view. There is no thread dock, since files and terms have no review thread. A different item opens at its top with a quiet slide; a redraw of the same item keeps its place. Below 1024px wide the page scrolls as one. Built in from `tools/chat/split-scroll.js` by `inline_layout.py`, which the build runs.
