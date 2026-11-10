# ProblemRecords

Follows PR 6 (decision 0010), not merged yet. The problem list holds charges and records that have a problem of their own. A record row sits in the same `.ft-ledger` list as charge rows, with the same columns, and reads as a different kind at a glance: a small document mark before its name, "Record" where a charge shows its ledger line, and a neutral kind tag where a charge shows its colored bucket.

**Kinds** (`FTProblems.KINDS`): Term to confirm, Bill not charged (60 days after it arrived), Bill over-linked, Terms disagree, Duplicate file (raised by code), and Agent flag (anything else, with the agent's reasoning). The reason line ends with who raised it.

**Row actions** are quiet underlined buttons under the reason, shown only on the selected row so the list stays dense. Charges and most records get Snooze and Accept with a note; a term gets Review and Snooze (it leaves by Confirm or Reject); a duplicate gets Confirm duplicate and Not a duplicate. The same actions sit on the right side, in the thread. There's no resolve button.

**Sort (a proposal; the PR leaves it open):** records that change what the checks use, like a term waiting, first; then charges, most serious first, then oldest.

**Module:** `components/_src/problems.js`, inlined into this card. `FTProblems.recordRowHtml(rec)`, `rowActionsHtml(id, acts)` for charge rows, `bind(container, handlers)` (its click handler stops other listeners on the same list, so a row-select redraw can't drop the button a dialog returns focus to), `doneText(kind, target, result)` for the inline done line with Undo, and `stateTagHtml({state, until})` for a charge that left the list by a decision.

**Hash params:** `#sel=L-1010`, `#open=snooze`, `#open=accept`, `#t=dark`.

The first list is Example Bay on Apr 10, 2026. The second list is examples of every other kind; its IDs and dates aren't part of the demo grant.
