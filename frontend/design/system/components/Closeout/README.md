# Closeout

The clickable closeout page for one grant, in the app shell: where the grant stands against Berkeley's closeout steps, what's left before the accountant signs off, and the evidence report with its sign-off.

**What it shows, top to bottom**
- **The grant head:** the award, its title, and "48 of 51 charges ready for closeout" with the readiness bar (`ft-grant-head`, `ft-ready`).
- **Berkeley's closeout steps** (`ft-co-steps`): today, the Notice of Expiration, the end date, the Award Closeout Certification due date, day 90 and day 120. The certification is the accountant's own deadline, so it alone gets a filled dot, a bold name and the "Your deadline" tag on the line. Dates are for an end date of Jan 31, 2027, from Contracts and Grants Accounting (CGA).
- **Before you sign off:** the charges that aren't Evidence complete, as list rows with their bucket and reason. Each opens the problem list.
- **Evidence report:** status (Draft or Signed off), as of date, pages and charges, Preview (`data-act="preview-report"`, calls `FTReport.open` when the page has it) and Download PDF.
- **Sign-off:** prepared by the accountant (you), a Note, and Sign off, the page's only main action (`ft-btn--approve ft-btn--main`). Under it: "Your supervisor approves the Award Closeout Certification in BFS. The report has a line for their signature."
- A quiet last line: attach the report to the certification in BFS (Berkeley Financial System), next to the CalAnswers ledger report. FundTrail files nothing with the university or NSF.

**Sign-off behavior**
- While any charge is open, the note is required. Signing off without it shows the field error "Add a note. It goes into the report next to the 3 open charges." and focuses the note.
- Sign off acts at once, with no "are you sure?". The inline done line "Signed off Apr 12, 2026. The report now shows your sign-off." takes focus, with Undo for 8 seconds. The status becomes Signed off, and the note shows read-only.
- Signing off adds `is-signed` to the `html` element, and Undo removes it. The report pages read it to swap Draft for the sign-off date.

**Proposals (not decided in docs/product.md):** the report's name, the sign-off flow (the accountant signs off here; the supervisor approves in BFS, so the report carries a blank Reviewed by block), signing off with charges open as long as there's a note, and whether a later change reopens a sign-off.

**Hash params, for screenshots:** `#signed=1` shows the signed state with a sample note, `&done=1` adds the done line, `#err=1` shows the missing-note error, `#t=dark` sets the dark theme.

**Uses:** AppShell, GrantHeader's readiness, ChargeRow, BucketBadge, Field, Button, the trail's done line. New styles are `ft-co-*`.

Don't: block sign-off on open charges, or let the page file or submit anything outside FundTrail.
