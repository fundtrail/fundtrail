# 0015. Code checks six rules, and the agent's rulebook holds the rest

**Date:** 2026-11-10 · **Status:** accepted. Amends [0009](0009-agent-judges-code-checks.md).

## Context

[0009](0009-agent-judges-code-checks.md) split the work: code checks the clear-cut rules and the agent answers the rest. It named code's checks loosely, and [domain.md](../domain.md) still listed as open which National Science Foundation (NSF) rules code checks and which become questions for the agent.

Reading NSF's Grant General Conditions (GC-1), its Prior Approval Matrix, its policy guide and the federal cost rules in 2 CFR 200 (Title 2 of the Code of Federal Regulations, Part 200) changed three of the checks:

- Not every date outside the grant's period is a conflict. The university may approve costs up to 90 days before the start date on its own.
- Some things need NSF's approval on every NSF grant, whatever the award letter says.
- Going over one budget line isn't a violation, because the university may move money between lines.

A comparison with outside sources then found 17 rules about a single charge that the list didn't name. Many have the form "this kind of cost isn't allowed, or only under a condition".

## Decision

- **Code checks six rules.** Five are about a charge. One, the budget, is about the grant and never adds a reason to a charge.

  | # | Code checks | When it fails |
  |---|---|---|
  | 1 | The cost's date is inside the grant's period in force | Possible conflict |
  | 2 | Every item on the evidence checklist is filled, and the amounts add up | Missing evidence, or Needs a human if the amounts go over |
  | 3 | A required approval is there, from the right person, through the right channel, before the cost | Missing evidence if there's none. Possible conflict if it's the wrong person, the wrong channel or too late. |
  | 4 | The budget, on the grant: spending against each budget line and against the award's limit | A note or a problem on the grant. See below. |
  | 5 | Every value the charge rests on is confirmed | Needs a human |
  | 6 | A reversal or cost transfer names the line it corrects and has a written justification | Missing evidence, reported by check 2 |

- **The date check follows NSF's four zones.** During the grant is fine. Up to 90 days before the start date is allowed, and the checklist asks for the university's own pre-award approval, so a missing one shows as missing evidence, not a conflict. More than 90 days before is Possible conflict unless NSF's approval is on file, which means an approval linked to the charge that the agent's Covers answer supports. After the end date is Possible conflict, and the agent can dispute it with proof that the order was placed before the end date.
- **The approvals check carries NSF's standing list.** It's the same for every NSF grant, and each award letter adds what's specific to its grant. Among the things a charge can show, the list is: moving money out of participant support, a payment to a partner institution that wasn't in the proposal, faculty salary above the base salary, dependents' travel, buildings and land, and extra participant items such as gifts and t-shirts. Equipment and foreign travel don't need approval. When the agent recognizes one of these, "NSF approval" goes on the charge's checklist, and a missing one is flagged right away. An approval that came by email stays in Needs a human, since whether it counts outside Research.gov isn't confirmed.
- **The budget check runs on the grant.** An overspent budget line is a note on the grant, and spending over the award's limit is a problem on the grant. The limit is the "Total Amount Obligated to Date" on the latest confirmed notice, and spending is the sum of the charges on the grant's ledger. Moving money out of Participant Support stays with the approvals check.
- **Check 6 has no reason of its own.** The line it corrects and a written justification are the reversal's two default checklist items, and the checklist check reports them, filled or missing.
- **Kind-of-cost rules go to the agent.** Every rule of the form "this kind of cost isn't allowed, or only under a condition" is answered by the agent under the Allowable question, with the passage that shows it: airfare class, U.S. airlines for international trips, meals and hotels for staff who aren't travelling, publication fees for unrelated work, benefit rates applied to stipends, the costs that are never allowed, consultants who are employees, office staff salaries charged directly, and long-term visas. A documented exception on file turns the answer to supports.
- **Purchases close to the end date are the agent's flag.** Code has no day count, because NSF names none. The agent is given the end date in force and flags equipment, a computer or a restock bought with little time left to use it. It's a flag, which sends the charge to Needs a human, and not contradicts, because NSF's wording is "typically should not" and only the professor knows whether the item was used.
- **Participant support paid to project staff is the agent's comparison.** The agent compares who was paid with the people named on the grant. A match is contradicts, citing both lines. Someone not named on the grant is supports.
- **A late extension notice is the agent's flag.** When a notice was filed less than 10 days before the end date and no NSF approval is on file, the agent flags the notice, and the accountant sees the flag when confirming the new end date.
- **The agent's rules live in one rulebook per funder,** starting with NSF. It's a plain file in the repo. Each rule is one or two sentences with its source, and a rule goes in only after it's checked against that source. The agent gets the whole rulebook on every run, and its answer names the rule it used. The accountant doesn't edit it, and there's no settings screen: changing a rule is a change to the file, like the default checklists.
- **The university's own policies come in only through the default checklists for now,** such as Berkeley's rule that lodging needs a receipt at any amount.

## Considered and set aside

- **Any date outside the period as a conflict.** That flags pre-award costs NSF allows.
- **Budget room as a check on each charge.** NSF lets the university move money between lines, so going over one isn't a violation.
- **Code checks for a late extension notice and for costs that are never allowed.** Both go to the agent instead.
- **A number of days in code for purchases close to the end date.** NSF names none.
- **Code comparing the payee with the people named on the grant.** Names are written differently from page to page.
- **Holding the university's other policies,** such as an expense report within 45 days of a trip. Out for now, with the design kept open for them.

## Consequences

- [product.md](../product.md#what-code-checks) lists the six checks and what goes to the agent. [domain.md](../domain.md#what-code-checks-and-what-goes-to-the-agent) holds the NSF rules behind them, with how far each source was read.
- The NSF rulebook has to be written before the agent is built. About a dozen federal cost sections are still unread, so the exact list isn't settled.
- The agent catches only what a document shows. So the checklist has to ask for the document: through the default where every charge in the group needs it, and through the agent's own item otherwise, such as a flight's itinerary when the bill doesn't show the airline and fare class. The agent also knows only the people the documents name: a participant who is a university employee but appears in no document on the grant passes.
- Whether a Program Officer's email counts as approval is still open.
- Indirect costs are out for now, so comparing spending with the award's limit is only as complete as the ledger.
- The checks' output gains problems on the grant itself and a note for an overspent line (see [contracts.md](../contracts.md#8-the-checks-interface)).
