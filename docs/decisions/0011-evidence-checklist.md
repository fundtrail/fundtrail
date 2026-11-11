# 0011. Each charge has an evidence checklist

**Date:** 2026-11-09 · **Status:** accepted. Amends [0009](0009-agent-judges-code-checks.md). Amended by [0016](0016-default-checklists-by-account-group.md) (defaults hang on groups of accounts, and Berkeley's effort reports come twice a year, not every quarter) and [0030](0030-benefit-charges.md) (code recalculates a benefit charge from its rate and its salary lines).

## Context

[0009](0009-agent-judges-code-checks.md) had one rule for evidence: the receipts linked to a charge add up to its amount. That fits purchases. It doesn't fit salaries, stipends, fringe benefits or per diem, which never have a bill. With missing evidence now flagged after 60 days ([0010](0010-agent-suggests-accountant-decides.md)), every payroll line would land on the problem list.

A charge can also be filed under the wrong ledger account, such as a laptop posted as a participant stipend. Nothing caught that unless an approval rule happened to apply.

## Decision

- **Every charge has a checklist of the evidence it should have.** Code tracks each item as filled or missing.
- **Defaults come from the ledger account.** Each account has a default list, for Berkeley's accounts first. An account with no default gets only the agent's items. The defaults live in the code for now, and code works them out fresh each time. So a fixed default reaches old charges too, which can put them back on the list.
- **The agent adds what the charge needs.** Adding takes effect right away. Removing an item is a suggestion that waits. So a misfiled charge surfaces when the agent asks to drop a default that doesn't fit.
- **The accountant can add or remove items,** and their changes take effect right away.
- **Code adds a required approval as an item** when an approval rule applies. A reversal or cost transfer defaults to the line it corrects plus a written justification.
- **Bills still add up.** An item that carries an amount is checked against the bills linked to it, and the amounts on a checklist add up to the charge. When an amount comes from a rate, the agent writes the math and code re-checks it. The quantity and the rate are both cited, and the rate has to come from a file on the grant. A rate for the whole grant, such as a fringe benefit rate, is a term the accountant confirms once.
- **One document can fill items on many charges.** An item can name a period, and code checks that the linked document's period covers it.
- **An item can say when it's expected,** and the 60 days count from then. An effort report signed after the quarter isn't late before the quarter ends. Inside the 90-day closeout window every missing item is listed anyway, with its expected date shown.
- **A charge with an empty checklist is in Needs a human.** Otherwise a charge on an account with no default, where the agent adds nothing, would be complete with no evidence.
- **Structure over memory.** When a file arrives, code hands the agent every item still missing on the grant and asks which ones the file fills.
- **Invoices and receipts are one kind of record.** "Receipt" is renamed to cover invoices, receipts and card slips. "Bill" is the working name.

## Considered and set aside

- **Exempting payroll.** It's usually the largest cost on a grant.
- **The accountant checking every such charge by hand.** A click on every payroll line.
- **Sorting charges into fixed groups,** each with its own rule. The groups overlap, since a trip is part receipt and part rate. They're never complete, and putting a charge in the wrong group is a new mistake to make.
- **Letting the linked evidence decide which check applies,** with no checklist. A mixed charge like a trip doesn't fit, and nothing says what's missing.
- **The agent writing the whole checklist.** The agent would set its own bar.
- **One broad question, "is the evidence enough?"** Concerns get overlooked, which is why [0009](0009-agent-judges-code-checks.md) set broad questions aside.

Defaults plus the agent's items combines the third and fifth options: code sets the minimum and the agent adds the nuance.

## Consequences

- The contracts add a checklist item record, links that name the item they fill, and a default checklist per ledger account (see [contracts.md](../contracts.md)).
- The default table covers Berkeley's account names for now. Other universities name accounts differently.
- An account with no default rests on the agent alone. That's the weak spot.
- The eval gets a case for each kind of nuance: a quarterly report, a per diem, a misfiled charge, a real exception.
