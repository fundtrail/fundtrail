# Walkthrough

Start here. Every screen in the order the accountant meets them, joined by the screens' own buttons, so you can click through the whole product: sign in, the workspace home, adding a grant, the grant page with its evidence trail, checklist, thread and viewer, Charges, Evidence, Grant terms, Closeout, the evidence report, and the screen map.

**Getting around.** Click the real controls: Continue with Google, a grant's row, Add a grant, the sidebar's Workspace, Problem list, Charges, Evidence, Grant terms and Closeout, the top bar's Evidence report, Open the problem list, and Sign out. The bar at the top also jumps to any screen, steps Back and Next, restarts the current screen, and switches light and dark. A one-line hint under it says what to try on each screen.

**Built from the other cards.** Each screen is the published card, unchanged, with a small script that sends its navigation clicks to this page. Everything inside a screen still works as it does on its own card. Rebuild this card (`tools/walk/build.py` in the design system's tooling) whenever a screen changes.

**Not a live app.** Each screen keeps its own demo state: confirming the extension on the grant page doesn't change Closeout. Kelp Forest Survey and Tidal Marsh Carbon have no grant page of their own.
