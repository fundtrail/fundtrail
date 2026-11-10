# Demo

The grant, its problem list and one charge as the desktop web app, clickable. It runs the golden fixture's grant from Apr 9, 2026; the Light and Dark buttons in its top bar switch the theme.

**The story, in four clicks:**

1. **It opens on the problem.** The GrantHeader says 46 of 51 charges are ready for closeout, and the timeline shows today in red, after the grant's end date. Charge L-1002's evidence trail breaks at the award letter.
2. **Next arrival.** The clock moves to Apr 10 and the agent reads an extension notice from Google Drive. The new end date is a record at the top of the problem list, a term to confirm, so the list goes from 5 to 6. L-1002's trail points to it, and the timeline shows the new end date dashed.
3. **Confirm grant extension.** The term record leaves the list, L-1002's trail repairs (the award letter is replaced, the amendment turns blue) and the charge slides out of the list. 47 of 51 are ready, and today is back inside the grant. The problem list goes from 6 to 4. The boat rental, L-1015, stays: it has been missing its bill for 60 days since it posted on Jan 16, so it has been listed since Mar 17 whatever the end date. Snooze appears on rows from here on; before Confirm the grant was past its original end date, so the closeout window was open, and the window ends every snooze. Undo stays for 8 seconds.
4. **Next arrival again.** On Apr 12 a receipt photo arrives and the boat rental clears itself with no click: 3 on the problem list, 48 of 51 ready. The message has an Open receipt button.

L-1010, L-1015 and L-1019 are dated January 2026, inside the original period, so only L-1002 breaks the original end date.

Also clickable: the filter tabs, every row (each charge has its own trail), and the agent's Unsure on the microscope camera, which you can answer.

It follows the system's density rules and is built only from the system's classes; its script is the demo's own. Copy the layout and behavior as a starting point; the screens themselves belong to the app.

**The viewer.** Every trail link name, and every quoted passage, opens the viewer over the page at that fact (`FTViewer.open`). Esc or the close button returns focus to the link. The viewer scripts are built into this card from `components/_src/viewer-*.js`. For screenshots, `#v=F1&vf=End date` opens a file at a fact (F1 award letter, F2 amendment 01, F3 sequencing email, F4 approval email, F5 invoice SEQ-0311, F6 and F7 receipt photos).

**Ledger line numbers don't follow the dates.** L-1001 and L-1002 come from the golden fixture, so L-1010, L-1015 and L-1019 (dated January 2026) carry higher numbers than L-1002 (February 2026). Ledger systems number lines as they post, not by when the work was done.

## PR 6 (not merged yet)

This card follows grant-j-kim/fundtrail#6 (decisions 0010 to 0012).

- **The problem list holds records too.** When the extension notice arrives, the term waiting for confirmation is a record row at the top of the list ("New end date, Jan 31, 2027", tagged Term to confirm). Its panel has the term, its quote, Confirm grant extension and Reject amendment, and its own thread. L-1002's trail points to it with Review the term. Records sort first, a proposal: the PR leaves the sort open. Invoice 2050 isn't on the list until May 29, 2026, so the grant note banner is gone.
- **Missing evidence uses the 60-day rule.** A charge goes on the list 60 days after it posted, or 90 days before the end date in force, whichever comes first. L-1015 posted Jan 16, 2026, so it is listed from Mar 17 whatever the end date, and it stays on the list after Confirm until its bill arrives.
- **Each charge's panel:** the header with the ledger account and the agent's budget line, the evidence trail, the evidence checklist (FTChecklist), the review thread with the ask box (FTThread), then the history, folded. The answer and split forms stay in the trail. Every action writes to the thread.
- **Snooze and Accept with a note** are on the selected row and in the charge's header. Each takes the charge off the list with the inline done line and Undo; readiness doesn't change. Snooze needs the 90-day closeout window to be closed, because the window ends every snooze, so before the extension is confirmed (the grant is already past its original end date) only Accept with a note shows.
- **Asking the agent:** on L-1019, "Is the camera in the budget justification?" gets a scripted answer after a short read. Other charges and the term record get a short scripted answer too.

| Step | Problem list | Ready |
|---|---|---|
| Apr 9 | 5 | 46 |
| Apr 10, the extension notice arrives | 6 (the term record and 5 charges) | 46 |
| Confirm | 4 | 47 |
| Undo | 6 | 46 |
| Apr 12, the receipt photo arrives | 3 | 48 |
| Answer L-1019 | 2 | 49 |
| Split L-1010 | 1 | 50 |

Hash: `#s=2` opens with the term record selected; `#sel=R-01` selects it directly.

**Layout (the standard, option C).** Below the grant header, the problem list and the selected problem fill the rest of the screen and scroll separately; the page itself doesn't scroll. The problem's details scroll in the top of the right panel, and its review thread is docked at the bottom: newest entry last, scrolled to it, with the ask box always on screen. The dock takes 42% of the panel, or 67% with Show more. On short screens (a panel under 640px tall) it starts at about a third, never less than the newest entry plus the ask box, so the details keep more room. Picking another row slides the new details in quietly (none under reduced motion) and the dock switches to that problem's thread. Below 1024px wide the page falls back to normal scrolling. The layout script is built into this card by `tools/inline_layout.py` in the design system's tooling.

**When a problem leaves the list, the next one opens.** After Confirm, an answer, a split, the receipt arriving, a Snooze or an Accept, the charge that took its place opens on the right (else the one before it, else the empty state). The done line with Undo stays on screen and keeps focus while it shows; when it expires, focus moves to the newly selected row. Undo brings back the earlier selection. `#s=3` and `#s=4` open on L-0981, the first charge still on the list.
