# ChargeRow

One ledger line as a row: date, description with its ledger ID, amount, bucket, and code's one-line reason.

**Use it** for the problem list, the charge list in a grant and the closeout view. The evidence report's charge table uses the same columns.

**The consumer provides** a `ChargeRow` from the API: its `charge` (`transaction_date`, `description`, `ledger_line_id`, `amount_cents`) and its `status` (the bucket and the most serious reason's `text`). Status is `None` until the checks first run: show the row without a badge and the caption "Not checked yet".

- Wrap rows in `ft-ledger`, with an `ft-ledger__head` row of column labels. Inside a panel, add `ft-ledger--flush` to drop its own border. On the problem list the table is the whole panel, with no heading above it: the sidebar and top bar already name the page.
- The ledger ID sits under the date, so the description column keeps its width for the charge's name and reason.
- Dates and amounts use tabular figures; amounts align right and show cents. A reversal or transfer out is negative: "-$650.00".
- The reason line is code's status text, never the agent's reasoning.
- `is-selected` marks the charge open beside the list. Rows are focusable and open the charge on Enter.
- On narrow screens the header hides and the date moves above the description.

- Something that just arrived gets an `ft-new` tag after the charge's name until the accountant acts on it.
- Rows take the keyboard: the up and down arrows move through the list, Enter selects.
- **When a charge's bucket changes on screen**, it changes visibly, once: the row's badge swaps and the row turns `is-resolved` (`complete-tint`) for about a second, then collapses out of the problem list (`ft-collapse`) while the counts update. If the charge is open on the right, its stamp lifts (`ft-swap is-out`) and the new badge appears. Under `prefers-reduced-motion` it changes at once.

Do: sort the problem list by severity, then date. Don't: truncate the ledger ID or reformat it.

In a list narrower than 640px the amount and the bucket stack in one column on the right; narrower than 420px the date moves under the name. The list adapts to its own width, not the window's.
