# Demo video: script and shot list

*Form: a live demo link (Google Drive, Loom, or unlisted YouTube), viewable by anyone with the link, 2 to 3 minutes.*

Six of the larger sample's twelve highlights, about 20 seconds each, in timeline order. Target length: 2:40. The narration is about 300 words, read at a calm pace. Every amount, name and award number on screen is synthetic.

## Before recording

- **Alex's OK.** The prerun isn't on main, so this plays "Larger sample, read live from the start" with the real model: about 70 events, roughly an hour of agent time and real model spend. Ask Alex first. If there's no answer by about 9 PM, record the small-sample fallback below.
- **The play is the rehearsal.** The larger sample has never been played with the real model, so every "On screen" line below is what the sample's answer key expects, not something anyone has seen. Record the whole play (see "The clips"), then edit each beat's narration to what the screen actually showed before recording the voice.
- **Running locally:** CLAUDE.md's "Running things", with Docker running for the local database.
- **Labels:** the screens are being restyled tonight. Check each quoted button label on main before recording.

## Moving the clock

The timeline is one line at the top of the grant overview: "Sample timeline", the date, "Next event" and **More**. Click **More** to open the controls: "Next highlight", **Go to a date** (a date box and **Go**), the **Skip the human steps** checkbox and "Start over". "Go" stays disabled until you pick a date after today.

Every jump below is **Go to a date with Skip the human steps ticked**, so the sample accountant makes the scripted decisions in between. The jump lands at midnight UTC (Coordinated Universal Time) at the start of the day you pick, so each date is after the highlight and after the charge it affects, and before any scripted step you do yourself on camera.

| Beat | Go to | Why that date |
|---|---|---|
| 02 Terms | (the sample opens here) | |
| 03 Shared invoice | May 20, 2025 | The split email arrives May 14; its charge posts May 19 |
| 04 Held mail | Jan 14, 2026 | The email is held Jan 12; the dinner charge posts Jan 13; the scripted let-in is Jan 15 |
| 05 Budget | May 6, 2026, then Jun 13, 2026 | The corer posts May 5. The sample accountant accepts the overage May 6 at 17:00. The increment arrives Jun 12; its scripted confirm is Jun 15 |
| 06 Extension | Sep 9, 2026, then Sep 15, 2026 | Boat time posts Sep 8; the extension arrives Sep 14; its scripted confirm is Sep 15 at 17:00 |
| 07 Closeout | Mar 1, 2027 | Four more events arrive after the Nov 2 notice; the scripted sign-off is Mar 10 |

**Getting around:** the sidebar under the grant has Problem list, Evidence, Grant terms, Ledger and Closeout. It has no Overview entry yet, so get back to the overview from the grant's name in the workspace's Grants list, or "Back to the grant" on a charge.

## Beats

Click paths are from `ui-preview` at 0422786 (main plus the UI pull requests in review). Recheck the labels on main before recording.

### 0:00 Open (15 s)
- **Clicks:** the workspace home, then **Add a grant** (top right). On the **Sample** card, set **Which sample** to "Larger sample, read live from the start", click **Open**, then **Start it**.
- **On screen:** the grant overview, with the sample timeline stopped on the award letter.
- **Note:** the confirm line before "Start it" repeats the sample's name awkwardly. Click through it quickly, or cut it.
- **Say:** "Automate the Old Way. When a research grant ends, a university has a few months to prove every charge followed the rules. That proof is scattered across email, shared drives and receipts. FundTrail keeps a running evidence file for every grant, so the proof is ready before anyone asks."

### 0:15 Terms tied to their passages (20 s)
- **Clicks:** wait for the agent (cut the wait). Sidebar **Grant terms**. Under "Waiting for you", each term is a row with its quote underneath, the cited words highlighted. On the end date, click **Open the source**: the viewer opens at that passage. Back, then **Confirm all** (the number is however many terms the agent read).
- **Say:** "We start at the award letter. The agent pulls out every term, each tied to the sentence it came from, and code checks that quote against the file. Nothing is used until the accountant confirms it."

### 0:35 Shared invoice, 56 of 96 (20 s)
- **Clicks:** **More**, **Go to a date** May 20, 2025, Skip ticked, **Go**. Back on the overview, under "The grant's file", click **All charges**, then the row "16S library prep kit, shared" (L-1835-0014).
- **On screen:** the evidence trail: "invoice_EGS-20931.pdf" covering "$5,833.33 of $10,000.00", and "email_kit_split_basis.eml" as the basis for splitting the bill, with the 56-of-96 sentence.
- **Note:** a quote clicked on the charge page opens the file at the top, not at the passage. To show the passage highlighted, open the file's card from the sidebar's **Evidence** and click the value's quote.
- **Say:** "A year in, one invoice is split between two grants. The professor's email says 56 of the 96 samples are ours, so that's the share linked here, and code checks the arithmetic."

### 0:55 Held vendor email (25 s)
- **Clicks:** **More**, Go to Jan 14, 2026, Skip ticked, **Go**. Sidebar **Held mail**: the row "Invoice EFG-30418" from an unknown address. Click **Let in** ("Let in. It arrives now as evidence."). Wait for the agent. Sidebar **Problem list**, then the row "Field crew dinner, dry bags".
- **On screen:** Possible conflict, with "Allowable: The agent answered contradicts" and the rule NSF-NEVER-ALCOHOL. The rule's wording and the wine line aren't shown on the charge; to show the wine, open the invoice from the evidence trail and point at its line.
- **Say:** "Mail from an address nobody on the grant uses is held, unread, until someone lets it in. Once it's in, the agent reads the invoice and answers that the dinner isn't allowable: it includes wine, which a National Science Foundation award can't pay for."

### 1:20 Over budget, then more money (25 s)
- **Clicks:** Go to May 6, 2026, Skip ticked. On the overview: "Charged" is past "the award's $60,000.00 limit", and the first row under "things need you" is tagged **Grant**. Go to Jun 13, 2026, Skip ticked: the sample accountant accepts the overage with its note on the way. Sidebar **Grant terms**: on "notice_001_increment.txt", **Confirm all**. Back on the overview, the limit reads $120,000.00.
- **Note:** there's no button to accept a grant problem with a note yourself; only the sample accountant's skipped step does it. The timeline marks it as the sample accountant's decision.
- **Say:** "A field corer takes spending past what's been awarded so far. The accountant accepts it with a note, because more money is on the way. When the funding notice arrives, the agent reads the new total, and once it's confirmed, the limit rises."

### 1:45 Extension found in Drive (20 s)
- **Clicks:** Go to Sep 9, 2026, Skip ticked. Sidebar **Problem list**: the boat-time charge (L-1835-0033), "Dated Aug 31, 2026, after the grant's end date, Jul 31, 2026", Possible conflict. Go to Sep 15, 2026, Skip ticked. Sidebar **Grant terms**: on "extension_notice_002.txt", **Confirm all 2** ("All 2 confirmed."). Back to the overview, **All charges**, the boat-time row.
- **On screen:** the badge now reads Evidence complete, the date check is under "Passing", and "Status history" has one more change. It's off the problem list, which is why you reopen it from All charges.
- **Say:** "This boat time comes after the grant's end date. Then an extension, signed before the old date, turns up in Drive. Once the accountant confirms it, every check reruns and the charge clears, citing the notice."

### 2:05 Closeout (25 s)
- **Clicks:** Go to Mar 1, 2027, Skip ticked. Wait until the timeline no longer says "The agent is still catching up". Sidebar **Closeout**: the steps as a trail, then "Still open". In **Note**, type the note. Click **Sign off** ("Signed off ... The report now carries your sign-off."). Under "Evidence report", **Make the draft**, then **Open the draft (PDF)**.
- **Note:** if the agent is still working, Sign off answers "The agent is still working on this grant. Sign off once it's done." Wait and try again.
- **Check:** the answer key expects at least two charges open: the professor's own conference fee (Possible conflict) and the $1,260.00 charge with $1,200.00 of bills (Missing evidence). Say the number the screen shows.
- **Say:** "At closeout, the review is already done. Two charges are still open: a fee the professor approved herself, and a bill sixty dollars short. The accountant signs off with a note, and the evidence report is ready to attach to Berkeley's closeout certification."

### 2:30 Close (10 s)
- **On screen:** the evidence report's pages, then the FundTrail wordmark.
- **Say:** "The agent reads and suggests. Code checks every rule it can. A person makes every final call. That's FundTrail."

## If a beat runs long

Cut "Shared invoice" first, then "Over budget". The open, the terms, the extension, closeout and the close carry the story.

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
- **Record continuously** through the whole play (see "The clips" below). The edit cuts out each beat.
- **Don't stop for the agent's waits.** They get cut in the edit.
- **Move the mouse slowly,** and rest it on what the narration names, such as the highlighted passage or the bucket.
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

Because the clock only moves forward, a beat can't be redone without Start over, which resets the whole sample. So record the screen **continuously through one full play**, from Open to the report, and cut the clips out in the edit. Name the voice files by beat:

| # | Voice file | Beat |
|---|---|---|
| 01 | `01-open` | Open |
| 02 | `02-terms` | Terms tied to their passages |
| 03 | `03-shared-invoice` | Shared invoice, 56 of 96 |
| 04 | `04-held-mail` | Held vendor email |
| 05 | `05-budget` | Over budget, then more money |
| 06 | `06-extension` | Extension found in Drive |
| 07 | `07-closeout` | Closeout |
| 08 | `08-close` | Close |

