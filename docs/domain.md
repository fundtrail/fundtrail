# Domain

What the checks need to know about NSF (National Science Foundation) grants. **Verify every rule here against NSF's own pages and eCFR before coding it.** The section numbers below are pointers to check, not settled facts.

## The rules

- **Two layers of rules.** NSF's own terms (the award's general conditions, and NSF's proposal and award policies) sit on top of the federal Uniform Guidance, 2 CFR 200 (Title 2 of the Code of Federal Regulations, Part 200). Both are written into code once and shared by every grant.
- **The award letter adds grant-specific terms:** the period of performance, the budget and its lines, the people and their roles, and any special approval rules.
- **Amendments change the terms,** for example an extension notice. A check uses the terms in force, based on each document's own date.
- For now: NSF only, direct costs only. Rules get organized per funder so more funders can be added later.

## Concepts the checks use

| Concept | What it means for a check | Pointer to verify |
|---|---|---|
| Period of performance | A cost has to be incurred between the start and end dates. An extension moves the end date. | 2 CFR 200.309, 200.308 |
| Allowable cost | A cost has to be necessary, reasonable, allocable and consistent with the award's terms. | 2 CFR 200.403 |
| Allocable cost, shared costs | A cost shared across grants has to be split on a documented basis, for example "56 of 96 samples". | 2 CFR 200.405 |
| Budget lines and rebudgeting | Some moves between budget lines need prior approval from the funder. | 2 CFR 200.308, the award letter |
| Participant support costs | Costs for participants, such as stipends, travel and registration, not for project staff. Moving these funds to other uses needs prior approval. | 2 CFR 200.1, 200.456 |
| Prior approval | The approval has to come from the right person, through the right channel, before the cost. | The award letter, NSF policy |
| Closeout | Final reports are due 120 days after the end date. | 2 CFR 200.344, NSF policy |
| Record retention | Records are kept for 3 years after the final financial report. | 2 CFR 200.334 |

## Approvals

- **Code decides an approver's role** by matching the sender against the people named in the award letter. The model never decides who someone is.
- **Example: the approval channel.** An email approval reaches Needs a human at best, even one from the real Program Officer. Only a Research.gov record reaches Evidence complete. The exact NSF rule gets confirmed before it's coded.
- **Example: self-approval.** A professor approving their own charge is not a prior approval.

## Closeout

- NSF doesn't receive an evidence packet. Our packet is the accountant's sign-off before the final financial report goes in, and it's the audit file the university keeps for the retention period.
- Confirm the NSF closeout details, such as deadlines and which reports are due, against NSF's own pages.

## Glossary

| Term | Meaning |
|---|---|
| Award letter, award notice | The document that creates the grant and states its terms |
| Principal Investigator (PI) | The professor who leads the project |
| Program Officer (PO) | The NSF person responsible for the program, who approves scientific and budget changes |
| Grants Officer | The NSF person with authority over the award's financial and legal terms |
| Research.gov | NSF's system for grant requests and approvals |
| Sponsored programs office | The university office that manages grants. Our user, the grant accountant, works here. |
| General ledger | The accounting system's record of every charge to every grant |
| Ledger line | One entry in the ledger, with an ID, transaction date, posting date and amount |
| Transaction date, posting date | When the cost happened, and when the ledger recorded it |
| Reversal, cost transfer | New ledger lines that undo or move an earlier charge. The ledger never edits a line. |
| Direct costs | Costs charged straight to the project. Indirect costs (overhead) are out of scope for now. |
| Cost sharing, in-kind | Contributions the university or a third party makes to the project. In-kind cost sharing is out of scope for now. |
| Closeout | Finishing a grant after its end date: final reports, final charges, and the audit file |

## Not decided yet

| Item | Who settles it |
|---|---|
| The exact list of NSF rules to code for the hackathon build | product |
| The exact approval-channel rule, verified against NSF's pages | product |
| The closeout details: deadlines and which reports are due | product |
| How each rule is coded, and how rules are organized per funder | builder (W2) |
