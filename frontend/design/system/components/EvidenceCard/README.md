# EvidenceCard

One piece of evidence and every fact the agent read from it, each with its quoted passage and location.

**The consumer provides** an `EvidenceCard` from the API: the file's display name, its source (Gmail, Google Drive or upload), arrival date, and its fact records (receipt, approval, note, or a grant term), each with its citation.

- Facts are label, value, then the quote in `quote` on `highlight` with its location in `caption` ("line 8", "p. 2", "box checked by a second look"), and an unconfirmed fact says so instead of showing a highlight.
- Clicking a quote opens the viewer at that passage.
- The "Agent" label shows the facts are the agent's. A fact the accountant corrected shows their attribution line under it.
- A file that arrived before its ledger line has no links yet: add the caption "Waiting for its ledger line" under the title.
- Source names are written out: "Google Drive", not "drive".

Don't: show a value without its quote, or highlight anything that isn't verbatim from the file.
