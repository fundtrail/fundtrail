# Domain

What the checks need to know about NSF (National Science Foundation) grants. **Verify every rule here against NSF's own pages and the Electronic Code of Federal Regulations (eCFR) before coding it.** The section numbers below are pointers to check, not settled facts.

## The rules

- **Two layers of rules.** NSF's own terms (the award's general conditions, and NSF's proposal and award policies) sit on top of the federal Uniform Guidance, 2 CFR 200 (Title 2 of the Code of Federal Regulations, Part 200). Both are shared by every grant. The clear-cut rules are written into code once. The ones that take judgment, such as whether a cost is necessary and reasonable, become questions the agent answers (see [architecture.md](architecture.md#trust-rules)).
- **The award letter adds grant-specific terms:** the period of performance, the budget and its lines, the people and their roles, any special approval rules, and anything else it says that those don't hold, such as a principal investigator going on leave.
- **Amendments change the terms,** for example an extension notice. A check uses the terms in force, based on each document's own date.
- For now: NSF only, direct costs only. Rules get organized per funder so more funders can be added later.

## Concepts the checks use

| Concept | What it means for a check | Pointer to verify |
|---|---|---|
| Period of performance | A cost has to be incurred between the start and end dates. An extension moves the end date. | 2 CFR 200.309, 200.308 |
| Allowable cost | A cost has to be necessary, reasonable, allocable and consistent with the award's terms. Code can't judge this, so it's the Allowable question the agent answers. | 2 CFR 200.403 |
| Allocable cost, shared costs | A cost shared across grants has to be split on a documented basis, for example "56 of 96 samples". | 2 CFR 200.405 |
| Budget lines and rebudgeting | Some moves between budget lines need prior approval from the funder. | 2 CFR 200.308, the award letter |
| Participant support costs | Costs for participants, such as stipends, travel and registration, not for project staff. Moving these funds to other uses needs prior approval. | 2 CFR 200.1, 200.456 |
| Prior approval | The approval has to come from the right person, through the right channel, before the cost. | The award letter, NSF policy |
| Supporting documentation | Every charge has to be backed by source documentation, and the documentation should show the university's review or approval, ideally before the cost. | 2 CFR 200.302(b)(3), NSF's Proposal and Award Policies and Procedures Guide (PAPPG) Chapter VII.A.1 |
| Cost transfer | Moving a charge off a grant needs a written explanation. Berkeley asks why the move is needed, why the wrong fund was charged, and how the expense relates to the project. | University policy, for example Berkeley's cost transfer procedures |
| Closeout | Reports to NSF and the final payment amount are due 120 days after the end date. Universities set earlier internal deadlines (see [Closeout](#closeout)). | 2 CFR 200.344, NSF PAPPG Chapters VII.D.4 and VIII.E |
| Record retention | Records, including the supporting documents for every charge, are kept for 3 years. NSF counts from financial closeout. 2 CFR 200.334 counts from the final financial report. Some universities keep them longer, for example Stanford keeps 4 years. | 2 CFR 200.334, NSF PAPPG Chapter VII.E |

## Evidence a charge needs

Verify this section against Berkeley's own documentation requirements before writing the default checklists. It comes from UC Davis's list (see [What the university keeps](#what-the-university-keeps)) and general practice.

- **Bills.** An invoice asks to be paid, and a receipt shows it was paid. For a university purchase the invoice is usually enough, because the ledger line itself shows the payment. FundTrail treats invoices, receipts and card slips as one kind of evidence. "Bill" is the working name.
- **Many charges never have a bill:**

| Kind of charge | Usual evidence |
|---|---|
| Salaries and wages | Appointment letter, salary rate, certified effort reports. One effort report often covers several months, and it's signed after the period ends. |
| Fringe benefits | The benefit rate, applied to the salary |
| Participant stipends | The participant list and payment records |
| Travel per diem | The trip's dates and the per diem rate, instead of receipts |
| Internal recharges, such as a core facility | The facility's usage statement |
| Subaward payments | The partner institution's invoice |
| Reversals and cost transfers | The line being corrected and a written explanation |

- **These kinds overlap,** so FundTrail doesn't sort charges into fixed groups. One trip can be part airfare, with a receipt, and part per diem, at a rate. Each charge gets its own evidence checklist instead (see [product.md](product.md#the-evidence-checklist)).
- **How soon evidence has to be on file.** We found no federal rule that sets a number of days. Universities set their own paperwork deadlines. FundTrail's 60 days is its own choice.

## Approvals

- **Code decides an approver's role** by matching the sender against the people named in the award letter. The agent never decides who someone is.
- **Example: the approval channel.** An email approval reaches Needs a human at best, even one from the real Program Officer. Only a Research.gov record reaches Evidence complete. The exact NSF rule gets confirmed before it's coded.
- **Example: self-approval.** A professor approving their own charge is not a prior approval.

## Closeout

Checked on Nov 8, 2026 against the sources at the end of this file. Where FundTrail fits in this process is in [product.md](product.md#closeout).

### What NSF receives

NSF never sees individual charges or the evidence behind them. It gets one number and two research reports, all due 120 days after the end date:

| Item | Where | Who |
|---|---|---|
| The final payment amount for the award. NSF doesn't require a separate final financial report. | ACM$ (Award Cash Management Service), NSF's payment system | The university's central accounting office |
| Final Annual Project Report. Filing it certifies that the statements are true and that the work is done. | Research.gov | The principal investigator (PI) |
| Project Outcomes Report, a short public summary | Research.gov, posted publicly by NSF | The PI |
| Final cost share notification, only if the award required cost sharing | Research.gov | The university's authorized official |

NSF closes the award financially 120 days after the end date. It closes the award administratively after that, usually automatically. NSF doesn't require a final invention statement. If costs change later, the university files an adjustment in ACM$.

### What the university does

Every university reviews every charge before the final amount goes to NSF. The steps are similar everywhere, but the names, forms, systems and deadlines differ. Berkeley's process, from its Controller's Office:

1. **90, 60 and 30 days before the end date:** Contracts and Grants Accounting (CGA) sends a Notice of Expiration to the PI, the research administrator and the department manager. They review the charges to make sure they're complete, accurate and allowable.
2. **End date:** no new spending.
3. **Adjustment period, until the books close two months after the end date:** the research administrator checks that every charge belongs to the award, fixes errors with cost transfers, moves unallowable charges off the grant, and finishes payroll corrections.
4. **Award Closeout Certification, due at the close of the 2nd month:** the research administrator files a form in BFS, Berkeley's financial system, with a CalAnswers ledger report showing every cost is recorded, plus supporting documents for accruals and payroll transfers. Submitting it indicates the PI approves the final expenses. The research administrator's supervisor reviews it and approves or denies it.
5. **By day 90:** CGA reviews the charges and files the final financial report. For NSF, that's the amount entered in ACM$.
6. **By day 120:** anything missed needs a Closeout Exception Request. Overspending is swept to the department.

Berkeley's cost criteria: each charge must be incurred in the budget period, allowable, necessary and reasonable, allocable, consistently treated, and adequately documented. UC Davis's closeout checklist asks nearly the same questions.

### What the university keeps

The supporting documents for every charge, kept for the retention period and handed to auditors on request. Nothing gathers them in one place. They sit in the ledger, payroll, purchasing and effort systems, and with the department, including emails. UC Davis lists what it keeps for each type of expense:

| Expense | Documents kept |
|---|---|
| Salaries | Appointment letter, salary rate, the PI's approval of payroll charges, certified effort reports |
| Equipment | Requisition, bids, justification and approval to buy, invoice, proof of receipt, inventory record |
| Supplies | Invoice or receipt, and how a shared cost was split |
| Travel | Expense report with the trip's purpose and receipts, sponsor approval if required |
| Subawards | Invoices with the PI's approval to pay, the subaward agreement, progress reports |
| Cost transfers | The PI's request, the transfer document with approvals, a written explanation |

### Audits

- **Every year,** an outside firm audits a sample of the university's federal awards under 2 CFR 200, Subpart F, and asks departments for the documents behind specific transactions.
- **At any time,** the NSF Office of Inspector General can audit. For example, its San Francisco State audit sampled 50 transactions and asked for the documentation behind each one.
- Auditors sort problem costs into **unsupported** (the proof is missing) and **unallowable** (the proof shows a broken rule). NSF can recover money for either, even after closeout.

## Glossary

| Term | Meaning |
|---|---|
| Award letter, award notice | The document that creates the grant and states its terms |
| Principal Investigator (PI) | The professor who leads the project |
| Program Officer (PO) | The NSF person responsible for the program, who approves scientific and budget changes |
| Grants Officer | The NSF person with authority over the award's financial and legal terms |
| Research.gov | NSF's system for grant requests and approvals |
| Sponsored programs office | The university office that manages grants. Names differ: at Berkeley, the Sponsored Projects Office handles awards and Contracts and Grants Accounting (CGA) handles the money. |
| Research administrator | The department staff member who manages a grant's charges and prepares its closeout. At Berkeley, this person files the Award Closeout Certification. Our user, called "the accountant" in these docs, can be in this role or in the sponsored programs office. |
| Award Closeout Certification | Berkeley's closeout form, filed with a ledger report and supporting documents two months after the end date and approved by the preparer's supervisor |
| ACM$ | Award Cash Management Service, NSF's payment system. The final payment amount entered here is NSF's final financial report. |
| Project Outcomes Report | The PI's short public summary of a grant's results, filed in Research.gov at closeout |
| Evidence report | FundTrail's PDF per grant: the proof behind every charge, attached to the university's closeout step |
| General ledger | The accounting system's record of every charge to every grant |
| Ledger account | The expense category the university's accounting system gives each ledger line, such as Materials and Supplies. Names differ between universities. |
| Bill | FundTrail's working name for any document that bills for a cost: an invoice, a receipt or a card slip |
| Effort report | A signed statement of how a person's time was split across projects. It backs salary charges. |
| Per diem | A daily allowance for meals and lodging at a set rate, paid instead of itemized receipts |
| Fringe benefits | Benefit costs such as health insurance and retirement, usually charged as a rate on salary |
| Ledger line | One entry in the ledger, with an ID, transaction date, posting date and amount |
| Transaction date, posting date | When the cost happened, and when the ledger recorded it |
| Reversal, cost transfer | New ledger lines that undo or move an earlier charge. The ledger never edits a line. |
| Direct costs | Costs charged straight to the project. Indirect costs (overhead) are out of scope for now. |
| Cost sharing, in-kind | Contributions the university or a third party makes to the project. In-kind cost sharing is out of scope for now. |
| Closeout | Finishing a grant after its end date: the university's review of final charges, the final amount and reports to the funder, and the records kept for audits |

## Not decided yet

| Item | Who settles it |
|---|---|
| The exact list of NSF rules for the hackathon build, and which are coded and which become questions for the agent | product |
| The exact approval-channel rule, verified against NSF's pages | product |
| Which universities' closeout steps to support after Berkeley | product |
| The default evidence checklist for each of Berkeley's ledger accounts, verified against Berkeley's documentation requirements | product, then W2 |
| How each rule is coded, and how rules are organized per funder | builder (W2) |

## Sources

- [NSF PAPPG 24-1, Chapter VII: Award Administration](https://www.nsf.gov/policies/pappg/24-1/ch-7-award-administration)
- [NSF PAPPG 24-1, Chapter VIII: Financial Requirements and Payments](https://www.nsf.gov/policies/pappg/24-1/ch-8-financial-requirements-payments)
- [NSF PAPPG 24-1, Chapter XI: Other Post Award Requirements](https://www.nsf.gov/policies/pappg/24-1/ch-11-other-post-award-requirements)
- [2 CFR 200.302: Financial management](https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-D/section-200.302)
- [2 CFR 200.334: Record retention](https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-D/section-200.334)
- [2 CFR 200.344: Closeout](https://www.law.cornell.edu/cfr/text/2/200.344)
- [Berkeley CGA: Award Closeout](https://controller.berkeley.edu/cga/award-closeout)
- [Berkeley CGA: Certifying an Award is Ready to Close](https://controller.berkeley.edu/cga/award-closeout/certifying-award-ready-close)
- [Berkeley CGA: Completing the Closeout Certification Form (PDF)](https://controller.berkeley.edu/sites/default/files/completingcloseoutcertficationform.pdf)
- [Berkeley CGA: Cost Transfer Procedures](https://controller.berkeley.edu/cga/award-management/cost-transfer-procedures)
- [UC Davis: Documentation Required to Support Charges to Sponsored Projects](https://afs.ucdavis.edu/finance/contracts-grants-accounting/policies/doc-req/sponsored)
- [UC Davis: Closeout Checklist (PDF)](https://research.ucdavis.edu/wp-content/uploads/AwardCloseoutChecklist.pdf)
- [Stanford: Project Closeout](https://ora.stanford.edu/resources/sponsored-projects-maintenance/project-closeout)
- [Harvard FAS: Audits](https://research.fas.harvard.edu/audits)
- [NSF OIG audit of San Francisco State University (2022)](https://www.oversight.gov/sites/default/files/oig-reports/NSF/22-1-007-San-Francisco-State-University.pdf)
