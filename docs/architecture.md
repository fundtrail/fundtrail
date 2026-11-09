# Architecture

## Overview

```
charges: ledger lines per grant ─► code ──────────────────────────────┐
                                                                      ▼
evidence: Gmail · Drive · upload ─► AGENT ─► RECORDS ◄──── questions ─ CHECKS (code) ─► statuses + history
                                    reads, links, answers ▲                   │
                                                          │                   ▼
                     accountant ──────────────────────────┘   confirms terms, approves fixes, answers, signs off
```

- **The agent** is the app's intelligence. It reads evidence, writes cited facts, links them to charges, and answers the questions code asks. It never sets a status.
- **Records** are the single source of truth. A record is never edited. A correction is a new record that replaces the old one. The accountant writes records too.
- **Checks** are code. They check the clear-cut rules and ask questions about what they can't settle. Every time a record changes, code reruns every check and recomputes every status, with no agent call. "What changed" is the difference between before and after.
- The decision behind this split is [decisions/0009](decisions/0009-agent-judges-code-checks.md). The contracts are in [contracts.md](contracts.md).

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

### Files go to the agent as they are

PDFs, scanned PDFs and images are sent unchanged. The only exception is .docx, which the model doesn't accept, so its text is extracted first.

## The agent

"The agent" is our code that sends each step to the model and saves what comes back. Anything the model decides or does is the agent's.

```
the agent (our code, in backend/app/agent/)
  ├─ gives the model (claude-opus-5-5) the task: what arrived, and what to do
  ├─ loop: the model asks to look at something or to write something,
  │        our code carries it out and shows the model the result
  ├─ every write is checked as it happens, and problems go back to the model
  └─ when the model is done and every required question is answered,
     the backend saves everything from the run
```

- **When it runs.** A background job is queued whenever a charge or an evidence file arrives, whenever one of the accountant's records leaves a question open for the agent, and once per grant as closeout nears. Runs for one grant go one at a time. In the demo, "arrives" means the clock reaches the item's arrival time.
- **What it does.** It works in a loop of actions, like a person at a desk. It can look at anything on its grant, with no filtering. For now each grant is isolated, so it doesn't see other grants. It sees every charge with its links, every source and the facts read from it, the grant's terms, and a charge's history, including fixes the accountant rejected. It can open any file again to quote the exact part it needs. It writes facts, links, suggested fixes, answers to code's questions, and flags for anything no question covers. Reading, matching and answering aren't fixed steps; it does them in whatever order it needs.
- **Budget lines.** The agent decides which budget line each charge belongs to, because there's a lot of nuance in it. It writes the choice as a `budget_assignment` record (see [contracts.md](contracts.md#2-links)).
- **Matching.** The agent matches in both directions: a new receipt to its charges, and a new charge to the receipts on file. It looks through everything, not a shortlist, so it can also spot an earlier link that looks wrong.
- **Correcting earlier mistakes.** The agent is told to look for them: every time it matches, when a sum goes over, and once in a review of all the grant's links as closeout nears. Every fix is a suggestion that waits for the accountant. When a new link conflicts with an old one, the agent still writes it and suggests a fix for the old one, and the over sum keeps the charges with the accountant until they decide.
- **Reading files.** Files go to the model as they are. For text and for PDFs with real text, citations are on, and the API returns each cited passage with its location: page numbers for PDFs, character ranges for plain text, block indexes for custom content documents. For photos and scans the API has no citations, so the agent estimates a box around each quote. The agent never types a quote itself.
- **No database access.** The agent only proposes. The backend checks every write as it happens and returns any problems to the agent. Everything a run wrote is saved together at the end, so a run that fails saves nothing.
- **Still to design: its exact actions and prompts (W1).** Only the idea above is settled. Whoever builds the agent decides the actions, the prompts and the guidance, and whether to tune them against the eval. The eval can help, but it isn't required. The prompts have to balance firm rules against flexibility, because models follow rules too literally. Starting points from the design discussion, as guidance rather than rules:
  - Write the links you believe are right. Don't skip or shrink a link to make a sum fit, because code checks the sums.
  - When matching a new item, check whether it shows that an earlier link was wrong. If it does, suggest a fix and say why.
  - Don't guess between charges that look alike. Flag it instead.
  - Write part of a receipt as an amount when a document states that part, or when the numbers leave only one answer.

  Code enforces only the hard limits below.

The model is called through Anthropic's SDK inside LangGraph. The reason is in [decisions/0006](decisions/0006-stack.md).

## Trust rules

These are deliberately simple:

1. **The agent reads, links and answers.** It writes each fact together with its citation, links facts to charges, and answers the questions code asks. Its first links are trusted, and the eval measures how often they're wrong. Any fix it suggests to an existing link waits for the accountant, including a fix to one of the accountant's own links. It never changes the accountant's records on its own, and never their answers.
2. **Every quote is checked.** Code confirms each value appears in its cited passage, both when the agent writes it and in the checks. Photos and scans have no passage, so their values must match their ledger line instead: the amount, the date or the vendor. How that works when one receipt pays part of a charge, or several charges, is still open (see [contracts.md](contracts.md#not-decided-yet)). If the check fails, the charge goes to Needs a human. The box drawn on an image only shows where to look.
3. **The agent may do simple math. Code re-checks every number it can:** the link sums, and dates against the period in force. Code does every clear-cut rule.
4. **The accountant has the last word.** They answer what the agent was unsure about, can overrule any answer, and sign off on the evidence report before attaching it to the university's closeout step.

Hard limits that code enforces: the sums, the quote check, the agent never overruling the accountant, and the agent's fixes waiting for the accountant's approval. Everything else is guidance in the agent's prompts.

Code also decides an approver's role by matching the sender's address against the people named in the award letter. For a forwarded email, the agent extracts the original sender, with a citation. Unknown senders go to Needs a human. The National Science Foundation (NSF) rules the checks apply are in [domain.md](domain.md).

## The clock

- Each workspace has a clock that sets the app's "now."
- Every item has two dates:
  - **Its own date,** such as the date on a document or a ledger line's transaction date. The checks use this one.
  - **Its arrival date,** such as when an email arrived or when a ledger line was synced or uploaded. The clock uses this one.
- An item counts once its arrival date is at or before "now." For the demo ledger file, a line's arrival date is its posting date.
- The clock only moves forward, either to the next arrival or to a date you choose. Resetting a workspace starts it over.
- Anything the accountant or the agent writes, and anything that arrives live, is stamped with the clock's date.
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
| Agent | LangGraph, calling Anthropic's SDK directly |
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
| Retries for failed agent runs, and the job runner | builder (W4 with W1) |
| How often Gmail and Drive are checked, push or polling | builder (W3) |
| Email body vs. attachments, duplicate files | builder (W3) |
| The email address format for each grant | builder (W3) |
| The agent's exact actions, graph nodes, prompts and guidance, and how it handles errors. Needs design work, as its own task. Tuning against the eval is optional. | builder (W1) |
| Whether citations work on a file the agent opens again in the middle of a run. The citation test in `spikes/` can check it. | builder (W1) |
| How quoted text is located in a PDF for highlighting | builder (W6) |
| How scheduled release by the clock is implemented, and live arrivals while the clock is in the past | product, then W4 |
| When the clock jumps past several arrivals at once: the order agent runs go in, and whether the clock waits for each run to finish before releasing the next item | product, then W4 with W1 |
| Grants that share evidence and links, with files that belong to the workspace instead of the grant they arrived on. For now each grant is isolated. | later |
| Efficient sorting for matching, once accuracy is solid | builder (W1), later |
| A regular sweep that re-checks old links, beyond the one review as closeout nears | later |
