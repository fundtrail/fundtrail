# Product

## The problem

A university spends a research grant over several years under rules that change along the way: extensions, budget moves, approvals. When the grant ends, the university has to prove that every charge followed the rules. The evidence is scattered across email, shared drives, invoices and the accounting system. Today someone pieces it together by hand at closeout, under a 120-day deadline, after the people who remember the details have moved on.

This fits the hackathon theme, "Automate the Old Way": an old financial workflow built on spreadsheets, email chains and receipts, rebuilt with AI.

## The product

**FundTrail keeps a running evidence file for every grant.** As evidence arrives, FundTrail connects it to the charges and keeps each charge's status current. Problems show up while they can still be fixed, and the closeout packet is ready when the grant ends.

**How it differs from Ramp.** Ramp's Grant Policy Agent checks a purchase when it's made. FundTrail works with evidence Ramp never sees, such as email, shared drives and amendments signed months later, and it rechecks the whole history every time something changes. We don't pitch receipt matching.

## Users and workspaces

These limits are for now. The design stays open to grow (see below).

- The only user is the grant accountant in the university's sponsored programs office, and each workspace has one person. Professors and lab staff only send evidence in.
- Users sign in with Google. A workspace holds many grants.
- A new account starts with a demo workspace already loaded with grants. Users can create more workspaces.

## Grants

- To add a grant, the accountant drops in the award letter. The agent pulls out the terms as cited records: dates, budget lines, people and their roles, and approval rules. The accountant confirms the terms before any check uses them.
- Amendments, such as an extension notice, update the terms the same way.
- For now, only NSF (National Science Foundation) grants, and only direct costs.

## Buckets

Every charge sits in exactly one bucket.

| Bucket | Meaning |
|---|---|
| **Evidence complete** | Every check passes on verified records |
| **Possible conflict** | Verified evidence contradicts a rule |
| **Missing evidence** | Something required isn't on file |
| **Needs a human** | Code can't decide safely |

When several checks fail, the charge shows the most serious bucket and lists every reason. From most to least serious: Possible conflict, Needs a human, Missing evidence.

## What the user sees

- **Evidence cards.** Each piece of evidence gets a card listing the facts pulled from it. Every fact shows its quoted passage and page number.
- **Viewer.** Clicking a fact opens the full original in a viewer, scrolled and zoomed to the passage, with the passage highlighted.
  - **PDFs with real text, email, .docx:** the highlight is exact.
  - **Photos and scans:** the viewer zooms to a box Claude estimated, and the box is approximate. There's no OCR (optical character recognition).
- **Status history.** Every status change records what triggered it and links to it. Example: "Apr 2026 · extension notice arrived · Possible conflict → Evidence complete."
- **People as sources.** Example: "Split entered by the accountant, May 22, 2026."
- **Status text comes from code.** Every status explanation is built by code from the check and its records. The model writes no status text.

## Closeout

- **Closeout view in the app:** every expense with its bucket, its evidence and its history.
- **PDF packet per grant,** showing who signed off and when. Example layout, to decide later: a summary table of every expense, then a section for each expense.
- **What the packet is for on real grants.** NSF doesn't receive an evidence packet. The packet is the accountant's sign-off before the final financial report goes in, and it's the audit file the university keeps afterwards (see [domain.md](domain.md)).

## Demo data (examples)

Everything in this section is an example. The actual grants, people, amounts, dates and documents get decided later, when we build the seed data. All of it is synthetic.

The seeded workspace has a few NSF grants. At least two of them share a cost, so a split shows up on both.

| Example situation | What FundTrail does |
|---|---|
| A professor's conference fee is charged to participant support with no approval. Later the professor forwards their own "approved" email | **Possible conflict**, and it stays there: wrong approver, wrong channel |
| A charge is for work done after the grant's end date. Later an extension notice, signed before the old end date, turns up in Drive | **Possible conflict**, then **Evidence complete**, citing the new end date |
| One purchase is shared with a second grant and split across both ledgers | **Missing evidence** on both until the accountant enters the basis, for example "56 of 96 samples". Then **Evidence complete** on both |
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
- The packet with sign-off
- The eval, with the minimum blind test
- Hosting

**Optional: if there's time**

- Chat
- Creating extra workspaces
- .docx files
- The Drive connector
- A bigger blind test
- Packet styling and a zip of the originals
- Workspace members

**Designed to grow.** These are out for now, but nothing in the design should block them later:

- more users and roles: workspace members, and a read-only view for professors
- more funders, with rules organized per funder, starting with NSF
- indirect costs
- in-kind cost sharing (third-party contributions that never appear on the ledger)
- a real-time card feed, like Ramp's, that shows charges before they post
- users connecting their own Google accounts
- chat, drafted follow-up emails, and OCR if it's ever needed

## Not decided yet

| Item | Who settles it |
|---|---|
| Demo data specifics: grants, people, amounts, dates, documents | product |
| How to demo: how the clock and the seeded workspace get used in the pitch | product |
| Packet layout and the sign-off flow | product |
| The clock controls the user sees | product |
| What a workspace reset clears, and how the seed is copied on sign-up | product |
| Which fields count as grant terms, and the screen where the accountant confirms them | product |
| Screen layouts, and how emails are displayed | builder |
