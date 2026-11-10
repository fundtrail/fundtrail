# BucketBadge

The bucket a charge is in, as a word with a mark in a soft pill: Possible conflict, Needs a human, Missing evidence or Evidence complete.

**Use it** wherever a charge's status appears: charge rows, the charge's details, status history, the bucket summary and the evidence report.

**The consumer provides** the bucket (`Bucket` in `backend/app/contracts/checks.py`: `possible_conflict`, `needs_human`, `missing_evidence`, `evidence_complete`) and, when the status has it, `rechecking`.

| Bucket | Class | Mark |
|---|---|---|
| `possible_conflict` | `ft-badge ft-badge--conflict` | Diamond |
| `needs_human` | `ft-badge ft-badge--human` | Ring |
| `missing_evidence` | `ft-badge ft-badge--missing` | Dashed ring |
| `evidence_complete` | `ft-badge ft-badge--complete` | Dot |

- Every badge is the same pill: 22px tall, at least 132px wide, `radius-pill`, a tinted fill, no outline.
- On a charge's details the pill sits at the right end of the ID line. When the bucket changes it fades out (`ft-swap is-out`) and the new pill fades in (`ft-appear`).
- The rubber stamp (`is-stamped`) is retired: reviewers found it noisy, and it moved the badge around.
- When `rechecking` is true, keep the badge and add `<span class="ft-tag ft-tag--rechecking">Rechecking</span>` beside it, wrapped in `ft-status`.
- For the agent's answer words (Supports, Contradicts, Unsure) use `ft-chip`, not a badge.

Do: write the bucket name exactly as above. Don't: shorten it, color a row instead of using the badge, or show a mark without its word.
