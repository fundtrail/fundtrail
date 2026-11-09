# Product

## The problem

A university spends a research grant over several years under rules that change along the way: extensions, budget moves, approvals. When the grant ends, the university has a few months to review every charge, move off any that broke the rules, and certify that the grant is ready to close. Years later, auditors can pick any charge and ask for the proof behind it. That proof is scattered across email, shared drives, invoices and the accounting system. Today someone pieces it together by hand, after the people who remember the details have moved on.

This fits the hackathon theme, "Automate the Old Way": an old financial workflow built on spreadsheets, email chains and receipts, rebuilt with AI.

## The product

**FundTrail keeps a running evidence file for every grant.** As evidence arrives, FundTrail connects it to the charges and keeps each charge's status current. Problems show up while they can still be fixed. When the grant ends, the review the university has to do is already done, and the evidence report is ready to attach to the university's own closeout step (see [Closeout](#closeout)).

**FundTrail fits into the university's process. It doesn't replace it.** It sits beside the university's systems, reads the charges and the evidence, and hands the person doing closeout what they need at each step. It files nothing with the university or with the National Science Foundation (NSF).

**How it differs from Ramp.** Ramp's Grant Policy Agent checks a purchase when it's made. FundTrail works with evidence Ramp never sees, such as email, shared drives and amendments signed months later, and it rechecks the whole history every time something changes. We don't pitch receipt matching.

## Users and workspaces

These limits are for now. The design stays open to grow (see below).

- The only user is the person who manages a grant's money and prepares its closeout. These docs call them **the accountant**. At Berkeley, that's the department's research administrator, who prepares the Award Closeout Certification. At other universities, it can be a grant accountant in the sponsored programs office.
- Each workspace has one person. Professors and lab staff only send evidence in.
- Users sign in with Google. A workspace holds many grants.
- A new account starts with a demo workspace already loaded with grants. Users can create more workspaces.

## Grants

- To add a grant, the accountant drops in the award letter. The agent pulls out the terms as cited records: dates, budget lines, people and their roles, approval rules, and anything else the letter says that those don't hold, such as a principal investigator going on leave. The accountant confirms the terms before any check uses them.
- Amendments, such as an extension notice, update the terms the same way.
- For now, only NSF grants, and only direct costs.

## Buckets

Every charge sits in exactly one bucket.

| Bucket | Meaning |
|---|---|
| **Evidence complete** | Every check passes on verified records, and every question about the charge is answered supports |
| **Possible conflict** | Verified evidence contradicts a rule, or an answer is contradicts |
| **Missing evidence** | Something required isn't on file |
| **Needs a human** | Code can't decide safely, the agent is unsure, or a fix the agent suggested waits for the accountant |

When several checks fail, the charge shows the most serious bucket and lists every reason. From most to least serious: Possible conflict, Needs a human, Missing evidence.

### How a charge gets its bucket

- **Code checks the clear-cut rules:** dates against the period in force, whether the receipts linked to a charge add up to it, the approver's role and channel, and budget room. When terms change, code reruns instantly, with no agent call.
- **The agent decides what takes judgment.** It decides which budget line each charge belongs to, and code asks it about each charge: is this cost necessary and reasonable, and is it for this project? Does this approval cover this charge? Does this unusual term change anything? The agent answers supports, contradicts or unsure, with its reasoning and quotes. Contradicts is Possible conflict, and unsure is Needs a human.
- **The accountant has the last word.** They answer what the agent was unsure about, can overrule any answer, and approve or reject any fix the agent suggests. Once they've answered a question, new evidence sends it back to them, not to the agent.
- **While the agent is answering again,** the charge shows its last answer marked "rechecking", or Needs a human if there's no answer yet.

### The problem list

Possible conflict and Needs a human are always on the accountant's problem list. A charge in Missing evidence stays off the list until 90 days before the grant's end date, when Berkeley sends its first Notice of Expiration, because receipts often arrive weeks after a charge posts. From then on, a receipt with money never charged is listed on the grant too.

## What the user sees

- **Evidence cards.** Each piece of evidence gets a card listing the facts pulled from it. Every fact shows its quoted passage and page number.
- **Viewer.** Clicking a fact opens the full original in a viewer, scrolled and zoomed to the passage, with the passage highlighted.
  - **PDFs with real text, email, .docx:** the highlight is exact.
  - **Photos and scans:** the viewer zooms to a box the agent estimated, and the box is approximate. There's no OCR (optical character recognition).
- **Status history.** Every status change records what triggered it and links to it. Example: "Apr 10, 2026 · new end date confirmed · Possible conflict → Evidence complete."
- **Receipts covering a charge.** Each charge lists the receipts that pay for it, with how much of each it uses, for example "invoice 2050, $5,000 of $10,000". Clicking one opens the receipt with the part for that charge highlighted. Approvals and explaining emails show the same way.
- **The agent's answers.** Each answer shows the question, the answer, the agent's reasoning and its quotes, labeled as the agent's.
- **Suggestions waiting.** A fix the agent suggests to an earlier link waits on the charge, with its reason, until the accountant approves or rejects it.
- **People as sources.** Example: "Link corrected by the accountant, May 22, 2026."
- **Status text comes from code.** Every status explanation is built by code from the check and its records. The agent's reasoning appears next to it, labeled as the agent's.

## Closeout

What really happens at the end of a grant, and the rules behind it, are in [domain.md](domain.md#closeout).

### Where FundTrail fits: Berkeley as the first example

Every university has its own closeout step, with its own forms and deadlines, but the rules underneath are the same federal and NSF rules. FundTrail's checks follow those shared rules. Only the evidence report's format and labels follow the university. Berkeley is the first template and the demo example.

| Berkeley's step | Today | With FundTrail |
|---|---|---|
| **90 days before the end date.** Berkeley sends a Notice of Expiration and asks for a review of every charge. | Reviewed by hand | The review is already done. The accountant works a short list of problem charges. |
| **Adjustment period**, from the end date until the books close two months later. Problem charges get moved off the grant. Each move needs a written explanation. | Written by hand | FundTrail drafts each explanation from the evidence it holds (optional feature). The accountant edits it and makes the move in Berkeley's own system. |
| **Award Closeout Certification**, due at the close of the 2nd month. The accountant files a form with a ledger report and supporting documents, and their supervisor approves it. | The ledger report shows totals, not proof | The accountant also attaches FundTrail's evidence report. |
| **Final financial report**, filed by central accounting by day 90. For NSF, that's one amount entered in ACM$ (Award Cash Management Service). | Unchanged | Not involved. The amount is cleaner because problem charges are already gone. |
| **Audit, years later.** Auditors pick charges and ask for the proof. | Dug up from old email and files | Pulled from FundTrail |

### What the user gets

- **Closeout view in the app:** every expense with its bucket, its evidence and its history.
- **Evidence report: a PDF per grant.** It shows why each charge was allowed. It's attached to the university's closeout step, next to the university's own ledger report, which shows only what was spent. NSF doesn't require it and never receives it. Example layout, to decide later:
  1. Summary: the award, its dates, the total of all charges (matching the ledger report), and how many charges are in each bucket.
  2. A table with one row per charge: date, description, amount, bucket and a one-line reason.
  3. A section per charge: the checks, the evidence quoted from its source, and its status history.
  4. Sign-off: who prepared it, who reviewed it, and when. At Berkeley this mirrors the preparer and the supervisor who approves the certification.
- **Drafted explanations (optional).** For each charge that has to move off the grant, a draft that answers the university's questions, such as Berkeley's: why the move is needed, why the wrong fund was charged, and how the expense relates to the project.
- **Audit export (optional).** The same records, filtered to the charges an auditor picked.

**One-line pitch:** at Berkeley, every grant ends with a Closeout Certification due two months after the end date. FundTrail has the proof for every charge ready to attach, so the review is done before the deadline and any audited charge can be answered right away.

## Demo data (examples)

Everything in this section is an example. The actual grants, people, amounts, dates and documents get decided later, when we build the seed data. All of it is synthetic.

The seeded workspace has a few NSF grants. At least two of them share a cost, so a split shows up on both.

| Example situation | What FundTrail does |
|---|---|
| A professor's conference fee is charged to participant support with no approval. Later the professor forwards their own "approved" email | **Possible conflict**, and it stays there: wrong approver, wrong channel |
| A charge is for work done after the grant's end date. Later an extension notice, signed before the old end date, turns up in Drive | **Possible conflict**, then **Evidence complete** once the accountant confirms the new end date, citing it |
| One purchase is shared with a second grant and split across both ledgers | The agent links the invoice to both charges, each for its part, from the invoice's itemized lines, or from an email giving the basis, for example "56 of 96 samples", which it also links to both charges. **Evidence complete** on both. If nothing gives the basis, **Needs a human** until the accountant enters it |
| A receipt arrives before its ledger line posts | It waits unlinked, then links when the line arrives |
| A new grant is built from scratch from a seed pack: award letter, ledger file, emails, invoices, a receipt photo | Create the grant, confirm its terms, upload the ledger, add the evidence, watch the statuses fill in |

## Scope

**Core: has to ship**

- Sign-in, workspaces and the seeded workspace
- The clock
- The demo situations
- Adding a grant from its award letter, including the from-scratch seed pack
- The agent and the checks
- Provenance, with the viewer and highlights
- Ledger upload, the Gmail connector and uploads
- Text, email, PDF and photo formats
- The evidence report with sign-off, in Berkeley's terms
- The eval, with the minimum blind test
- Hosting

**Optional: if there's time**

- Chat
- Creating extra workspaces
- .docx files
- The Drive connector
- A bigger blind test
- Report styling and a zip of the originals
- Drafted explanations for charges moved off the grant
- Audit export for the charges an auditor picks
- Workspace members

**Designed to grow.** These are out for now, but nothing in the design should block them later:

- more users and roles: workspace members, and a read-only view for professors
- more funders, with rules organized per funder, starting with NSF
- more universities, each with its own evidence report template, starting with Berkeley
- evidence files that belong to the workspace instead of the grant they arrived on
- indirect costs
- in-kind cost sharing (third-party contributions that never appear on the ledger)
- a real-time card feed, like Ramp's, that shows charges before they post
- users connecting their own Google accounts
- chat, drafted follow-up emails, and OCR if it's ever needed

## Not decided yet

| Item | Who settles it |
|---|---|
| Demo data specifics: grants, people, amounts, dates, documents, including a situation only the agent's judgment catches | product |
| How to demo: how the clock and the seeded workspace get used in the pitch | product |
| The evidence report's name, its layout, and the sign-off flow (preparer and reviewer) | product |
| Whether checks and reasons use the university's cost criteria as labels, for example Berkeley's | product |
| How drafted explanations are written: by code from the records, or by the agent with citations | product, if the feature is built |
| The clock controls the user sees | product |
| What a workspace reset clears, and how the seed is copied on sign-up | product |
| The screen where the accountant confirms terms and reviews the agent's suggestions | product |
| A charge's bucket between an amendment's arrival and the accountant's confirmation of it, and while a grant's terms aren't confirmed yet | product |
| How reversals and cost transfers show in buckets and at closeout | product |
| Whether a later change reopens a sign-off | product |
| Whether the agent's corrections to its own facts, such as a misread receipt total, wait for the accountant like its link fixes do. Only link fixes were discussed. The contracts make every correction the agent writes wait, except a new answer to its own question. | product |
| How the evidence report shows the agent's answers next to code's reasons | product |
| Screen layouts, and how emails are displayed | builder |
