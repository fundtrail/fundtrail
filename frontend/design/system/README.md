FundTrail keeps a running evidence file for every research grant. The interface is a ledger that can show its work: every charge sits in one of four buckets, and every claim on screen leads back to the exact passage that supports it. Design for the person who prepares closeout (these docs call them **the accountant**): a professional at a desk, working a list, who needs to trust each line and find the few that need them.

Three ideas carry the whole system:

1. **A business tool, not a showpiece.** Neutral solid surfaces, rule borders, dense tables, a left sidebar. Nothing decorates. Color appears only where it means something.
2. **Highlighter means a citation.** `highlight` yellow sits behind quoted source text and nowhere else. If something is yellow, the user can click it and see the original.
3. **Every word has an author.** Status text comes from code, answers come from the agent or the accountant, and the interface always says which.

Parts marked **(PR 6)** follow grant-j-kim/fundtrail#6, which isn't merged yet: the word "bill", the bucket meanings, the problem list, the evidence checklist, the review thread, snooze and accept with a note, checked quotes and unconfirmed facts, and the report's decisions.

## Content fundamentals

- **Be direct and concise.** Short declarative sentences. Say what happened and what it means: "Work done after the grant's end date." Not "It looks like this charge might be outside the window."
- **Spell out acronyms on first use** in each view: "National Science Foundation (NSF)", "Award Cash Management Service (ACM$)". After that, the short form.
- **No em dashes.** Use a period, a comma, a colon or the middle dot separator.
- **No invented statistics, savings claims or percentages** in product copy, the README or the pitch. Show counts and amounts that come from the data.
- **Sentence case everywhere**, including buttons, headings, column headers and badges.
- **The bucket names are fixed** and always written exactly: Evidence complete, Possible conflict, Missing evidence, Needs a human. Never "Error", "Warning", "OK", "Flagged" or "Approved".
- **The agent's answers** are the words supports, contradicts and unsure. Capitalize only when the word starts a label: "Supports".
- **Name the three authors plainly:** "the agent", "the accountant", "code". Never "AI", "the model", "our system" or "Claude" in the interface.
- **Status text is built by code** from the check and its records, and reads as a plain statement: "Charged $2,180.00; bills on file cover $1,240.00." The agent's reasoning appears beside it, labeled as the agent's.
- **A bill (PR 6)** is any invoice, receipt or card slip. Use "bill" in generic labels ("Bills covering this charge", "A bill that adds up to the charge"); keep a document's own name for a specific file ("Receipt photo", "Invoice SEQ-0311").
- **Proposed until confirmed.** A term the agent read but the accountant hasn't confirmed is "proposed": "Proposed end date", "Proposes a new end date". Actions name their object: "Confirm grant extension", "Reject amendment". Under a decision, one line says what it changes: "Updates the grant end date to Jan 31, 2027 and rechecks its charges. 1 charge would become ready."
- **History lines** use the middle dot separator and an arrow for the change: "Apr 10, 2026 · new end date confirmed · Possible conflict → Evidence complete".
- **People as sources** end with who and when: "Link corrected by the accountant, May 22, 2026."
- **A record's problem (PR 6)** states the fact, then asks: "Invoice 2050: $5,000.00 nobody charged, 60 days after it arrived. Paid another way, or charged to another grant?"
- **Dates** in the interface are short month, day, year: "Feb 20, 2026". Dates quoted from a document stay as the document wrote them.
- **Money** in tables and status text shows cents: "$2,180.00". A part of a bill reads "$5,000 of $10,000", whole dollars when both amounts are.
- **IDs are copied, not reformatted.** Ledger lines (L-1002), invoices (SEQ-0207) and awards (SYN-2300117) appear exactly as the source writes them, in `id`.
- **Demo data is synthetic.** Award numbers start with `SYN-`; email addresses use the `.example` domain. Never put a real person, award or address in a mock-up.
- **What FundTrail does not say.** It files nothing with the university or NSF, so never write "Submitted", "Filed" or "Certified". The accountant attaches the evidence report; FundTrail prepares it. Don't describe it as receipt matching.

## Visual foundations

### Layout

- Every screen is the AppShell: a left sidebar at `sidebar-width`, a top bar at `topbar-height`, and the main area. It is a desktop web app first; on narrow screens the sidebar collapses, but nothing is designed phone-first.
- The sidebar holds the wordmark, the workspace switcher, a Workspace item (the workspace home), one Grants list where the current grant opens to its pages (Problem list, Charges, Evidence, Grant terms, Closeout), and the clock with an Account menu at its foot. Counts appear only where something needs the accountant.
- The top bar names the page (breadcrumbs: grant, then page) and the grant's end date, and holds page actions on the right.
- **Grant first, then list left and charge right.** Each grant page opens with the GrantHeader: the grant's name, how many charges are ready for closeout, and its timeline with today on it. Below it, the left side only lists (the problem list, most serious first) and the right side only shows the selected charge or record (`ft-split`). A problem that isn't about one charge, such as a term waiting or a bill nobody charged, is a row in the same list, not a banner (PR 6). Filter tabs with each bucket's count sit at the top of the list. Below the GrantHeader, the list and the selected item fill the screen and scroll on their own; the page itself doesn't scroll. The item's review thread is docked at the bottom of the right panel, so the chat with the agent is always visible next to the problem it's about. Opening the viewer (see The viewer, under Citations) is the only step that leaves the screen.
- A charge's details read top to bottom: its ID, date, ledger account and budget line (both, since a disagreement between them is a problem, PR 6), the bucket pill on the same line, then its name and amount on one line, then the **evidence trail** (Trail), the **evidence checklist** and History, closed, all in the panel's scrolling area; the **review thread** (PR 6) sits docked below them. The trail carries the reasons, bills and answers: each is a link, and the trail shows where it breaks. The agent's suggestions wait in the thread.
- **Laptop widths.** The layout holds from 1024px up and is tuned for 1280px and 1440px. Below 1280px the sidebar narrows to 208px. The list, the charge and the main area each adapt to their own width (container queries): a narrow list stacks each row's amount over its bucket and the tabs drop their marks; a narrow charge drops the stamp below the name; when the main area is under 900px the charge moves below the list and the GrantHeader stacks. Never let text wrap a word per line: rearrange instead. Below 1024px the two columns stop scrolling on their own and the page scrolls as one, with the thread at the end of the item.
- 4px base: `space-1` to `space-7`. Panels pad `space-4` sideways and `space-3` between sections; panels stack `space-4` apart; the main area pads `space-5`.

### Density

- **Open only what needs the accountant.** Failing reasons, anything waiting for them, and Contradicts or Unsure answers are shown. Passing checks ("2 checks pass"), a bill that covers the whole charge, a Supports answer and the history are single lines in an `ft-more` disclosure.
- **Color only where something needs the accountant.** Links that hold, links in general, the selection and the timeline's past are neutral; color is left for what breaks, waits or is missing, and for the one decision (Approve and Reject).
- **Say it once.** Never repeat what the sidebar or top bar already shows: no panel heading that names the page, no counts of everything, no award number beside the breadcrumbs.
- **Two scrolls, one dock.** On the grant page and Charges the list and the item scroll separately. The thread dock takes about two fifths of the right panel, newest entry last and scrolled to it, with the ask box pinned at the very bottom; Show more makes it taller. No floating chat widgets or drawers: the conversation stays attached to its item.
- **Space before lines, lines before boxes.** Sections inside a panel are separated by space. Box only the panels themselves and what the accountant must act on ("Waiting for you").

### Color

- Two neutral layers. The app background and sidebar are `paper`. Panels, tables, cards and the top bar are `paper-raised`. Table header rows, row hover and wells are `paper-sunken`.
- Borders do the separating: `rule` around panels and between rows, `rule-strong` around inputs.
- Set text in `ink`, and secondary text in `ink-muted`. Both hold 4.5:1 on every surface and every `-tint`, in both themes. There is no fainter text color: if it isn't worth `ink-muted`, cut it.
- `ledger` green is the brand, used very sparingly: the focus ring. Links are `ink`, quietly underlined; the active sidebar item and the selected row are `paper-sunken`. Green on screen means Approve, nothing else, and **ledger green never signals a status.**
- `approve` (a dark, teal-leaning green) and `reject` (the same red as `conflict`) are for the Approve and Reject buttons only.
- `highlight` is reserved for citations. Text on it is `on-highlight`. The passage the viewer is scrolled to is `highlight-active`. The box around a value on a photo or scan (`ft-box`) is a `highlight-wash` fill with an `ink` outline.
- Bucket colors appear only on bucket badges, reason lines and answer chips. See [Buckets](#buckets).
- Every color is solid. The only transparent value is `highlight-wash`, because it lies over a photo.

### Type

- Two working families. `sans` (Geist) is the whole interface, titles included. `mono` (Geist Mono) is for IDs only. `serif` (Newsreader) is used only for text quoted from evidence, so source words never look like interface words.
- Dense by default: `body` is 14px. The top bar's page title and a charge's name are `title`; panel headings are `heading`; amounts are `body-strong`.
- Badges, column headers and field labels are `label`. Dates, sources, page numbers, sidebar section labels and attribution lines are `caption` in `ink-muted`.
- `display` is only for the evidence report's cover and the closeout view's title.
- Quoted passages are `quote` on `highlight`, always with the page number or location in `caption` after them.
- Every column of amounts or dates sets `font-variant-numeric: tabular-nums` and right-aligns amounts.
- Keep reasoning, status text and quotes within `measure`.

### Buttons

- Every button is an outline over a solid fill. Neutral buttons: a 1px `ink` outline over `paper-raised`. Approve, Accept and Confirm: an `approve` outline, label and check over `approve-tint`. Reject: a `reject` outline, label and x over `conflict-tint`.
- The one action a view is for (Approve, Confirm, Sign off) gets `ft-btn--main`: a 2px outline. One per view.
- Approve or Accept always comes before Reject. With the darker teal green, the orange-leaning red, the thicker outline and the check and x, the pair never depends on red against green.
- `control-md` in the top bar, `control-sm` inside panels.

### Forms

- The accountant answers inline, at the trail link the answer settles (AnswerForm), never in a dialog: the evidence stays in view.
- Fields (Field) have a visible label, a hint or error under the control, and validate on save. Placeholders are examples.
- Every answer asks for a short reason, because it goes into the evidence report labeled as the accountant's.
- A live check says what a value would do before it is saved ("Covers this charge"), and saving shows the result with Undo where the accountant acted.
- Forms are neutral: no approve or reject colors, one neutral main button.

### Adding a grant

- Four steps, shown as a stepper (Steps): Award letter, Terms, Ledger, Evidence. Each starts with a drop zone (DropZone), and a dropped file becomes a file row with its state: Reading, then what was read.
- Terms appear one by one as the agent writes them, each with its quote and line (TermReview). No check uses a term until the accountant confirms it.
- Per row, the actions are quiet links: Correct and Reject. One main Confirm (`ft-btn--approve ft-btn--main`, "Confirm 7 terms") confirms the set; it is disabled and says "Reading…" until the agent finishes.
- Rows that need the accountant (`.is-check`, needs-human tint) say what is missing and what it blocks, with one small action: a person with no email address ("Add email"), or budget lines the letter leaves to an attachment that isn't on file ("Add the budget").
- After Confirm, the next step opens with an inline done line ("7 terms confirmed. Checks use them from now on.") and Undo, the same as in the trail.
- A ledger file shows what happened to every row: added, already on file, and skipped rows with the row number and the reason. Fixing a row and dropping the file again adds only what's missing.

### Charges, Evidence and Grant terms

- **Same shape as the problem list.** Each page opens with the GrantHeader, then `ft-split`: the list on the left, the selected item on the right. Only the list changes.
- **Charges:** every charge on the grant, not just problems. Bucket tabs with counts, a budget line filter and a search; newest first, sortable by amount. The right side is the charge exactly as on the problem list: its trail, the bills covering it with how much of each it uses, its checklist and thread (PR 6), and its history.
- **Evidence:** every file on the grant, newest first, with tabs for All and Not linked, and a Kind filter. The right side is the file's evidence card: where it came from, each fact with its quote, its location and whether it's confirmed (PR 6) (clicking one opens the viewer), and "Pays for", the charges it covers and how much of it each uses. A bill linked to nothing says so, with the date it joins the problem list: 60 days after it arrived (PR 6).
- **Grant terms (proposal):** "Waiting for you" first (terms to confirm, which are also rows on the problem list, or one line saying nothing is waiting), then "In force" grouped by kind, each with its quote, then "Replaced", struck through with what replaced it. Confirm and Reject work as in the trail: an inline done line with Undo. The agent's suggestions wait in each charge's thread, not here (PR 6).

### Borders, radii and shadows

- Flat. Panels are `paper-raised` with a 1px `rule` border and `radius-md`; no shadows. Inside a panel, sections are separated by space, not dividers or nested boxes. The bucket summary is an unboxed strip.
- Badges, inputs, sidebar items and highlight marks use `radius-sm`; buttons and panels `radius-md`; the viewer and dialogs `radius-lg`. `radius-pill` is only for sidebar counts.
- `shadow-float` is the only shadow, for what floats over the page: menus, dialogs, the viewer.
- Content the agent wrote carries the plain label "Agent". When it stands alone as a card (`ft-card--agent`), the card's outline is dashed `rule-strong`.

### States

- Focus: a solid 2px `focus` outline, offset 2px, on every interactive element. Never remove it.
- Hover on a row, sidebar item or neutral button: `paper-sunken`. Selected row: `paper-sunken` with a 2px `ink` bar on its left. Active sidebar item: `paper-sunken`.
- Disabled buttons get a dashed `rule-strong` outline and `ink-muted` text, with no fill; never reduce opacity on text.
- Rechecking: when the agent is answering again, keep the last bucket and add the Rechecking tag beside it. Don't blank the badge or show a spinner in its place.
- Waiting for the accountant: a `needs-human-tint` header reading "Waiting for you", or in the thread an outlined suggestion box with Accept and Reject (PR 6). It is the one box inside a charge.
- Undo instead of "are you sure?": Confirm, Approve, Accept and Reject act at once. Snooze and Accept with a note ask for a date or a note first, then act the same way. Their result and Undo appear at the end of the charge's trail, where the accountant acted (`ft-trail__done`, `role="status"`, focused after the change), for 8 seconds: "Extension confirmed. 47 of 51 charges ready. Undo". A Toast is only for what happens without a click.
- Closed by default: `ft-more` disclosures show a muted summary line ("2 checks pass", "History · 1 change") that opens in place.

### Motion

- Motion shows the product working, and nothing else. Four moments move:
  - **The recheck.** When a charge's bucket changes on screen, the bucket pill fades out (0.3s), the row turns `complete-tint` with its new badge for about a second, then collapses out of the list (0.35s) while the counts flash `is-bumped`.
  - **The agent at work.** A pulsing `ft-working-dot` in the top bar while the agent reads.
  - **The trail repairs.** When a fix is confirmed, the broken link turns Replaced, the fix turns into a blue check, the dashed line goes solid, and the GrantHeader's count and timeline update.
  - **The viewer.** It scrolls the active passage to the center and its mark fades in to `highlight-active` over 200ms.
- Nothing else animates: no hover motion, no page transitions, no spinners in place of a badge.
- Respect `prefers-reduced-motion`: every change happens at once, and the dot stops pulsing.

## Sign-in and workspaces

- **Sign-in:** one page without the app shell: the wordmark, one line on what FundTrail does, and one button, "Continue with Google". It is our own outlined `ft-btn ft-btn--main`; never draw Google's logo or copy Google's button styling. A fine-print line says the first sign-in creates a demo workspace with sample grants, all synthetic. Busy and error states change the button's text and add one line; nothing hides the page.
- **First sign-in (proposal):** the seed is copied into a new workspace named "Demo workspace". A short "Setting up your demo workspace" state lists what is being copied, with no percentages, then opens the workspace home.
- **Where you land (proposal):** the workspace home. Every grant is a row, sorted by its next deadline: name and award number, period, readiness ("48 of 51" with the thin bar), problem list count, the waiting count only when above 0, and the next deadline. A closed grant stays at the end, quiet. "Add a grant" is the page's one main action; an empty workspace shows the same action and one line on what happens next.
- **Menus** (`ft-menu-`): the sidebar's workspace block and Account button open them. One per trigger, anchored to it, `shadow-float`, `radius-md`. Focus goes to the checked workspace, or the first item, up and down arrows move, and Esc, an outside click or a choice closes it and returns focus to the trigger. The workspace menu lists the workspaces (the current one checked), New workspace (optional scope) and, in the demo workspace, Reset demo workspace. The account menu shows the name, email, "Signed in with Google" and Sign out.
- **Dialogs** (`ft-dialog-`): centered over the scrim, `radius-lg`, `shadow-float`, a title that says what happens. Focus stays inside; Esc closes and returns focus to what opened it.
- **Destructive confirms:** the title names the action and its scope ("Reset the demo workspace?"), the body says what is cleared and what isn't, the button repeats the verb ("Reset workspace", `ft-btn--reject`), and focus starts on Cancel, so Enter never destroys anything.
- **Reset (proposal):** clears everything done in the demo workspace (answers, confirmations, uploads, sign-offs) and sets its clock back to the seed's start. It never touches another workspace.

## Buckets

Every charge is in exactly one bucket. When several checks fail, the badge shows the most serious and the charge lists every reason. All four badges are the same soft pill: one height, at least 132px wide, a tinted fill in the bucket's color, no outline. The word, the mark and the color tell them apart:

| Bucket | Means (PR 6) | Mark | Tokens |
|---|---|---|---|
| Possible conflict | Verified evidence contradicts a rule, or an answer is contradicts | Diamond | `conflict`, `conflict-tint` |
| Needs a human | Code can't decide safely, the agent is unsure, a suggestion waits, or the charge rests on an unconfirmed fact | Ring | `needs-human`, `needs-human-tint` |
| Missing evidence | An item on the charge's evidence checklist isn't on file | Dashed ring | `missing`, `missing-tint` |
| Evidence complete | Every check passes, every checklist item is filled, and every answer is supports | Dot | `complete`, `complete-tint` |

- **Always show the word.** A bucket is never a color or a mark alone.
- On a charge's details the pill sits at the right end of the ID line, always in the same place, so the name never wraps around it. When the bucket changes, the pill fades out and the new one fades in.
- Evidence complete is blue, not green, so it never depends on red against green to differ from Possible conflict.
- The agent's answers are `ft-chip` colored words in the bucket they lead to.
## The problem list and the charge (PR 6)

### The problem list

- **Charges:** every Possible conflict and Needs a human charge. Missing evidence joins 60 days past the date an item was expected (the posting date by default), or 90 days before the end date in force, whichever comes first. A missing approval joins at once.
- **Records** with a problem of their own are rows in the same list: a term waiting for confirmation, a bill with money nobody charged 60 days after it arrived, a bill linked for more than its total, confirmed terms that disagree, the same file twice, and the agent's flags. Each has its own thread.
- Most serious first, then oldest (a starting point; the sort is open).
- **No resolve button.** A problem leaves when it fixes itself, when it's snoozed, or when it's accepted with a note, so the list never disagrees with the checks.

### The evidence checklist

- Every charge shows the evidence it should have: each item filled or missing, who added it (Default, Code, Agent, You), and any removal still waiting.
- Defaults come from the ledger account. Code adds a required approval when an approval rule applies. The demo uses "A bill that adds up to the charge" for all three of its accounts until the defaults are decided.
- The agent's added items take effect at once; a removal it suggests waits under the item, with Accept and Reject. The accountant's additions and removals take effect at once.
- A filled item names what fills it and how much of it the charge uses: "Invoice SEQ-0207 · $2,180.00 of $2,180.00". An item can name a period and when it's expected ("Effort report for January", not late before the quarter ends), and an amount rule shows its math, re-checked by code: "5 days at $100 a day = $500.00".

### The review thread

- Every charge, and every record with a problem, has one. It reads top to bottom: code's reasons, the agent's comments, suggestions and disputes, and the accountant's replies and decisions. Each entry opens with its author (Code, Agent, You) and date.
- **A suggestion** is an outlined box inside the agent's entry: what is now, what it suggests, its reason, Accept and Reject. **A dispute** is the same box naming the check the agent thinks is wrong, with its quote; while it waits, the charge is Needs a human. After a rejection, the same one doesn't come back without new evidence.
- **Docked, always visible.** On the grant page and Charges the thread is docked at the bottom of the item's panel, not below the trail: its entries scroll in their own area, newest last, and the ask box is always on screen. Clicking another row swaps in that item's thread. Show more makes it taller.
- **Asking the agent:** a box at the bottom. The agent answers about this charge only, ahead of its queued work, and shows "Agent is reading" meanwhile. Any change it proposes comes back as a suggestion.
- Messages stay with the charge and out of the evidence report, which shows only the decisions.

### Snooze, accept with a note and standing notes

- **Snooze until a date,** with a reason: "Refund coming, check Mar 1." It comes back on that date, sooner if a new problem arrives, and every snooze ends when the 90-day closeout window opens.
- **Accept with a note:** the note is required. The acceptance covers the problem as it stood; if the facts change, the charge comes back. It takes the charge off the list but doesn't make it Evidence complete.
- **A standing note** is one option in the same dialog. It covers every charge on the grant with the same problem, ledger account and vendor, past and future; a charge with no vendor only gets a one-off note. Covered charges read "Accepted under the accountant's note", the grant lists each standing note with the charges it covered, and withdrawing it brings them back.
- Both open a dialog (`ft-dialog-`), then act at once with the inline done line and Undo.

## Citations

- Every fact on an evidence card shows its quoted passage on `highlight`, its location ("p. 2" for a PDF, "lines 4 to 6" for text, "box on photo" for a photo or scan), and whether it's confirmed (PR 6). Grant terms show theirs the same way.
- **Quotes are checked against the file (PR 6):** exact characters for text and email, the passage found on its PDF page (an exact or close match), and on photos and scans a pixel box checked by a second look. A fact that can't be placed is unconfirmed, and anything resting on it is Needs a human until the accountant confirms the value or types the right one. Still no OCR (optical character recognition).
- In the charge, every link's name opens the viewer at its passage. Only the links that decide something (one that breaks the trail, one waiting for the accountant) show their quoted passage, in `quote` without yellow, with its location. Yellow appears only on evidence cards and in the viewer.
- Clicking a quote or a link's name opens the viewer at that passage.
- Never set a paraphrase on `highlight`. If it isn't verbatim from the source, it isn't yellow.

### The viewer

The viewer opens a file at one passage. It is a sheet (`ft-sheet`) that comes in over the app from the right, on a scrim (`ft-scrim`), and it is the only step that leaves the screen. Closing it returns to the same charge, scrolled where it was.

- **Head:** the file's title ("Award letter"), then its file name in `mono`, where it came from and when it arrived: "award_letter.txt · Uploaded by you · Jan 12, 2023". On the right, Download original and Close.
- **Bar:** what the passage is and how it was checked: "End date · Exact passage · line 15", or "Total · Box checked by a second look" (PR 6). On the right, zoom for PDFs and photos, then the passage pager ("6 of 10").
- **Document:** the whole original on `paper-sunken`, never cropped to the passage. Only the active passage is marked. The file's other cited passages are reached from the side list and the pager, so the page doesn't fill with yellow.
- **Side:** "In this file" lists every fact read from the file with its value and location. The active one has `aria-current` and an inset `ink` bar, and clicking another moves the mark. "Linked to" lists the charges the file supports and how much of each: "L-1002 · $2,180.00 of $2,180.00". A file of grant terms shows a note instead: "Grant terms. Confirmed by you, Jan 12, 2023."
- **Marks and boxes (PR 6).** Text, email, PDFs with real text and .docx get a `highlight-active` mark on the passage, found by character range or on its page. Photos and scans have no text layer and no OCR. They open zoomed to the box around the value, checked by a second look at the boxed area, drawn as `ft-box`, with "Show whole photo" to zoom out.
- **Unconfirmed facts (PR 6).** A fact that couldn't be placed opens to its page with no mark, and its quote shown beside the page with "Couldn't place this quote in the file", Confirm the value and Type the right value. The side list marks it Unconfirmed. Never guess a highlight.
- **Keyboard:** the sheet is a modal dialog. Focus moves into it on open and stays inside. Esc closes it and returns focus to the link that opened it. The pager moves between passages from anywhere in the sheet, and in the side list the up and down arrows do the same.
- **Motion:** the document scrolls the passage to the center and the mark fades in over 200ms. Under reduced motion it jumps there.
- **Narrow screens:** under 900px wide the sheet fills the screen and the side list is hidden. The pager still moves between passages.

## Closeout and the evidence report

FundTrail files nothing with the university or NSF. The review happens while the grant runs, so at closeout the accountant attaches the evidence report to the university's own step. Berkeley is the first template; only the report's format and labels follow the university.

| When | Berkeley's step | What FundTrail gives the accountant |
|---|---|---|
| 90, 60 and 30 days before the end date | Notice of Expiration: review every charge | The review is already done; only the problem list is left |
| End date | No new spending | The closeout page, with the steps and their dates |
| Until the close of the 2nd month | Adjustment period: move problem charges off the grant | Each open charge with its reason and what would close it |
| Close of the 2nd month | Award Closeout Certification in BFS (Berkeley Financial System), with a CalAnswers ledger report; the supervisor approves or denies it | The evidence report to attach, signed off by the accountant |
| By day 90 | CGA (Contracts and Grants Accounting) files the final financial report; for NSF, the amount in ACM$ | Nothing; FundTrail isn't involved |
| By day 120 | Anything missed needs a Closeout Exception Request | Nothing; FundTrail isn't involved |

### The closeout page

- **One job:** show what stands between the accountant and signing off. Top to bottom: the GrantHeader with its readiness, Berkeley's dated steps with today on them (the certification due date is the one emphasized), then two columns: "Before you sign off" lists each open charge as a compact row (ledger line, description, amount, bucket, reason) linked to the problem list, and "Evidence report" holds the report's status, its as-of date, its page count, Preview, Download PDF and the sign-off.
- **One main action:** Sign off is the only decision on the page, so it alone is `ft-btn--approve ft-btn--main`. After it, the inline done line with Undo, the report status reads "Signed off" and the note shows read-only.
- **Where the report goes,** in one quiet line at the bottom: attach it to the Award Closeout Certification in BFS, next to the CalAnswers ledger report. Never "Submit", "File" or "Certify".

### The evidence report

One PDF per grant on US Letter pages (`ft-rpage`). Every page has a running head (the report's name, the award in `mono`, the grant's title, and Draft with "As of" its date until signed off) and a foot with the page number.

- **Page plan:** 1 Summary. 2 and 3 All charges, one row per charge. 4 to 6 A section per charge: its checks, the evidence quoted from its sources, the answers, the accountant's decisions (PR 6) and the status history. 7 Open at sign-off, then Sign-off. 8 and 9 Sources, every file the report cites.
- **Decisions, not conversations (PR 6).** A charge's section shows every decision that changed what it needed or how it was judged: an accepted reason with its note (standing notes too), an accepted dispute with the agent's reasoning, a default checklist item the accountant agreed to remove, a confirmed duplicate, and a changed answer next to the earlier one. Thread messages, rejected suggestions and ended snoozes stay out.
- **Draft until signed off.** Every page says Draft and "As of" its date, and the report regenerates whenever a record changes. Once signed, the head reads "Signed off" with the date.
- **Totals match the ledger report.** The summary's total and the table's totals row equal the ledger lines to the cent. Counts and amounts come from the data, never typed by hand.
- **Quotes are exact,** in quote marks with the file name and location (line or page). A photo or scan names its checked box and quotes nothing. An unconfirmed fact says so (PR 6).
- **Answers are labeled** Agent or Accountant, with their reasoning. Code's checks are labeled Code.
- **Open charges stand out without color alone:** the bucket's word and mark, and a distinct row treatment in the table, so they read on a black and white printout.
- **The PDF prints light.** In the app the pages follow the theme; the printed or downloaded PDF always uses the light one.

### Sign-off (proposal)

- The accountant signs off in FundTrail: a `sign_off` record with a note, which only the accountant can write.
- Signing off with charges still open is allowed, but the note is required, and those charges are listed under "Open at sign-off".
- **Reviewer block:** the supervisor reviews and approves the certification in BFS, not in FundTrail, so the sign-off page carries "Reviewed by" with the supervisor's name and role and blank signature and date lines.

## Authorship

- Code's status text has no label; it is the system speaking. In the review thread and the evidence report, every entry is labeled Code, Agent or You (PR 6).
- The agent's work carries one label, the plain word **Agent** (`ft-tag--agent`), wherever it appears, suggestions and disputes included.
- The accountant's decisions carry an attribution line: "Answered by the accountant, Apr 10, 2026."
- When the accountant overrules the agent, show both, the accountant's on top.

## Iconography

- The repository has no icon set or logo yet. Set the name "FundTrail" in `sans` at 700 weight as the wordmark (`ft-wordmark`), in `ink`.
- The four bucket marks (diamond, ring, dashed ring, dot), the trail's nodes, and the check and x on Approve and Reject are drawn in CSS by `components/bundle.css`, so they take their element's color in both themes.
- Choosing an icon library for anything else is still open; until then, words only. No emoji anywhere.

## Components

Class-based and framework-free: load `tokens.css` and `components/bundle.css`, then use the `ft-` classes shown in each component's preview. The stylesheet imports the three Google Fonts families. Each component's README lists the contract fields it shows, so the Next.js screens can bind them straight to the API types.

- Layout: AppShell (an intentional addition: the docs leave screen layouts to the builder)
- Sign-in and workspaces: SignIn (the sign-in page and first-run setup), Workspace (the workspace home), WorkspaceMenu (the workspace and account menus, and the dialog pattern)
- Status: GrantHeader, BucketBadge, BucketSummary
- Charges: Trail, ChargeRow, StatusHistory, ReceiptCoverage (the bills covering a charge)
- Evidence: EvidenceCard, CitedPassage (the passage mark and the box on a photo)
- Viewer: ViewerSheet (the frame), ViewerText, ViewerEmail, ViewerPdf, ViewerPhoto, ViewerUnconfirmed (a fact that couldn't be placed, PR 6)
- Judgment: AgentAnswer, Suggestion, GrantTerm, ReviewThread and EvidenceChecklist (PR 6)
- Problem list (PR 6): ProblemRecords (record rows and their actions), AcceptNote (accept with a note, snooze, standing notes)
- Forms: Field, AnswerForm
- Adding a grant: Steps, DropZone, TermReview
- Grant pages: Charges (every charge), Evidence (every file), GrantTerms (terms, a proposal)
- Closeout: Closeout (the page: what is left, the report, the sign-off), EvidenceReport (the PDF's pages)
- Actions: Button and Toast (intentional additions: the docs name approve, reject, confirm and sign off, but no button style or undo)
- Demo: AddGrant, the four steps from award letter to evidence, clickable: terms appearing as the agent reads, Correct and Reject per row, Confirm with Undo, the ledger results and the readiness filling as evidence arrives.
- Demo: the grant, its problem list and a charge as the desktop web app, clickable: the clock's Next arrival, the evidence trail repairing on Confirm with Undo, the readiness count and timeline updating live, filter tabs, and a light and dark switch

## Not synced

The repository (grant-j-kim/fundtrail at 77f24d5) has no frontend, stylesheets, fonts, logo or icons yet. Bucket names, severity, answer words, the copy rules and every component's data come from it; every color, type, spacing, radius and shadow value here is new. Components are hand-written, class-based renditions in `components/bundle.css`, not built from code.

Open items for Adding a grant:

- The screen where the accountant confirms terms is still open in docs/product.md; this is a proposal.
- approved_budget.pdf amounts are placeholders until the seed pack has a budget.
- The seed letter's period ends Aug 31, 2025, before the demo clock.

Open items for Closeout and the evidence report (docs/product.md lists these as not decided; what's here is a proposal):

- The report's name, its layout, and the sign-off flow with a preparer and a reviewer.
- Signing off with charges still open, with a required note and an "Open at sign-off" list.
- Recording the reviewer as a blank signature block, since the supervisor approves in BFS.
- Whether a later change reopens a sign-off.
- How reversals and cost transfers show at closeout.
- Whether checks and reasons use Berkeley's cost criteria as labels.

Open items for Sign-in and workspaces (docs/product.md lists these as not decided; what's here is a proposal):

- What a workspace reset clears.
- How the seed is copied on sign-up, and the first-run setup state.
- The workspace home as the page you land on.
- Creating extra workspaces, which is optional scope.
- The clock controls the user sees (the sidebar's Clock and Next arrival).

Open items for Charges, Evidence and Grant terms (docs/product.md lists these as not decided; what's here is a proposal):

- The Grant terms screen, where the accountant confirms terms.
- PR 6 puts the agent's suggestions in each charge's thread, so Grant terms keeps only terms waiting.

Open items from PR 6 (not merged yet; its docs list these as not decided):

- The screens for confirming terms, the problem list, the checklist and the thread. The PR's layout ideas are the starting point.
- The default checklist for each ledger account, starting with Berkeley's account names. The demo uses "A bill that adds up to the charge" for all three of its accounts.
- How standing notes and confirmed duplicates are laid out, and where the grant lists its standing notes.
- How charges and records are sorted together on the problem list. A start: most serious first, then oldest.
- How the optional chat relates to review threads.
