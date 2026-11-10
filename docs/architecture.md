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

- **The agent** is the app's intelligence. It reads evidence, writes cited facts, links them to charges, answers the questions code asks, and suggests changes for the accountant to decide. It never sets a status.
- **Records** are the single source of truth. A record is never edited. A correction is a new record that replaces the old one. The accountant writes records too.
- **Checks** are code. They check six clear-cut rules, listed in [product.md](product.md#what-code-checks), and ask questions about what they can't settle. They read only terms the accountant has confirmed. Every time a record changes, code reruns every check and recomputes every status, with no agent call. "What changed" is the difference between before and after.
- The decisions behind this split are [0009](decisions/0009-agent-judges-code-checks.md), [0010](decisions/0010-agent-suggests-accountant-decides.md), [0011](decisions/0011-evidence-checklist.md), [0012](decisions/0012-checked-quotes-and-highlights.md), [0015](decisions/0015-six-code-checks-and-the-agents-rulebook.md), [0016](decisions/0016-default-checklists-by-account-group.md), [0017](decisions/0017-grant-terms-from-award-notices.md) and [0018](decisions/0018-agent-works-from-saved-facts.md). The contracts are in [contracts.md](contracts.md).

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
- Each line carries the ledger's own account, the expense category the university's accounting system gave it. FundTrail uses it as an outside opinion on what kind of charge it is. Each account belongs to a group, and the group picks the charge's default evidence checklist and gives the National Science Foundation (NSF) budget category that's compared with the agent's budget line.

### Evidence: why the spending was allowed

- **Gmail:** each grant gets its own email address on our demo account. The backend checks for new mail on a timer, every one to two minutes.
- **Google Drive:** the connector reads folders that users share with our demo account, on the same timer. Users never connect their own Google account.
- **Upload:** files can also be added in the app.
- Only email from known senders is processed: our accounts, the addresses of the workspace's members who can act ([0029](decisions/0029-workspace-members-and-one-access-check.md)), the people named in each award letter, and anyone the accountant adds. Mail from anyone else is held for the accountant.
- Evidence that arrives before its ledger line waits, unlinked, until the line shows up.

### Files go to the agent as they are

PDFs with real text are sent unchanged. There are two exceptions. A .docx file's text is extracted first, because the model doesn't accept .docx. A photo, or a scanned page with no text, is turned into an image at a size we control before it's sent, so a box the model draws maps back onto the original (see [Quotes and highlights](#quotes-and-highlights)). There's no OCR (optical character recognition).

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

- **When it runs.** A background job is queued whenever a charge or an evidence file arrives, whenever one of the accountant's records leaves a question open for the agent, whenever the accountant writes in a thread, and once per grant as closeout nears. Runs for one grant go one at a time. A question in a thread goes ahead of queued runs and waits only for the run in progress, and the thread shows that the agent is busy. Procrastinate runs these jobs: a lock per grant gives one at a time, and a priority puts the question first. On a sample grant, "arrives" means the grant's clock reaches the item's arrival time.
- **What it does.** It works in a loop of actions, like a person at a desk. It can look at anything on its grant, and code hides nothing from it. For now each grant is isolated, so it doesn't see other grants. It sees every charge with its links, every source and the facts read from it, the grant's terms, and a charge's history, including fixes the accountant rejected. It can open any file again to quote the exact part it needs. It writes facts, links, checklist items, answers to code's questions, comments, suggestions, and flags for anything no question covers, on a charge or on a record. Reading, matching and answering aren't fixed steps; it does them in whatever order it needs.
- **Structure over memory.** The agent has no hidden memory between runs, so code hands it what needs attention instead of expecting it to remember. When a file arrives, it gets every checklist item still missing on the grant and is asked which ones the file fills. It gets the checks that are failing on the charges in the run, so it can dispute one it has evidence against. When a bill arrives, code finds the bills already on file that look like the same one, and the agent compares the saved facts first. It opens an earlier file only when the facts don't settle it, which should be rare. When it's asked a question in a thread, it gets that thread and the charge's records. Every run also gets the end date in force, which the rule on purchases close to the end date needs.
- **Lists of saved facts.** Looking at anything on the grant can't mean reading every file again on every run. A three-year grant can have 2,000 ledger lines and 1,500 documents. So the agent gets what just arrived in full, and the rest of the grant as lists: one line per charge and one line per document, built from the facts already read and saved. It can search the lists and open any file in full, and it chooses what to look at. The saved facts are the records it wrote when each file first arrived. It reads the whole file once, every value carries its quote, and code checks each quote against the file. When the saved facts don't settle a question, it opens the file. A bill carries an optional document number, such as an invoice or order number, because the ledger line often carries it too and it's the strongest match. The agent puts anything else that identifies a document in its description: names, order numbers, and the project or award number it mentions. The limit is that the saved facts are only as good as the first read, so a detail nobody recorded is found only when the file is opened. On a small grant nothing changes, because the lists are short.
- **The rulebook.** The agent's rules live in one rulebook per funder, starting with NSF. It's a plain file in the repo. Each rule is one or two sentences with its source, and a rule goes in only after it's checked against that source. The agent gets the whole rulebook on every run, and its answer names the rule it used, so the accountant can see why. The accountant doesn't edit it, and there's no settings screen: changing a rule is a change to the file, like the default checklists. It holds the rules that go to the agent instead of code: the kinds of cost that aren't allowed or are allowed only under a condition, purchases close to the end date, participant support paid to project staff, a late extension notice, and fringe benefits on stipends (see [product.md](product.md#what-goes-to-the-agent)).
- **Budget lines.** The agent decides which budget line each charge belongs to, because there's a lot of nuance in it. It writes the choice as a `budget_assignment` record (see [contracts.md](contracts.md#2-links)).
- **Matching.** The agent matches in both directions: a new bill to its charges, and a new charge to the bills on file. It works from the lists of everything on the grant, not a shortlist that code picked, so it can also spot an earlier link that looks wrong.
- **Correcting earlier mistakes.** The agent is told to look for them: every time it matches, when a sum goes over, and once in a review of all the grant's links as closeout nears. That review also looks again at every checklist item still missing. Every fix is a suggestion that waits for the accountant. When a new link conflicts with an old one, the agent still writes it and suggests a fix for the old one, and the over sum keeps the charges with the accountant until they decide.
- **Reading files.** For text and for PDFs with real text, citations are on, and the API (application programming interface) returns each cited passage with its location: page numbers for PDFs, character ranges for plain text, block indexes for custom content documents. For photos and scans the API has no citations, so the agent returns a box around each value, in pixels on the image we sent. The agent never types a quote itself. How quotes are checked and highlighted is in [Quotes and highlights](#quotes-and-highlights).
- **No database access.** The agent only proposes. The backend checks every write as it happens and returns any problems to the agent. Everything a run wrote is saved together at the end, so a run that fails saves nothing.
- **Still to design: its exact actions and prompts (W1).** Only the idea above is settled. Whoever builds the agent decides the actions, the wording of the prompts and the guidance, and whether to tune them against the eval, and discusses them with Alex before building. The NSF rulebook is written before the agent is built. The eval can help, but it isn't required. The prompts have to balance firm rules against flexibility, because models follow rules too literally. Starting points, as guidance rather than rules:
  - Write the links you believe are right. Don't skip or shrink a link to make a sum fit, because code checks the sums.
  - When matching a new item, check whether it shows that an earlier link was wrong. If it does, suggest a fix and say why.
  - Don't guess between charges that look alike. Flag it instead.
  - Write part of a bill as an amount when a document states that part, or when the numbers leave only one answer.
  - Link an approval that was offered for a charge even when it doesn't fit. The Covers answer then says so, and the accountant learns the wrong approval was sent.

  Code enforces only the hard limits below.

The model is called through Anthropic's SDK inside LangGraph. LangGraph's saving of a run partway through is off for now, so a crashed run starts over. The reasons are in [decisions/0006](decisions/0006-stack.md) and [0013](decisions/0013-stack-additions-and-repo-structure.md).

## Trust rules

These are deliberately simple:

1. **The agent reads, links, answers and suggests.** It writes each fact together with its citation, links facts to charges, and answers the questions code asks. Its first links are trusted, and the eval measures how often they're wrong. Anything it does that adds information or raises a concern takes effect right away. Anything that would clear or weaken a problem, or change something already decided, is a suggestion that waits for the accountant (see [The agent suggests, the accountant decides](#the-agent-suggests-the-accountant-decides)). It never changes the accountant's records on its own.
2. **Every quote is checked against its file.** Code confirms each value appears in its cited passage, and that the passage is really in the file. For photos and scans, which have no passage, a second look reads only the boxed area and has to see the same value. A fact that fails is unconfirmed, until the accountant confirms the record it's in or types the right value. It can't make anything pass and it isn't ignored: whatever rests on it goes to Needs a human until the accountant confirms the value or types the right one (see [Quotes and highlights](#quotes-and-highlights)).
3. **The agent may do simple math. Code re-checks every number it can:** the link sums, and dates against the period in force. Code does every clear-cut rule.
4. **The accountant has the last word.** They answer what the agent was unsure about, can overrule any answer, accept or reject every suggestion, can accept any reason on a charge with a note, and sign off on the evidence report before attaching it to the university's closeout step.

Hard limits that code enforces: the sums, the quote check, the agent never overruling the accountant, and the agent's suggestions waiting for the accountant's approval. Everything else is guidance in the agent's prompts.

Code also decides an approver's role by matching the sender's address against the people named in the award letter. For a forwarded email, the agent extracts the original sender, with a citation. Unknown senders go to Needs a human. The NSF rules the checks apply are in [domain.md](domain.md).

### The agent suggests, the accountant decides

The rule: what goes with the flow takes effect, and what goes against it waits, unless it overrides nothing, like a comment.

| Takes effect right away | Waits for the accountant |
|---|---|
| A comment | Changing an answer the accountant gave |
| A link for evidence nobody has linked | Fixing an existing link. A bill and a charge have one link in force at a time, so a second link beside it doesn't count until it's accepted. |
| A flag, on a charge or a record | Withdrawing its own flag, or turning its own contradicts into supports |
| A new checklist item | Removing a checklist item |
| A first answer to a question code asks, a refreshed answer that says the same thing, or a change toward a concern | Disputing one of code's checks |
| A new answer after its own unsure, once new evidence arrives | The same change with no new evidence |

- **New evidence** means something that arrived after the agent's last answer, or a grant term confirmed after it. Something the agent links later from what was already on file doesn't count. Code checks it, so the agent can't claim it.
- **A dispute** names the check, the agent's reasoning and a quote. While it waits, the disputed reason counts as Needs a human, so the charge moves from Possible conflict to Needs a human unless another reason keeps it there. Accepting it works like accept with a note, with the agent's reasoning as the note. Rejecting it puts the charge back.
- **No repeats.** After the accountant rejects a suggestion or a dispute, or keeps their own answer, the agent can't raise the same one again without new evidence.
- **An instruction is still a suggestion.** When the accountant tells the agent in a thread to change something, the change comes back as a suggestion with one click, so every change is seen before it happens and leaves the same record.
- **Accepting a reason** covers the problem as it stood. If the facts under it change, the charge comes back, and the accountant can reopen it. An accepted charge shows as Accepted and keeps the bucket the checks gave it. It's never counted as Evidence complete. A snoozed charge keeps its bucket too and is only hidden from the list.
- **Reusing a note.** A note is one-off or reusable. A reusable note applies on its own only inside its limits: the same check failing for the same reason, the same ledger account and vendor, and an amount no larger than the largest the accountant has accepted under it. A charge with the same problem and ledger account that fails the vendor or amount limit is flagged as usual, with the note offered for one click. Code does the matching, not the agent, and every other check still runs.
- **Where it's kept.** Thread messages are kept in their own table, outside the evidence file. Suggestions and decisions are records, so they're never edited and the evidence report can show them. The agent's own working steps are kept per run, for debugging.

## Quotes and highlights

The accountant clicks a fact and the file opens at the right spot. We copy patterns that are already in production use ([0012](decisions/0012-checked-quotes-and-highlights.md)).

| File | Where the spot comes from | The check |
|---|---|---|
| Plain text, email, .docx (as text) | The API's citation gives the exact characters | The text at those characters is the quoted passage, and the value is inside it |
| PDF with real text | The API's citation gives the page and the quoted passage. Code finds the passage in that page's text. | The passage is found on the page, by exact match first and then a close match, and the value is inside it |
| Photo, or a scanned page | We send an image at a size we control, and the agent returns a pixel box around the value, following Anthropic's coordinates guide. Code scales the box back to the original. | A second look reads only the boxed area and has to see the same value |
| Anything that can't be placed | The viewer opens the page and shows the quote beside it, with no guessed highlight | The fact is unconfirmed (trust rule 2) |

- **Confirmed three ways.** A value counts as confirmed when its citation was found in its file, when the accountant confirmed the record it's in, or when the accountant typed it. Code works this out each time, and nothing stores it. Confirming a grant term therefore confirms its values too. Only a value that a check or an answer rests on sends a charge to Needs a human.
- **Corrections carry their links.** When a record is corrected, links to the old one follow it to the new one, and the checks rerun.
- **Matched once, on the server.** The match runs when the record is saved, and where the highlight goes is stored. The viewer only draws it. The server uses pypdfium2 to read a page's text, find the passage and turn a scanned page into an image, and Pillow to resize photos.
- **How Claude reads a PDF.** Each page goes in as an image with its extracted text alongside. A PDF citation returns the quoted passage and the page range, nothing finer, and Anthropic's own cookbook finds the passage on the page the same way.
- **OCR is the fallback** if the eval shows boxes on photos aren't reliable enough.

## The clock

- **One clock per grant** ([0028](decisions/0028-one-clock-per-grant.md)). One place answers what time it is for a grant. A real grant's clock gives the real time. A sample grant's clock gives its simulated "now" ([0027](decisions/0027-sample-grants.md)). The clock belongs to the grant, not the workspace.
- **Apart from the machine's own uses below, nothing asks the system for the time,** and nothing branches on whether a grant is a sample. A check in continuous integration (CI) fails new code that reads the system time anywhere else.
- **What goes through the clock:** arrivals, the date on every record and message, a run's date, what "today" means to the checks, the dating of live email and Drive files on a sample grant, status history, report and sign-off dates, and every date a screen shows.
- **What stays on real time,** because it belongs to the machine: the order records were stored in, background timers, logs, and sign-in expiry.
- Every item has two dates:
  - **Its own date,** such as the date on a document or a ledger line's transaction date. The checks use this one.
  - **Its arrival date,** such as when an email arrived or when a ledger line was synced or uploaded. The clock uses this one.
- An item counts once its arrival date is at or before its grant's "now." A ledger line's arrival date is its posting date if that's still ahead of "now", and otherwise now ([0023](decisions/0023-the-clock.md)).
- A real grant's clock is the real time, and nobody moves it. A sample grant's clock only moves forward: to the next event, or to a chosen date. Everything between plays in order ([0023](decisions/0023-the-clock.md), provisional). Starting over resets that one sample grant (first version, [0027](decisions/0027-sample-grants.md)).
- Anything that arrives live on a sample grant arrives at the grant's "now". A live email or Drive file there is dated to the simulated time, and the stored original is unchanged. A date printed inside a document is used as written.
- Every sample opens at the start of its timeline. Read live, the agent works on each arrival as the clock reaches it. In the prerun, the agent's work was done ahead of time: a saved run-through made with the real agent, loaded at once only while every decision so far is the sample accountant's scripted one. After the user's own decision, the agent works live (first versions, [0027](decisions/0027-sample-grants.md)). Nothing precomputed is used on a real grant or in the read-live samples, and there's no response cache.

## Stack

| Part | Choice |
|---|---|
| Frontend | Next.js on Vercel |
| Document viewer | PDF.js (for example react-pdf) with a highlight layer |
| Backend | Python FastAPI on Railway, always on |
| Database, sign-in, file storage | Supabase (Postgres, Google sign-in, storage) |
| Model | Claude `claude-opus-5-5` |
| Agent | LangGraph, calling Anthropic's SDK directly. Its mid-run saving is off for now. |
| Background jobs | Procrastinate, on our Postgres database |
| Screen updates | A "something changed" ping through Supabase Realtime, then a refetch from our API |
| PDFs and images on the server | pypdfium2 and Pillow |
| Records | Pydantic models |
| Connectors | Gmail API and Google Drive API, checked on a timer |

The screen learns that something changed, such as the agent replying in a thread, from a small ping on a private Supabase Realtime channel. It then refetches from our API. Supabase doesn't promise that every ping arrives, so the screen also refetches when it connects or reconnects.

The choices added after the first stack decision, and what was set aside, are in [decisions/0013](decisions/0013-stack-additions-and-repo-structure.md).

## Deployment

```
browser ─► Next.js (Vercel) ─► FastAPI (Railway) ─► Supabase: Postgres · auth · storage · Realtime
                │                    ├─► Anthropic API (Claude)
                └─ Supabase auth     └─► Gmail API · Drive API (demo account)
                   and Realtime pings
```

## Repo layout

The layout is in [CLAUDE.md](../CLAUDE.md#repo-map). The areas of the repo are in [plan.md](plan.md#areas).

## Not decided yet

| Item | Who settles it |
|---|---|
| How many times a failed agent run is retried, what the accountant sees when one fails, and how many grants run at once | builder (W4 with W1), discussed with Alex before building |
| How the backend connects to Supabase for Procrastinate: the direct connection or the session pooler, or polling | builder (W4), discussed with Alex before building |
| Which events send a ping to the screen, whether a channel is per grant or per workspace, and how the "agent is busy" notice is driven | builder (W4 with W5), discussed with Alex before building |
| Whether pypdfium2 plus our clean-up step finds quotes as reliably as PyMuPDF would, tested early on real PDFs. Its calls also can't run at the same time across threads. | builder (W1), reported to Alex |
| How the agent signals that it's done, the shape of its graph, and what's kept from each run for debugging | builder (W1), discussed with Alex before building |
| The exact interval for checking Gmail and Drive, and whether a file added inside a shared Drive folder always shows up in Drive's change feed | builder (W3) |
| Email body vs. attachments, duplicate files | builder (W3) |
| The email address format for each grant | builder (W3) |
| The agent's exact actions, graph nodes, prompts and guidance, and how it handles errors. That includes how the lists of charges and documents are built and searched. Needs design work, as its own task. Tuning against the eval is optional. | builder (W1), discussed with Alex before building |
| Where the rulebook file lives in the repo, its format, and the exact rules in it. The rulebook's header lists the sources still unread (see [domain.md](domain.md#not-decided-yet)). | builder (W1), discussed with Alex before building |
| Whether citations work on a file the agent opens again in the middle of a run. A small test against the API can check it. | builder (W1) |
| How loose the PDF passage match can be. A draft: clean up both texts the same way (straight quotes, single spaces, words rejoined across line breaks), and let a close match place the highlight. The fact is confirmed only when the value itself appears exactly in the matched text. | builder (W1 with W6), discussed with Alex before building |
| Quotes that cross a page break | builder (W1 with W6), discussed with Alex before building |
| The cost of the second look on photos: one call per fact, or one per photo with all its crops | builder (W1), discussed with Alex before building |
| What eval result would switch photos and scans to OCR | product |
| A value the API returns with no citation. Suggested: it's unconfirmed. | builder (W1), discussed with Alex before building |
| Handwriting, and scans with many pages | builder (W1), discussed with Alex before building |
| Citations can't be combined with structured outputs, so the agent's answer format has to work around it | builder (W1), discussed with Alex before building |
| The exact list of agent writes that wait, as code enforces it | contract |
| What an agent run loads when it's asked a question in a thread, and how long the agent's working steps are kept | builder (W1 with W4), discussed with Alex before building |
| The search rule for likely duplicate bills: which fields, and how wide a window of dates. A long list of candidates means the rule is too loose. Also what catches a duplicate the search misses. The closeout review could look again. | builder (W2), discussed with Alex before building |
| How code tells that two confirmed terms disagree | builder (W2), discussed with Alex before building |
| How a sample grant's timeline releases its scheduled events. A live arrival on a sample grant arrives at the grant's "now" and is dated to the simulated time ([0028](decisions/0028-one-clock-per-grant.md)). | contract, then W4 |
| When a sample grant's clock jumps past several events at once: the order agent runs go in, and whether the clock waits for each run to finish before releasing the next item. [0023](decisions/0023-the-clock.md) proposes playing everything between in order. | product, then W4 with W1 |
| How the CI check recognizes code that reads the system time outside the grant's clock | builder (W4), through a CI config PR |
| Grants that share evidence and links, with files that belong to the workspace instead of the grant they arrived on. For now each grant is isolated. | later |
| Efficient sorting for matching, once accuracy is solid | builder (W1), later |
| A regular sweep that re-checks old links, beyond the one review as closeout nears | later |
