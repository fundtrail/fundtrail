# ReviewThread

A charge's review thread, or one for a record with a problem of its own. It reads top to bottom: code's reasons, the agent's comments, suggestions and disputes, your replies and decisions, and a box to ask the agent. Follows PR 6 (decision 0010), not merged yet.

**Where it sits.** Docked at the bottom of the charge panel on the grant page and Charges (the standard layout). The charge's details scroll above it; the thread's entries scroll in their own area, newest last and scrolled to the end, and the ask box is pinned at the very bottom, so the chat is always on screen. It takes about two fifths of the panel; Show more makes it taller. Selecting another row swaps in that item's thread. Below 1024px wide it sits at the end of the item and the page scrolls as one. No floating chat widget or drawer. It is deliberately quieter than the trail: no connectors, thin rules between entries, 13px text. The trail says why the charge is in its bucket; the thread is the conversation around it.

**Authorship is always visible.** Each entry has a small mark and a word: Code (a check), Agent (a four-point star), You (a filled person, so your own entries stand out). Code's reasons lead with Fails, Passes or Missing. The agent's answers lead with Supports, Contradicts or Unsure, in the answer colors.

**Suggestions and disputes** are outlined boxes inside the agent's entry, with a `needs-human` outline while they wait and "waiting for you" in the head. A suggestion shows Now and Suggested; a dispute names the check it argues against and says what accepting does. Accept first (`ft-btn--approve ft-btn--main`), then Reject (`ft-btn--reject`). After a decision the box goes quiet: the replaced value is struck, the line says who decided and when, and the inline done line offers Undo for 8 seconds. A rejected suggestion says the agent can raise it again only if new evidence arrives.

**Asking the agent.** The ask box sits at the bottom, labeled with the charge. Its note says the agent answers about this charge only and that any change it proposes comes back as a suggestion. Sending clears the box, shows "Agent is reading this charge" and disables the box until the reply lands. Ctrl or Cmd with Enter sends. The reply is announced through a polite live region and only takes focus if you were still in this thread.

**The module.** `components/_src/thread.js` (built into this card by the design system's tooling):
- `FTThread.render(thread, opts)` returns the HTML.
- `FTThread.bind(container, thread, opts)` draws it and wires Accept, Reject, Undo and Ask. It returns `{ redraw }`.
- `thread`: `{ about: 'L-1019', entries: [...] }`. An entry: `{ who: 'code'|'agent'|'you', date, text, kind: 'reason'|'comment'|'suggestion'|'dispute'|'answer'|'decision', result?, answer?, quote?: { text, loc }, change?: { now, suggested }, check?, effect?, state?: 'waiting'|'accepted'|'rejected' }`.
- `opts`: `{ heading, ask, placeholder, today, undoMs, onAccept(entry), onReject(entry), onUndo(entry, was), onAsk(question, reply) }`. `onAsk` calls `reply({ text, quote })` when the agent answers.

**What's an example.** The L-1002 and L-1019 threads follow the demo story. The suggestion (a scan of receipt 0119) and the dispute (L-2003, a pre-award cost) are examples only; their files are not in the demo.

**Hash params:** `#hold=1` keeps L-1019's question pending, `#state=answered` shows the reply, `#decide=accept` or `#decide=reject` decides the examples, `#t=dark`.

Don't: let the thread decide anything on its own, or put thread messages in the evidence report. The report shows decisions only.
