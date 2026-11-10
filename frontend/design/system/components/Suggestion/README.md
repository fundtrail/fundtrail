# Suggestion

A fix the agent suggests to an earlier link, waiting on the charge until the accountant approves or rejects it.

**The consumer provides** the suggested record and the record it would replace (`replaces_id`), the agent's reason and quotes, and the approve and reject actions.

- The card is `paper-raised` with a 1px `needs-human` outline. The header reads "Waiting for you" on `needs-human-tint`, with the Agent label.
- Show "Now" and "Suggested" side by side so the change is plain, then the reason and a Source link to the passage it rests on.
- Approve first (`ft-btn--approve ft-btn--main`), then Reject (`ft-btn--reject`). Both are `ft-btn--sm`.
- After a decision, the card leaves and the history records it: "Link corrected by the accountant, May 22, 2026."

Don't: apply the fix before the accountant decides, or hide the current link.

Inside a charge's details, a waiting fix is a link in the Trail with its actions under it; use this card where fixes are listed on their own, such as the Grant terms page.
