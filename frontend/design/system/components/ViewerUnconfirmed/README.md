# ViewerUnconfirmed

The viewer when a fact couldn't be confirmed in its file (decision 0012 in PR 6, not merged yet). Quotes are checked against the file: text by exact characters, PDFs by finding the passage on its page, photos and scans by a second look at the boxed area. When that fails, the fact is unconfirmed.

**What the viewer does.** It opens the fact's page with no highlight and no box, so nothing is guessed. A panel above the page, which stays in view while the page scrolls, shows the quote (or, for a photo, the value the agent read), says that anything resting on the fact is in Needs a human, and offers two actions:

- **Confirm the value** marks it confirmed by you.
- **Type the right value** opens an inline field; Save sets the value and confirms it.

Either one leaves an inline result line with Undo, and the fact stays "not placed in the file": the bar says "Confirmed by you · not placed in the file" and the side list says "Confirmed by you". The side list marks a fact still waiting as "Unconfirmed".

**Data.** A fact with `confirmed: false` is unconfirmed. After the accountant settles it, the frame sets `confirmed: true`, `placed: false` and `confirmedBy: 'you'`. Facts without these fields behave as before, so every other card and page is unchanged.

**Photos.** A box is now drawn solid, because a second look checked it; the bar says "Box checked by a second look". An unconfirmed photo fact opens the whole photo with no box.

**Hash params, for screenshots:** `#file=F7` shows the camera receipt photo instead of invoice SEQ-0311 (F5), `#fact=N` picks a fact, `#t=dark` sets the dark theme. In both cases the card marks the file's Total unconfirmed on its own copy of the data.

Don't: draw a guessed highlight or box for an unconfirmed fact, or let it make a check pass.
