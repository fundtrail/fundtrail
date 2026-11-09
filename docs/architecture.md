# Architecture

## Overview

```
charges: ledger lines per grant ─► code ───────────────────────┐
                                                               ▼
evidence: Gmail · Drive · upload ─► AGENT ─► writes ─► RECORDS ─► CHECKS (code) ─► statuses + history
                                    1 read                     ▲
                                    2 write                    │
                                           accountant ─────────┘  confirms terms, enters splits, signs off
```

- **The agent** reads evidence and writes records. It never sets a status.
- **Records** are the single source of truth. A record is never edited. A correction is a new record that replaces the old one. The accountant writes records too.
- **Checks** are code. Every time a record changes, code reruns every check and recomputes every status. "What changed" is the difference between before and after.

## Inputs

### Charges: what was spent

- Charges come from the university's general ledger, the accounting system's record of everything charged to each grant. It already includes card purchases, invoices, payroll, stipends, reimbursements, internal facility charges and cost transfers.
- **Real app:** FundTrail connects to the university's accounting system (ERP, enterprise resource planning) and syncs new ledger lines automatically, usually every night. Nobody re-uploads anything. Manual upload is only a fallback for a system that isn't connected yet.
- **Hackathon build:** there's no real accounting system to connect to. Instead, each grant gets one upload of its full-history file, as CSV or Excel. The clock releases the lines by posting date.
- Lines are matched by ledger line ID, so a sync or an upload only ever adds new lines. A ledger corrects itself with new lines (reversals, cost transfers), so nothing is ever edited.
- Code reads ledger lines into charge records. The agent doesn't touch them.
- Each line has a transaction date, which the checks use, and a posting date. A line arrives in FundTrail when it's synced or uploaded.
- Each upload is for one grant.
- There's no card feed, because card purchases are already in the ledger, and there's no manual charge entry.
- A reimbursement is an ordinary ledger line. Its receipt usually arrives first and waits, unlinked, until the line posts.

### Evidence: why the spending was allowed

- **Gmail:** each grant gets its own email address on our demo account.
- **Google Drive:** the connector reads folders that users share with our demo account. Users never connect their own Google account.
- **Upload:** files can also be added in the app.
- Only email from known senders is processed: our accounts, the people named in each award letter, and anyone the accountant adds. Mail from anyone else is held for the accountant.
- Evidence that arrives before its ledger line waits, unlinked, until the line shows up.

### Files go to Claude as they are

PDFs, scanned PDFs and images are sent unchanged. The only exception is .docx, which Claude doesn't accept, so its text is extracted first.

## The agent

The agent is built on LangGraph and works in two steps:

1. **Read.** It sends the file to Claude.
   - For text and for PDFs with real text, citations are on, and the API itself returns each cited passage with its location: page numbers for PDFs, character ranges for plain text, block indexes for custom content documents.
   - For photos and scans, Claude reads the image and estimates a box around each quote. Claude's citations only work on text, so images have no API citation.
2. **Write.** It writes records that point to those passages. It never types a quote itself, and it never sets a status.

The read step calls Anthropic's SDK directly, inside a LangGraph node. The reason is in [decisions/0006](decisions/0006-stack.md).

## Trust rules

These are deliberately simple:

1. **The model reads and links.** It writes each fact together with its citation: the passage and where it sits. Its links between documents are trusted. The eval measures how often they're wrong, and link confirmation gets added only if that number is bad.
2. **One automatic check.** Code confirms each value appears in its cited passage. Photos and scans have no passage, so their values must match their ledger line instead: the amount, the date or the vendor. If the check fails, the charge goes to Needs a human. The box drawn on an image only shows where to look.
3. **Code does all rules and all math.** The model never calculates anything, for example a new end date from "extended 12 months", or a cost split.
4. **The accountant signs off** on the evidence report before attaching it to the university's closeout step. That's the human check.

Code also decides an approver's role by matching the sender's address against the people named in the award letter. For a forwarded email, the agent extracts the original sender, with a citation. Unknown senders go to Needs a human. The NSF rules the checks apply are in [domain.md](domain.md).

## The clock

- Each workspace has a clock that sets the app's "now."
- Every item has two dates:
  - **Its own date,** such as the date on a document or a ledger line's transaction date. The checks use this one.
  - **Its arrival date,** such as when an email arrived or when a ledger line was synced or uploaded. The clock uses this one.
- An item counts once its arrival date is at or before "now." For the demo ledger file, a line's arrival date is its posting date.
- The clock only moves forward, either to the next arrival or to a date you choose. Resetting a workspace starts it over.
- Anything the accountant does, and anything that arrives live, is stamped with the clock's date.
- Workspaces that users create run on the real date.
- How the demo uses the clock is decided later. For now we build it as a real app, with no response cache.

## Stack

| Part | Choice |
|---|---|
| Frontend | Next.js on Vercel |
| Document viewer | PDF.js (for example react-pdf) with a highlight layer |
| Backend | Python FastAPI on Railway, always on |
| Database, sign-in, file storage | Supabase (Postgres, Google sign-in, storage) |
| Model | Claude `claude-opus-5-5` |
| Agent | LangGraph, with the read step calling Anthropic's SDK directly |
| Records | Pydantic models |
| Connectors | Gmail API, Google Drive API |

## Deployment

```
browser ─► Next.js (Vercel) ─► FastAPI (Railway) ─► Supabase: Postgres · auth · storage
                │                    ├─► Anthropic API (Claude)
                └─ Supabase auth     └─► Gmail API · Drive API (demo account)
```

## Repo layout

The layout and its owners are in [CLAUDE.md](../CLAUDE.md#repo-map). Workstreams are in [plan.md](plan.md).

## Not decided yet

| Item | Who settles it |
|---|---|
| How sign-in passes from the frontend to the backend | contract |
| Background jobs for agent runs: what triggers a run, and retries | builder (W4 with W1) |
| How often Gmail and Drive are checked, push or polling | builder (W3) |
| Email body vs. attachments, duplicate files | builder (W3) |
| The email address format for each grant | builder (W3) |
| How a reversal or cost transfer ties back to its original line | contract |
| Graph nodes, tools, prompts, how the agent finds the charge to link, facts spread across documents, errors | builder (W1) |
| How quoted text is located in a PDF for highlighting | builder (W6) |
| How scheduled release by the clock is implemented, and live arrivals while the clock is in the past | product, then W4 |
| File layout in storage | builder (W4) |
