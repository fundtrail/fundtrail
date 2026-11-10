# GrantTerm

A term read from the award letter or an amendment, with its quote and whether the accountant has confirmed it.

**The consumer provides** a `Term` from the API: the record (period of performance, budget line, person, approval rule or other term) with its citation, and its state (`confirmed`, `waiting` or `rejected`).

- Waiting terms show Confirm (`ft-btn--approve ft-btn--main`) then Reject (`ft-btn--reject`). No check uses a term until it is confirmed.
- Confirmed is an `approve` green word; Rejected strikes the value through in `ink-muted` and says who rejected it and when.
- An amendment's term sits above the term it changes, so the accountant sees both.

For the first review of a new award letter, use TermReview: quiet Correct and Reject per row, one Confirm for the set.

Don't: show a term without its quote, or color a waiting term as a problem. It is waiting, not wrong.
