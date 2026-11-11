# Demo video: script and shot list

*Form: a live demo link (Google Drive, Loom, or unlisted YouTube), viewable by anyone with the link, 2 to 3 minutes.*

Target length: 2:50. The narration is about 400 words, read at a calm pace. Every amount, name and award number on screen is synthetic.

## Before recording

Everything the script needs is on main as of Nov 10 (PRs 218 to 223 merged), except one thing:

- **The prerun isn't built.** The choice is marked unavailable, so the recording uses "the larger sample, read live". The agent reads every arrival for real, so each jump waits on the model, and playing the whole sample costs model spend. **Ask Alex before playing it in full.**
- **Running locally:** follow CLAUDE.md's "Running things", with Docker running for the local database.
- **Rehearse first:** do one full run before recording, and note any beat that doesn't show what the script says.

How to record and edit: see [Recording and editing](#recording-and-editing) below.

## Moving the clock

"Next highlight" doesn't work yet (#267), so each beat uses **Go to a date**. It moves the clock to midnight UTC (Coordinated Universal Time) at the start of the day you pick, so each date below is the day after its highlight.

- **"Skip the human steps" off** when the beat's action is yours on camera. The clock stops on anything that's yours to deliver.
- **On** for every other jump, so the sample accountant makes the scripted decisions in between, such as confirming the rate agreement.

| Beat | Go to | Skip the human steps | What you do on camera |
|---|---|---|---|
| 02 Terms | (the sample opens here) | | Confirm the award letter's terms |
| 03 Receipt photo | Dec 31, 2024 | Off | Deliver for me |
| 04 Invoice first | Feb 11, 2025, then Feb 19, 2025 | On | |
| 05 Shared invoice | May 15, 2025 | On | Open the thread's suggestion |
| 06 Own approval | Sep 16, 2025 | On | |
| 07 Bill under its charge | Nov 13, 2025 | On | |
| 08 Same invoice twice | Nov 21, 2025 | On | |
| 09 Held mail | Jan 13, 2026 | Off | Let in |
| 10 Salary lines | Feb 20, 2026 | On | |
| 11 Moved off | Mar 10, 2026 | On | |
| 12 Over budget | May 6, 2026, then Jun 13, 2026 | Off | Accept with a note; confirm the increment |
| 13 Extension | Sep 15, 2026 | Off | Confirm the extension |
| 14 Closeout | Nov 3, 2026 | On | Sign off with a note |

Rehearse once first: check that each jump stops where the table says, and note any that doesn't.

## Fallback: the small sample

If the larger sample can't be played tonight, record the small sample ("Small sample, read live"). It works end to end on main, with three highlights. Target 2:15.

| # | Go to | Shot | Say |
|---|---|---|---|
| 01 | | Add a grant, "Small sample, read live", Open | "Automate the Old Way. When a research grant ends, a university has a few months to prove every charge followed the rules. That proof is scattered across email, shared drives and receipts. FundTrail keeps a running evidence file for every grant, so the proof is ready before anyone asks." |
| 02 | (opens here) | The agent reads the award letter (cut the wait). Grant terms, each value with its quote. Confirm all | "The agent reads the award letter and pulls out every term, each tied to the sentence it came from. Code checks each quote against the file, and nothing is used until the accountant confirms it." |
| 03 | Nov 17, 2026, skip off | The ledger posts and seven files arrive (cut the wait). The problem list, then the travel charge: its bucket, its checklist, the bills linked | "The ledger posts and the evidence arrives. Every charge gets a bucket and a checklist, and the agent links each bill to the charge it pays for." |
| 04 | Next event | The clock stops on the receipt photo. Deliver for me | "Some evidence only a person has, like this phone photo of a receipt. The charge waits for it." |
| 05 | Next event, then Nov 25, 2026 | The invoice arrives by Gmail before its charge. Then the ledger line posts and it links | "This invoice arrived before its charge posted. It waits, and links the moment the line shows up." |
| 06 | | On the travel charge, ask the agent "Do these cover this trip?" Its answer in the thread | "The accountant can ask the agent about any charge. It answers with its sources, and any change it proposes waits for a person." |
| 07 | | Closeout: the steps, what's still open, Make the draft, the evidence report | "At closeout, the review is already done, and the evidence report is ready to attach to Berkeley's closeout certification." |
| 08 | | The report scrolling, then the wordmark | "The agent reads and suggests. Code checks every rule it can. A person makes every final call. That's FundTrail." |

## Recording and editing

Record the screen first, then the voice. Claude then cuts the video together with ffmpeg.

### 1. The screen

- **Setup:** use macOS screen recording (Cmd+Shift+5, "Record Selected Portion") on the browser window.
  - Window size 1440 by 900, light theme, browser zoom at 100%.
  - Bookmarks bar hidden, notifications off (turn on a Focus).
- **One clip per beat,** named as in the table below. Start two seconds before the first click and stop two seconds after the result shows.
- **Don't stop for the agent's waits.** They get cut in the edit.
- **Move the mouse slowly,** and rest it on what the narration names, such as the highlighted passage or the bucket.
- **A mistake** means re-recording that one clip, saved as `-take2`.
- **Save the clips** in `~/Desktop/fundtrail-video/screen/`. Keep video out of the repo.

### 2. The voice

- **Record it after the screen clips,** so you narrate what actually happened.
- **One file per beat,** with the same number as its clip, such as `01-open.m4a`. QuickTime's "New Audio Recording" or Voice Memos both work.
- **Use a quiet room,** sitting the same distance from the microphone for every file.
- **Leave a second of silence** at the start and the end of each file.
- **Read the "Say" lines.** Change the wording wherever the screen turned out differently. Redo any line you stumble on.
- **Save the files** in `~/Desktop/fundtrail-video/voice/`.
- **Optional:** a webcam clip for the open and the close, which goes in a corner of the screen.

### 3. The edit (Claude, with ffmpeg)

- **Trimming:** each clip is cut to its action, and the agent's waits are sped up or cut.
- **Timing:** each clip is fitted to its voice file; the voice sets the length.
- **Titles:** a short title card names each highlight. Captions too, if wanted.
- **Audio:** even levels throughout.
- **Output:** one 1080p MP4 under three minutes.
- **Checking:** still frames from every cut are checked, then you watch it once from start to finish before uploading.

### 4. The upload

- **Where:** unlisted YouTube, Loom or Google Drive, set so anyone with the link can view it.
- **Check the link** by opening it in a private browser window.
- **Description:** "All data is synthetic. Agent processing time is shortened in editing."

### The clips

| # | File | Beat |
|---|---|---|
| 01 | `01-open` | Open |
| 02 | `02-terms` | Highlight 1: Terms tied to their passages |
| 03 | `03-receipt-photo` | Highlight 3: Receipt photo you deliver |
| 04 | `04-invoice-first` | Highlight 2: Invoice before its line |
| 05 | `05-shared-invoice` | Highlight 4: Shared invoice, 56 of 96 |
| 06 | `06-own-approval` | Highlight 5: Own fee, own approval |
| 07 | `07-bill-under` | Highlight 12: Bill under its charge |
| 08 | `08-duplicate` | Highlight 10: Same invoice twice |
| 09 | `09-held-mail` | Highlight 7: Held vendor email |
| 10 | `10-salary-lines` | Highlight 11: One report, six salary lines |
| 11 | `11-moved-off` | Highlight 7, continued: Moved off the grant |
| 12 | `12-over-budget` | Highlight 8: Over budget, then more money |
| 13 | `13-extension` | Highlight 6: Extension found in Drive |
| 14 | `14-closeout` | Highlight 9: Closeout |
| 15 | `15-close` | Close |

## Beats

Timeline order, as the larger sample plays them. Times are cumulative.

### 0:00 Open (15 s)
- **Shot:** the grant list, then Add a grant. Pick "The larger sample, read live" and click Open.
- **Say:** "Automate the Old Way. When a research grant ends, a university has a few months to prove every charge followed the rules. That proof is scattered across email, shared drives and receipts. FundTrail keeps a running evidence file for every grant, so the proof is ready before anyone asks."

### 0:15 Highlight 1: Terms tied to their passages (15 s)
- **Shot:** the Terms page for the award letter. Click a term, and the viewer opens with its passage highlighted ("Exact passage"). Confirm.
- **Say:** "We start at the award letter. The agent pulls out the terms, each tied to the exact sentence it came from. Code checks that quote against the file. Nothing is used until the accountant confirms it."

### 0:30 Highlight 3: Receipt photo you deliver (10 s)
- **Shot:** Go to Dec 31, 2024. The timeline panel's "Now" asks for the taxi receipt. The charge's checklist shows the receipt Missing. Click "Deliver for me".
- **Say:** "A sample grant has its own clock. Here a trip's taxi charge is missing its receipt until the professor sends the photo."

### 0:40 Highlight 2: Invoice before its line (10 s)
- **Shot:** Go to Feb 11, 2025: the invoice arrives by Gmail and waits on the Evidence page. Go to Feb 19, 2025: the ledger line posts, and the charge turns Evidence complete.
- **Say:** "An invoice can arrive before its charge posts. It waits, and links the moment the line shows up."

### 0:50 Highlight 4: Shared invoice, 56 of 96 (12 s)
- **Shot:** the charge page. The bill covers $5,833.33 of a $10,000.00 invoice, citing the email's "56 of 96 samples". Open the thread, where the agent's suggestion about the other grant waits for Accept or Reject.
- **Say:** "One invoice, two grants. The professor's email says 56 of 96 samples are ours, so that's the share linked here. The agent's suggestion about the rest waits for the accountant."

### 1:02 Highlight 5: Own fee, own approval (10 s)
- **Shot:** the problem list, then the charge page in Possible conflict, with the reason.
- **Say:** "The professor approved her own conference fee. It cites the email, and it stays a possible conflict: wrong approver."

### 1:12 Highlight 12: Bill under its charge (8 s)
- **Shot:** the charge page: a $1,260.00 charge, $1,200.00 of bills, Missing evidence.
- **Say:** "This bill is sixty dollars short of its charge. The freight bill never comes, and FundTrail won't pretend it did."

### 1:20 Highlight 10: Same invoice twice (8 s)
- **Shot:** the record's thread: the agent marks the Drive scan as a duplicate of the emailed invoice.
- **Say:** "The same invoice shows up twice, by email and as a scan. The agent marks the copy, so nothing counts twice."

### 1:28 Highlight 7: Held vendor email (12 s)
- **Shot:** Held mail in the sidebar. Click "Let in". The charge moves to Possible conflict, with the alcohol rule.
- **Say:** "Mail from an unknown sender is held until someone lets it in. Once it's read, the dinner invoice shows wine, which federal grants never pay for."

### 1:40 Highlight 11: One report, six salary lines (8 s)
- **Shot:** a salary line's charge page, its effort report linked, the checklist Filled.
- **Say:** "One effort report covers six months of the postdoc's salary, and every one of those lines."

### 1:48 Highlight 7, continued: Moved off the grant (8 s)
- **Shot:** the dinner charge's status history, and the correcting line, Evidence complete, citing its written justification.
- **Say:** "The department moves the dinner off the grant, with a written reason, and that correction gets its own evidence."

### 1:56 Highlight 8: Over budget, then more money (12 s)
- **Shot:** the grant page's budget figures over the limit, and the problem list's grant row. "Accept with a note". Go to Jun 13, 2026: confirm the increment's new limit on the Terms page.
- **Say:** "A field corer pushes spending past what's been awarded so far. The accountant accepts it with a note, and the next funding notice raises the limit."

### 2:08 Highlight 6: Extension found in Drive (12 s)
- **Shot:** boat time dated after the old end date, Possible conflict. The extension notice arrives from Drive. Confirm it on Terms, and the charge turns Evidence complete.
- **Say:** "This boat time is after the grant's end date, until the extension turns up in Drive. Once it's confirmed, the charge clears, citing the notice."

### 2:20 Highlight 9: Closeout (20 s)
- **Shot:** the Closeout page: Berkeley's steps, what's still open. Sign off with a note about the freight bill. "Make the draft" opens the evidence report PDF.
- **Say:** "At closeout, the review is already done. One charge is still open, so the accountant signs off with a note. The evidence report is ready to attach to Berkeley's closeout certification."

### 2:40 Close (10 s)
- **Shot:** the evidence report scrolling, then the FundTrail wordmark.
- **Say:** "The agent reads and suggests. Code checks every rule it can. A person makes every final call. That's FundTrail."

## If a beat runs long

Cut in this order: highlight 10, highlight 11, highlight 12. The open, highlights 1, 6 and 9, and the close carry the story.
