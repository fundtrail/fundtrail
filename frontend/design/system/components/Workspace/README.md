# Workspace

The workspace home: the page the accountant lands on after signing in. It lists every grant in the workspace with how ready it is for closeout and what's due next, so the grant that needs attention first is at the top.

**What it shows.** A title with the workspace's name, one summary line (grants, how many are closed, charges on problem lists, the agent's suggestions waiting for the accountant), and a main **Add a grant** button. Then one row per grant:

| Column | What it holds |
|---|---|
| Grant | The short name (the link that opens the grant), the award number in Geist Mono, and the principal investigator (PI) on its own line |
| Ends | The end date in force, with the start date under it |
| Ready for closeout | "48 of 51 charges" and the thin readiness bar (`ft-ready__bar` at 6px), in bucket order |
| Problem list | The count in an alert `ft-count`, "None" when empty, then quiet lines for the agent's suggestions waiting for the accountant and for missing evidence not on the list yet. Following PR 6, missing evidence joins the list 60 days after its charge posted, or 90 days before the end date, whichever comes first (Kelp Forest's three posted Mar 5, Mar 19 and Mar 30, 2026, so they join on May 4, May 18 and May 29). Before PR 6 it was 90 days before the end date |
| Next deadline | The date with "in N days", what it is (Notice of Expiration, for example), and the certification due date under it. Within 90 days the countdown turns bold |

Rows sort by next deadline, soonest first. A closed grant stays in the list under a quiet "Closed" divider, muted, with its sign-off date, because auditors can still ask about it. The sidebar has a **Workspace** item above the grants, active on this page.

**Empty workspace** (`#state=empty`). A workspace with no grants shows one next step: "Add your first grant", one paragraph on what happens (the agent reads the award letter and cites each term, nothing is checked until you confirm), the four steps from Add a grant, and the main button. The sidebar says "No grants yet". A workspace the user created runs on the real date, so its clock shows no Next button.

**Clickable.** A row or its grant name shows a toast saying it opens that grant's problem list; Add a grant says it opens Add a grant. In the app these navigate.

**Hash params, for screenshots:** `#state=empty` shows the new "Biology department" workspace; `#t=dark` sets the dark theme.

**Uses:** AppShell, the GrantHeader's readiness bar, `ft-count`, `ft-panel`, `ft-steps`, `ft-toast`. New styles are prefixed `ft-wh-`.

**Proposals.** The workspace home as the landing page, the columns, and the deadline sort are proposals; docs/product.md doesn't decide them. The three grants, their people, amounts and dates are synthetic placeholders until the seed data is built.

Don't: sort by name, or hide closed grants. The point of the page is what's due next, and closed grants still answer audits.

**Apr 9 state.** `#at=apr9` opens the workspace on Apr 9, 2026, the grant page's starting point: Example Bay has 46 of 51 charges ready and 5 on its problem list (2 Possible conflict, 2 Needs a human, 1 Missing evidence), and the sidebar clock offers Next: extension notice, Apr 10. Kelp Forest Survey doesn't change. The default stays Apr 12, after the extension and the receipt photo.

**Sidebar.** The sidebar stays full height and sticky, so the clock, Account and the theme switch are always on screen while the grant list scrolls.

In `#at=apr9`, Example Bay still ends Jan 31, 2026, because the extension notice arrives the next day. Its certification was due Mar 31, 2026, so its next deadline is the final financial report on May 1, 2026 (day 90), and it sorts first.
