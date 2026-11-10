# Trail

A charge's evidence trail: the charge at the top, then every link of proof behind it, and exactly where the trail breaks and what would fix it. The signature of the product, and the main view of a charge.

**Use it** as the body of a charge's details. It replaces separate lists of reasons, receipts and suggestions: each of those is a link in the trail.

**The consumer provides** the charge (ledger line, amount, account, date) and its links in order: each linked receipt, approval or explaining email with what code checked on it; the agent's answers; the grant term a check rests on; and anything waiting or missing.

| Node | Class | Verdict color | Meaning |
|---|---|---|---|
| Ink square | `ft-trail__node--charge` | `ink-muted` | The ledger line itself, always first |
| Blue check | `ft-trail__node--ok` | `ink-muted` | A link that holds: "Amount matches", "Known sender", "Supports", "In the period" |
| Red diamond | `ft-trail__node--fail` | `conflict` | Where the trail breaks: "Breaks the trail", "Wrong approver" |
| Amber ring | `ft-trail__node--human` | `needs-human` | A link only a person can settle: "Split unknown", "Unsure" |
| Dashed amber ring | `ft-trail__node--wait` | `needs-human` | A fix waiting for the accountant, with its actions under it |
| Dashed gray ring | `ft-trail__node--missing` | `missing` | What would complete the trail but isn't on file: "Not on file" |
| Small gray dot | `ft-trail__node--replaced` | `ink-muted` | A link that no longer applies, title struck through: "Replaced" |

- Each item is its name (the name is the link that opens the viewer at the passage), a verdict on the right, and, only for links that break, wait or are missing, one line of what it shows, written by code. Links that hold are a single line: color is left for exceptions.
- A link that decides something (one that breaks, one waiting for the accountant) also shows its quoted passage in `quote`, without yellow, with its location (`ft-trail__quote`).
- At a break caused by dates, one line lays the dates side by side (`ft-trail__dates`): "Grant ended Jan 31, 2026 → Work done (ledger) Feb 20, 2026 → Proposed end Jan 31, 2027". Say which source each date comes from.
- Name a judgment by what was checked, not who checked it: "Necessary, reasonable and for this project · Agent supports".
- Under a waiting fix's actions, one muted line says what the click will change (`ft-trail__scope`): "Updates the grant end date to Jan 31, 2027 and rechecks its charges. 1 charge would become ready."
- After the accountant acts, the result and Undo appear at the end of the trail (`ft-trail__done`, `role="status"`), and focus moves there, so a screen reader hears one outcome: "Extension confirmed. 47 of 51 charges ready." If a recheck fails, say so in the same place and offer Retry.
- A superseded term reads "End date superseded", not "Replaced": only that term is replaced, not the whole document.
- The line between two links is solid `rule-strong` while the trail holds. Below a broken or uncertain link it is dashed: `ft-trail__item--gap` (amber, toward a fix) or `ft-trail__item--gap-missing` (gray, toward something missing).
- Actions sit under the link they act on (`ft-trail__actions`): Confirm and Reject under a waiting term, an answer under the agent's Unsure.
- **When the trail is repaired on screen**, the broken link becomes Replaced, the fix becomes a blue check, and the dashed line turns solid. The charge's bucket changes with it (see ChargeRow).
- Label the list "Evidence trail" (`ft-trail-label`). Put History under it, closed.

Don't: show a link without its verdict, color a link that holds, or quote every link.
