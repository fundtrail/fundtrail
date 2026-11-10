# AppShell

The frame of every screen: a left sidebar for navigation, a top bar naming the page, and the main area. An intentional addition: the docs leave screen layouts to the builder, and every screen needs the same frame.

**The consumer provides** the workspace name, the list of grants with the current grant's pages, counts for what needs the accountant, the clock's date, the page title, the grant's end date and the top bar's actions.

- `ft-app` is a two-column grid: `ft-sidebar` at `sidebar-width`, then `ft-main` holding `ft-topbar` (`topbar-height`) and `ft-content`.
- The sidebar sits on `paper`, separated by a `rule` border. Panels in the main area sit on `paper-raised`.
- Sidebar, top to bottom: the wordmark, the workspace switcher, a Workspace item (the workspace home), one Grants list, and the clock with an Account menu at the foot. In a demo workspace the clock has a Next arrival button (`ft-sidebar__next`) naming what arrives next: "Next: extension notice, Apr 10". While the agent reads it, the button says "Reading…". The current grant (`ft-nav__item--grant`) opens to its pages in `ft-nav__children`: Problem list, Charges, Evidence, Grant terms, Closeout.
- The active page is `is-active` (`ledger-tint` with `ledger` text) and carries `aria-current="page"`.
- Counts appear only where something needs the accountant: problems (`ft-count--alert`) and terms waiting. Never a count of everything, never a percentage.
- The top bar shows breadcrumbs (grant, then page) and the grant's end date, with page actions on the right. One main action at most. On a page that opens with the GrantHeader, the end date is on its timeline, so the top bar shows only the breadcrumbs.
- While the agent is working, the top bar says so: `ft-working`, a pulsing `ft-working-dot` and "Agent is reading extension_notice.txt from Google Drive", with `role="status"`.
- Problems that aren't about one charge, such as a bill with money nobody charged, are records on the problem list (PR 6), not a banner.
- Use `ft-split` for the list left, charge right layout: the left side only lists, the right side only shows the selected item.
- On the grant page and Charges, everything below the GrantHeader fills the rest of the screen and the two columns scroll independently; the page itself doesn't scroll. The right panel docks the item's review thread at its bottom, with the ask box always visible. Below 1024px wide the page scrolls as one.

Don't: hide the clock. Every date in the app depends on it.
