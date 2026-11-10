# BucketSummary

How many charges sit in each bucket, in two forms: filter tabs above a list, and a strip on reports.

**The consumer provides** `bucket_counts` from `GrantSummary`; for the strip's optional foot, the number of charges, the award number and the total charged (which matches the ledger report).

**Filter tabs** (`ft-tabs`, `ft-tab`), above the problem list:

- All, then Possible conflict, Needs a human and Missing evidence, each with its mark (`ft-tab-mark--conflict`, `--human`, `--missing`) and an `ft-count`. Evidence complete is not a tab: those charges are not problems, and they live on the Charges page.
- The selected tab has `aria-selected="true"`: `ink` text with a 2px `ink` underline. Selecting a tab filters the list; if the selected charge is filtered out, select the first that remains.
- When a count changes on screen, flash it with `is-bumped`.

**Strip** (`ft-summary`), on the evidence report and the Charges page:

- Each cell is the bucket's `BucketBadge` with its count beside it, at the `title` size in tabular figures, cells split by a `rule` line. Always all four buckets, including zeros.
- The foot (number of charges and total charged) is optional.
- Below 760px of its own width the cells wrap two by two.

Don't: turn the counts into percentages or a chart.
