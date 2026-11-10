# AcceptNote

Follows PR 6 (decision 0010), not merged yet. How a problem leaves the list when it won't fix itself. Both are dialogs built on the shared `ft-dialog-*` styles: focus starts in the first field, Tab stays inside, Esc, Cancel and the scrim close it, and focus goes back to the button that opened it. The page behind is inert.

**Accept with a note.** For a problem that will never fix itself and that the accountant is fine with. The note is required and goes into the evidence report under their name. The problem leaves the list and comes back if the facts change. For a charge, "Make it a standing note" covers every charge on the grant, past and future, with the same problem, ledger account and vendor, and the dialog shows exactly that problem, account and vendor and how many charges it covers today. Every other check still runs. A charge with no vendor can't have a standing note: the box is disabled and says why. Records get no standing option.

**Snooze until a date.** For a problem the accountant expects to fix itself. A date after today and a reason are required. It comes back on that date if it isn't fixed, or sooner if a new problem shows up, and every snooze ends when the 90-day closeout window opens (Nov 2, 2026 for Example Bay), so later dates are refused with that reason.

**Standing notes** are listed on the grant (the PR doesn't say which page yet): the note, what it excuses, who wrote it and when, and every charge it covers. Withdrawing a note brings those charges back to the problem list. A covered charge shows "Accepted under the accountant's note".

**Module:** `FTProblems.acceptDialog(opts, onDone)`, `snoozeDialog(opts, onDone)`, `acceptDialogHtml` and `snoozeDialogHtml` for static pictures, and `standingNotesHtml(notes)`. See ProblemRecords for the rest.

**Hash params:** `#open=accept`, `#open=novendor`, `#open=snooze`, `#open=error` (the note left empty), `#t=dark`. The two dialogs on the card are inert pictures; the buttons at the top open the real ones. The standing note's charges (L-2201 to L-2230) are an example, not part of the demo grant.
