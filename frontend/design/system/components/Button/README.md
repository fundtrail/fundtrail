# Button

Actions, labeled in words: an outline over a solid fill. An intentional addition: the docs name approve, reject, confirm and sign off, but no button style.

**The consumer provides** the label, the handler, and whether this is the view's main action.

- **Neutral** (`ft-btn`): a 1px `ink` outline over `paper-raised`; hover is `paper-sunken`. Black in light, near-white in dark. Every button that isn't an approve or reject decision.
- **Approve** (`ft-btn--approve`): an `approve` green outline, label and check over `approve-tint`. Approve on suggestions, and Confirm on grant terms.
- **Reject** (`ft-btn--reject`): a `reject` red outline, label and x over `conflict-tint`.
- **Main action** (`ft-btn--main`): a 2px outline instead of 1px, on the one button a view is for (Approve, Confirm, Sign off). One per view.
- **Quiet** (`ft-btn--quiet`): underlined text with no outline, for low-stakes toggles inside a card.
- `ft-btn--sm` (`control-sm`) inside cards; the default height is `control-md`.
- Disabled buttons get a dashed `rule-strong` outline and `ink-muted` text, never lowered opacity. Say why nearby: "Sign off after the problem list is empty."
- Focus is a solid 2px `focus` outline, offset 2px.
- Approve, Confirm and Reject act at once and offer Undo in a Toast. Never put a confirmation dialog in front of them.

**For red-green color blindness**, an approve and reject pair never relies on hue alone:

1. The green leans teal and the red leans orange, so they part along the blue-yellow axis.
2. In light, the green is darker than the red, so they differ in grayscale too.
3. Approve is the main action, with the thicker outline.
4. Approve always comes first, Reject second.
5. Each carries its mark: a check before Approve, an x before Reject, and always the word.

Don't: use icons without words, color any other button green or red, or put Reject before Approve.
