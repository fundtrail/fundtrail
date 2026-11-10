# FundTrail design

The design for every screen of FundTrail, and the design system the frontend builds from. All data in it is synthetic.

It follows the docs on main, including decisions [0010](../../docs/decisions/0010-agent-suggests-accountant-decides.md) to [0012](../../docs/decisions/0012-checked-quotes-and-highlights.md). Where the docs leave a screen undecided, the design makes a proposal, listed below.

## Look at it

- **Click through every screen:** run `frontend/design/tools/build_all.sh`, then open `frontend/design/build/screens.html` in a browser. It opens on an overview of all the screens. Click one to open it full size; its own buttons move you on (Continue with Google, a grant's row, the sidebar, Evidence report, Sign out). A bar at the top jumps between screens, switches light and dark, and shows the demo clock.
- **One card at a time:** the same script renders each card on its own into `build/cards/<Card>.html`.
- **Hosted copies:** Grant has the same pages as two private artifacts, the screens page and the design system. Ask him to share them if you'd rather not build.

The build needs Python 3. Screenshots and the screen map's thumbnails also need Google Chrome (set `CHROME` if it isn't in the usual macOS place); without it those steps are skipped.

## What's here

| Path | What it is |
|---|---|
| `system/README.md` | The brand book: content rules, layout, color, type, buckets, citations, the viewer, the problem list, threads and checklists, closeout, sign-in |
| `system/tokens.json` | Colors for light and dark, type, spacing, radius, sizes |
| `system/components/bundle.css` | Every style, as `ft-` classes on the tokens |
| `system/components/<Card>/` | One folder per component or screen: `preview.html` (the live example) and `README.md` (states, rules, what not to do) |
| `system/components/_src/` | Shared demo scripts (the viewer, the thread, the checklist, problem records, the workspace menus) and the evidence report's data and pages. Demo code, not production code. |
| `tools/` | The scripts that build the cards from `_src`, the report, the walkthrough and the screens page |

## The screens

| Screen | Card |
|---|---|
| Sign in, and the first sign-in's setup | `SignIn` |
| The workspace home, every grant with its readiness and next deadline | `Workspace` |
| The workspace and account menus, and the New workspace and Reset dialogs | `WorkspaceMenu` |
| Adding a grant: the letter, the terms, the ledger, the evidence | `AddGrant` |
| The grant page: the problem list, each charge's evidence trail, checklist and docked agent thread | `Demo` |
| Every charge on the grant | `Charges` |
| Every evidence file, its facts and what it pays for | `Evidence` |
| The grant's terms, amendments and reusable notes | `GrantTerms` |
| The viewer: text, email, PDF, photo, and a quote that couldn't be placed | `Viewer*` |
| Closeout: Berkeley's steps, what's left, the sign-off | `Closeout` |
| The evidence report, 9 pages | `EvidenceReport` |
| All of them in order, with the click that leads from one to the next | `ScreenMap`, `Walkthrough` |

The demo follows Example Bay (SYN-2300117) from Apr 9 to Apr 12, 2026: the extension notice arrives and is confirmed, a receipt photo arrives, the accountant asks the agent about the microscope camera, answers it, and enters the shared run's split. The problem list goes 5, 6, 4, 3, 2, 1 and the ready count 46 to 50 of 51.

## Proposals that need your call

These are places the docs list as not decided. The design picks one so the screens are complete.

1. **The grant page layout.** The problem list on the left and the selected problem on the right scroll on their own. The charge's review thread is docked at the bottom of its panel with the ask box always on screen. Grant tried a bottom-right chat bubble and a header button and chose this.
2. **The problem list's sort.** Records (a term waiting, a bill nobody charged) come first, then charges by bucket.
3. **Grant terms.** Terms waiting for confirmation sit at the top (they're also rows on the problem list), then the terms in force, then what they replaced, then the reusable notes. The agent's suggestions stay in each charge's thread.
4. **Snooze before the extension.** On Apr 9 the grant is past its original end date, so only Accept with a note is offered until the new end date is confirmed.
5. **Default checklists.** Every demo account uses "A bill that adds up to the charge" until the defaults per ledger account exist.
6. **The evidence report.** Its name, a 9-page layout (summary, every charge, six charge sections, open at sign-off and sign-off, sources), and the sign-off: the accountant signs off in FundTrail with a note (required while charges are open), and the supervisor's approval in BFS gets a blank "Reviewed by" line on the report.
7. **Sign-in and workspaces.** Every sign-in lands on the workspace home. The first sign-in copies the seed into "Demo workspace". Reset clears everything the accountant did and sets the clock back. Extra workspaces are designed but marked optional.
8. **The demo story's data.** L-1010, L-1015 and L-1019 are dated January 2026 so they sit inside the original period; the shared sequencing run is "run 6", so it comes before L-1002's run 7; 45 more charges are generated to reach the grant's $96,412.18; Kelp Forest Survey and Tidal Marsh Carbon are placeholders. The extension notice arrives Apr 10 in the demo and Apr 9 in contracts.md's golden fixture. Add a grant uses the seed letter SYN-2400042, which PR 7 removed from `data/`.

## Where the design is behind main

Main's product.md changed after these screens were drawn:

- **Reusable notes** replace "standing notes": a one-off or reusable note, three limits (same problem; same account and vendor; an amount no larger than accepted under that note), and the "Accept the same way?" offer on a similar charge. The dialog and Grant terms still show the older standing note.
- **Accepted charges** should show as Accepted, with the note, be counted on their own in the report, and be reopenable.
- **A snooze inside the closeout window** can still be set, up to the grant's end date.

## Known limits

- Each screen keeps its own demo state. The screens page carries the demo clock between screens, but an answer or a split on the grant page isn't kept when you leave and come back, and a rejected amendment comes back waiting.
- On a charge whose newest thread entry is long, the docked thread can take about half the panel. Below 1024px wide the two columns fall back to one page scroll.
- The scripts in `_src` are for the demo. The frontend should take the tokens, the classes and the rules in each README, not these scripts.
