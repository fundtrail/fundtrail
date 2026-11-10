# Toast

One line at the bottom of the screen saying what just happened, with Undo when the accountant caused it. An intentional addition: it replaces "are you sure?" dialogs.

**The consumer provides** the sentence and, for the accountant's own actions, the undo handler.

- `ft-toast` floats at the bottom center: `ink` fill, `paper-raised` text, `shadow-float`. It has `role="status"`, so screen readers announce it.
- Confirm, Approve and Reject apply at once and never ask first. On a charge, their result and **Undo** appear at the end of its trail, where the accountant acted (see Trail), not in a toast.
- A toast is for changes the accountant didn't make: evidence that arrived, a charge that cleared itself. No Undo there.
- Write what changed and the result: "New end date confirmed. L-1002 is now Evidence complete." Name the charge by its ledger ID.
- One toast at a time; a new one replaces the old.

Don't: use a toast for errors that need action, or for anything the accountant must read later. Those belong on the charge.
