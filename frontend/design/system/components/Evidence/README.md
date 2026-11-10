# Evidence

The grant's Evidence page: every file the grant has, the facts the agent read from each one, whether each fact is confirmed in its file, and what each file pays for. Follows PR 6 (decisions 0010 and 0012, not merged yet). Same layout as the problem list: the grant header, then the files on the left and the selected file on the right.

**The list.** Every file, newest arrival first: the file name in Geist Mono, its kind and where it came from (Gmail, Google Drive, upload), the ledger lines it pays for, and the arrival date. Tabs: All and Not linked, with counts. A Kind select narrows it to award documents, bills, emails or photos, so the tab bar never overflows at laptop widths. Rows are focusable; up and down arrows move the selection, and Enter or Space selects.

**The selected file** is an evidence card:
- What it is, where it came from and when, and Open original (the viewer at the file's main fact).
- "Read from this file", labeled Agent, with a count on the right ("All 6 confirmed in the file", "1 of 6 unconfirmed"): each fact's value and its quoted passage, copied exactly, with the fact's own text marked, its line or page, and Confirmed. Clicking a quote opens the viewer at that passage. On a photo the fact says "Box checked by a second look" and opens the viewer zoomed to the box.
- **Unconfirmed facts** (decision 0012): the quote couldn't be placed in the file, or a photo's second look didn't read the same value. The quote shows with no mark, labeled Unconfirmed in the Needs a human color with its ring mark, and a short note says anything resting on it is in Needs a human until you settle it. Its quote opens the viewer's unconfirmed state, where Confirm or Type the right value settles it; the card then says "Confirmed by you" and keeps the quote unmarked.
- "Pays for": each charge it is linked to and how much of the file that charge uses ("$2,180.00 of $2,180.00"). The award letter and amendment 01 say what terms they set instead ("Used for").
- A bill linked to no charge (invoice 2050) is a record with a problem of its own (decision 0010), not a grant note: a dashed box with the question, the date it goes on the problem list (May 29, 2026, 60 days after it arrived, if still unlinked), and only Link to a charge, since it isn't on the problem list yet: "Goes on the problem list May 29, 2026, if it's still not linked." Snooze and Accept with a note appear once a record is on the list. Link to a charge isn't built in the demo and says so.

**Data.** Built by `tools/evidence/build.py` (in the design system's tooling) from the report data, the F1 to F7 viewer files and the golden fixture: 55 files, the 54 the evidence report cites plus invoice 2050. Nothing is typed by hand. invoice_1001.txt is the golden fixture's own document, so it opens in the viewer too. The generated bills have no original in this demo, and their cards say so instead of showing quotes.

**Hash params, for screenshots:** `#sel=F3` (a viewer file id) or `#sel=receipt_0936.pdf` (a file name), `#f=unlinked`, `#kind=photos`, `#state=unconfirmed` (one fact of invoice SEQ-0311 unconfirmed, on this card's copy only), `#t=dark`.

Don't: show quotes for a file whose original isn't on file, or mark more than the fact's own text inside a quote.

**Layout.** The same two scrolls as the grant page and Charges: below the grant header, the list and the selected item fill the screen and scroll on their own, and the sidebar stays full height with the clock and Account in view. There is no thread dock, since files and terms have no review thread. A different item opens at its top with a quiet slide; a redraw of the same item keeps its place. Below 1024px wide the page scrolls as one. Built in from `tools/chat/split-scroll.js` by `inline_layout.py`, which the build runs.

**Quotes on the card.** Each fact's quote is in the plain quote style used in the trail: serif, in quote marks, with its location. No yellow on the card; the highlight is the viewer's, when you click the quote.
