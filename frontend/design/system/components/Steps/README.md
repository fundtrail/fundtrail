# Steps

Where the accountant is in adding a grant: Award letter, Terms, Ledger, Evidence.

**Use it** at the top of the Add a grant page, under the page title. One indicator per flow; never more than four steps.

- **Structure:** `ol.ft-steps` holds `li.ft-step`, each with `ft-step__n` (a 22px circle) and a short noun label. A 32px `rule-strong` line joins neighbors.
- **Current:** `is-current` plus `aria-current="step"`: a filled `ink` circle and `ink` label.
- **Done:** `is-done`: the circle shows a check instead of the number. A done step is a button (`ft-step__btn`) that goes back to that step, with an `aria-label` like "Terms, done. Go back to this step." Going back never discards work: confirmed terms stay confirmed until the accountant changes them.
- **Ahead:** plain `ink-muted` label and an outlined number. Not clickable; steps unlock in order.

Don't: color the steps green or blue (color is for buckets), add a progress percentage, or let a step be skipped past one that isn't done.
