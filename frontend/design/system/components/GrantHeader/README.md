# GrantHeader

Where a grant stands, at the top of its pages: its name, how many charges are ready for closeout, and its timeline with today on it.

**The consumer provides** the grant (award number, funder, amount awarded, full title), the total charged, the count of charges per bucket, the period of performance with any amendment waiting, and the clock's date.

- **Name**: the award number, funder (spelled out on first use), amount awarded and total charged in `caption`, then the full title in `display` (`ft-grant-head__title`).
- **Readiness** (`ft-ready`): the count of Evidence complete charges (32px, 600), "of 51 charges ready for closeout", and a thin 6px bar split by bucket, worst first. No legend: the filter tabs already give the counts. Counts only, never a percentage.
- **Timeline** (`ft-timeline`): a thin 2px line, 56px tall, with one-line labels: start, the end date and today, the past in `ink-muted`. Color only on the overrun and the waiting date.
  - Today after the end date: the stretch after it turns `conflict`, and today's label reads "Today, after the end date" (`ft-timeline__mark--late`).
  - An amendment waiting to be confirmed: a dashed `needs-human` line to the new end date, labeled "New end date, waiting for you" (`ft-timeline__mark--ghost`).
  - Labels near the right edge align right (`ft-timeline__mark--right`). Keep labels short ("New end date" over "Jan 31, 2027, waiting") so neighbors never collide at laptop widths. Give the timeline an `aria-label` that says the same in words.
- When the main area is under 900px, the readiness block moves under the name.
- Everything here updates live with the clock and every recheck.
- With the GrantHeader on a page, the top bar shows only the breadcrumbs: the end date is on the timeline.

Don't: add other charts, or show money as a share of the budget.
