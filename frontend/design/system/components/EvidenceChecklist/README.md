# EvidenceChecklist

What a charge should have, from PR 6's decision 0011 (not merged yet). It sits in the charge panel, above or beside the evidence trail.

**One line per item:** a mark, what's needed, what fills it, its state and who added it.
- **Filled** has a check. **Missing** has a dashed ring and, when it has one, the date it was expected. **Not complete** (a bill linked but its part for this charge unknown) has a half ring. The state is always written out, so it reads without color.
- **Who added it:** Account default, Added by code (a required approval from the award's rules), Added by the agent, Added by you.
- **Periods and dates:** an item can name a period ("Effort report, January 2026") and the date it's expected. "Not due yet" before that date.
- **Rate items** write the math out ("5 days × $100.00 = $500.00, checked by code"). When items carry amounts, a sum line shows they add up to the charge.

**Removals wait.** When the agent suggests removing an item, the suggestion sits under it with its reason and Accept, then Reject. Accept strikes the item ("Removed by you, accepting the agent's suggestion"). Reject keeps it and says the agent can't suggest it again unless new evidence arrives. Both show the inline done line with Undo. Your own changes take effect right away: **Add item** opens an inline field.

**Use it:** `FTChecklist.render(items, opts)` returns HTML; `FTChecklist.mount(container, items, opts)` adds Accept, Reject, Undo and Add item, and calls `opts.onChange(items)`. `FTChecklist.summary(items)` gives the filled, missing and waiting counts. Options: `account` (the ledger account, shown in the header), `sum` ({parts, total}), `title`, `today`.

**The examples** are PR 6's four (a trip with per diem, a January salary filled by a quarterly report, a laptop posted as a stipend with a removal waiting, a speaker's honorarium swap you accepted) and the demo's L-0981. Hash params: `#t=dark`, `#w=560` to see it at panel width.

Don't: hide a missing item behind a count, or let the agent's removal take effect without your click.
