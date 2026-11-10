# Domain

What the checks need to know about NSF (National Science Foundation) grants. **Verify every rule here against NSF's own pages and the Electronic Code of Federal Regulations (eCFR) before coding it.** The section numbers below are pointers to check, not settled facts. The rules the agent applies are checked against their sources and quoted in the NSF rulebook, [backend/app/agent/rulebooks/nsf.md](../backend/app/agent/rulebooks/nsf.md). Where this doc and the rulebook differ, the rulebook holds.

## The rules

- **Two layers of rules.** NSF's own terms (the award's general conditions, and NSF's proposal and award policies) sit on top of the federal Uniform Guidance, 2 CFR 200 (Title 2 of the Code of Federal Regulations, Part 200). Both are shared by every grant. The clear-cut rules are written into code once. The ones that take judgment, such as whether a cost is necessary and reasonable, become questions the agent answers (see [architecture.md](architecture.md#trust-rules)). Which rules go where is in [What code checks, and what goes to the agent](#what-code-checks-and-what-goes-to-the-agent).
- **Which NSF conditions govern an award.** NSF's [page on award terms and conditions](https://www.nsf.gov/awards/terms-conditions) says its Grant General Conditions (GC-1) apply to all recipients of NSF grants issued on or after October 1, 2024, and it names institutions of higher education among them. A recipient of an award issued before that date follows the terms and conditions issued at the time of the award. For a university, those were the Research Terms and Conditions plus NSF's Agency Specific Requirements. The award notice itself states which conditions govern, and their date. For the rules FundTrail uses, the two sets differ only in citation, not in substance: pre-award costs within 90 days, the first extension with 10 days' notice, moving money between budget categories, participant support needing the Program Officer's written approval, requests through Research.gov, and U.S.-flag carriers.
- **The award letter adds grant-specific terms:** the period of performance, the budget and its lines, the people and their roles, any special approval rules, and anything else it says that those don't hold, such as a principal investigator going on leave. What a real one contains is in [What an NSF award notice contains](#what-an-nsf-award-notice-contains).
- **Amendments change the terms,** for example an extension notice. A check uses the terms in force, based on each document's own date.
- **A program solicitation can hold terms too,** such as a cap on a stipend. That example comes from one audit finding, which the university disputes and NSF hasn't resolved. When one is added to a grant as a source, its terms are read like the award letter's.
- **The university's own policies** reach FundTrail only through the default evidence checklists for now (see [Default checklists by account group](#default-checklists-by-account-group)).
- For now: NSF only, direct costs only. Rules are organized per funder so more funders can be added later.

## Concepts the checks use

| Concept | What it means for a check | Pointer to verify |
|---|---|---|
| Period of performance | A cost has to be incurred between the start and end dates, with the exceptions in [The cost's date](#the-costs-date). An extension moves the end date. | 2 CFR 200.309, 200.308, GC-1 Term and Condition Nos. 5 and 6 |
| Allowable cost | A cost has to be necessary, reasonable, allocable and consistent with the award's terms. Code can't judge this, so it's the Allowable question the agent answers. | 2 CFR 200.403 |
| Allocable cost, shared costs | A cost shared across grants has to be split on a documented basis, for example "56 of 96 samples". | 2 CFR 200.405 |
| Budget lines and rebudgeting | The university may move money between budget categories, so going over one line isn't a violation by itself. The total can't exceed the award. Moving money out of participant support needs NSF's approval. | 2 CFR 200.308, NSF's Prior Approval Matrix, the award letter |
| Participant support costs | Costs for participants or trainees, such as stipends, travel and registration. The policy guide adds "but not employees", and project staff aren't participants either. Speakers and trainers generally aren't participants. Moving these funds to other uses needs prior approval. | 2 CFR 200.1, 200.456, PAPPG Chapter II.D.2.f(v) |
| Prior approval | The approval has to come from the right person, through the right channel, before the cost. NSF has a standing list of what needs its approval (see [Approvals](#approvals)), and the award letter can add to it. | GC-1 Term and Condition No. 2, NSF's Prior Approval Matrix, the award letter |
| Supporting documentation | Every charge has to be backed by source documentation, and the documentation should show the university's review or approval, ideally before the cost. | 2 CFR 200.302(b)(3), NSF's Proposal and Award Policies and Procedures Guide (PAPPG) Chapter VII.A.1 |
| Cost transfer | Moving a charge off a grant needs a written explanation. Berkeley asks why the move is needed, why the wrong fund was charged, and how the expense relates to the project. NSF sets no time limit. The 90-day figure people cite comes from the National Institutes of Health (NIH) and from university policies. Berkeley's own limit is 120 days after the close of the month the charge posted. | University policy, for example Berkeley's cost transfer procedures |
| Closeout | Reports to NSF and the final payment amount are due 120 days after the end date. Universities set earlier internal deadlines (see [Closeout](#closeout)). | 2 CFR 200.344, NSF PAPPG Chapters VII.D.4 and VIII.E |
| Record retention | Records, including the supporting documents for every charge, are kept for 3 years. NSF counts from financial closeout. 2 CFR 200.334 counts from the final financial report. Some universities keep them longer, for example Stanford keeps 4 years. | 2 CFR 200.334, NSF PAPPG Chapter VII.E |

## What code checks, and what goes to the agent

The decision is [0015](decisions/0015-six-code-checks-and-the-agents-rulebook.md). The six checks themselves are listed in [product.md](product.md#what-code-checks). This section holds the NSF rules behind them.

**How far these were checked.** Checked for the rulebook on Nov 10, 2026, against 2 CFR 200 as of Nov 6, 2026, NSF's Grant General Conditions (GC-1, the edition dated July 31, 2026), and NSF's policy guide (PAPPG 24-1) with its Supplements 1 and 2. GC-1 numbers its parts "Term and Condition No.". The rulebook's header lists what is still unread, in short:

- 2 CFR 200 Subpart E: about 30 sections, most of 200.430, and parts of a few more. Every section from 200.420 to 200.476 was searched for "unallowable" and "not allowable", and each hit was read.
- PAPPG 24-1: every chapter except Chapter X and Chapter II.D.2.f(v) and (xiii), including Chapter VI.D.3.c on further extensions. Of Supplement 1, only its list of changes and items 4 and 13. Supplement 2 was read in full.
- GC-1 beyond Term and Condition Nos. 1 to 12.
- NSF's Prior Approval Matrix, which the standing approval list below rests on, and the Research Terms and Conditions for awards made before October 1, 2024.

Spot-check a rule against its source before coding it or adding it to the rulebook.

### The cost's date

The date check follows NSF's four zones:

| When the cost is dated | What the check says | Pointer to verify |
|---|---|---|
| During the grant | Fine | 2 CFR 200.309 |
| Up to 90 days before the start date | Allowed. The university may approve these costs on its own, at its own risk, documented under its own policy. The charge's checklist asks for the university's own pre-award approval, so a missing one is missing evidence, not a conflict. | GC-1 Term and Condition No. 5 |
| More than 90 days before the start date | Possible conflict, unless NSF's approval is on file: an approval linked to the charge that the agent's Covers answer supports | GC-1 Term and Condition No. 5 |
| After the end date | Possible conflict. A cost after the end date is allowed only to pay for a commitment made on or before the end date, so the agent can dispute the check with proof that the order was placed by then. | PAPPG Chapter X.A.2, under the heading "Post-End Date Costs" |

- **Extensions.** The university can extend the grant once on its own, by up to 12 months, by notifying NSF through Research.gov at least 10 days before the end date (GC-1 Term and Condition No. 6). It may not extend merely to spend the remaining balance, and it can't extend an award with a zero balance. Later extensions need NSF's approval, through the procedures in PAPPG Chapter VI.D.3.c, which hasn't been read. Code doesn't check any of this. A notice filed less than 10 days before the end date, with no NSF approval on file, is the agent's to flag. The agent also flags a notice that extends merely to spend the balance or extends an award with a zero balance.
- 2 CFR 200.403(h) states its date rule in terms of the budget period, and lets administrative closeout costs be incurred until the final report is due.

### Budget lines

The budget check runs on the grant, not on charges. NSF lets the university move money between budget categories, so an overspent budget line isn't a problem. FundTrail shows it as a note on the grant. Spending over the award's limit is a problem on the grant itself. The limit is the "Total Amount Obligated to Date" on the latest confirmed notice, and spending is the sum of the charges on the grant's ledger. Moving money out of participant support is different: it needs NSF's approval, and the approvals check covers it.

### Rules that go to the agent

Every rule of the form "this kind of cost isn't allowed, or is allowed only under a condition" goes to the agent, not to code. The agent's rulebook carries them, each with its source, and a rule goes into the rulebook only after it's checked against that source. Each rule is stated here in a sentence. The exact text, quotes and links are in the [rulebook](../backend/app/agent/rulebooks/nsf.md).

| Rule | Pointer to verify |
|---|---|
| Airfare above the basic least expensive unrestricted class isn't allowed. A higher class is allowed only when the cheaper one would need circuitous routing, travel at unreasonable hours or excessively long travel, would add costs that offset the savings, or wouldn't meet the traveler's medical needs, and the reason is justified and documented. GC-1 also makes the difference above economy airfare unallowable. | 2 CFR 200.475(e), GC-1 Term and Condition No. 10.a.2 |
| International flights use a U.S.-flag carrier, or a code-share with one, when one is available. The exceptions are GC-1's list: an Open Skies agreement, involuntary rerouting, set limits on added travel time and connections, and short trips a U.S. carrier would at least double. Lower cost and convenience aren't exceptions. | GC-1 Term and Condition No. 10.c and 10.d |
| No travel, meal or hotel costs for employees who aren't travelling | PAPPG Chapter X.C.3 |
| No meals or coffee breaks at internal meetings of the university or its labs, departments and centers. The policy guide words this for proposals, so it binds a grant only when the award notice restates it as a condition. | PAPPG Chapter II.D.2.f(xiii)(b) |
| Publication fees only for work the award supported, and only when the journal charges every item it publishes the same way. Costs not incurred during the period of performance can be charged during closeout, to the final budget period. | 2 CFR 200.461(b), PAPPG 24-1 Supplement 2 |
| A cost after the end date is allowed only to pay a valid commitment made on or before the end date. Equipment or supplies ordered after the end date generally can't be charged. | PAPPG Chapter X.A.2, under the heading "Post-End Date Costs" |
| Consultants are people who aren't officers or employees of the university, paid at a rate that's reasonable and can be justified | GC-1 Term and Condition No. 7, 2 CFR 200.459(a) |
| Administrative and clerical salaries are charged directly only when all three hold: the services are integral to the award, the people can be specifically identified with it, and the costs aren't also recovered as indirect costs | 2 CFR 200.413(c) |
| Short-term visas can be charged. Long-term immigration visas can't. | 2 CFR 200.463(d) |

**Kinds of cost that aren't allowed.** Alcohol, promotional items, entertainment, donations, fines, fundraising, lobbying, goods for personal use, interest, country, social and dining club memberships, alumni activities, student activities, commencement and convocation, taxes the university could have been exempted from, renting property from people or entities affiliated with the university, costs moved from another award that ran over its funding, banned telecommunications equipment, and covered foreign drones. Pointers: 2 CFR 200 Subpart E (200.421 to 200.471), 2 CFR 200.216 for telecommunications, and PAPPG 24-1 Supplement 1, item 4, for drones, which aren't in 2 CFR 200.

- Some have a narrow exception in the source: entertainment with a specific programmatic purpose included in the award, fines that come from complying with the award or have NSF's prior written approval, fundraising for the program's objectives with NSF's prior written approval, interest to finance capital assets, and student activities the award expressly authorizes.
- Membership in business, technical, professional, civic or community organizations is allowed. Membership in a lobbying organization falls under lobbying.
- Gifts, t-shirts and memorabilia for participants aren't promotional items. They're participant support and need NSF's prior written approval (see [Approvals](#approvals)).

Four more rules go to the agent because they need its reading of the documents. Each is a flag, not contradicts, except where the rule names a comparison:

- **Purchases close to the end date.** NSF's policy guide says the university "typically should not" buy "equipment, computing devices, or restocking of materials and supplies" to use up funds when little or no time is left to use them (PAPPG Chapter X.A.2, "Post-End Date Costs"). It names no number of days and doesn't word it as unallowable, so code has no day count. The agent flags the charge.
- **Participant support paid to project staff.** The definition of a participant excludes consultants, project personnel and university staff (2 CFR 200.1). The policy guide says participants or trainees "but not employees", and that speakers and trainers generally aren't participants (PAPPG Chapter II.D.2.f(v)). The agent compares who was paid with the people named on the grant, and flags a payment to a speaker or trainer.
- **A late extension notice,** as above.
- **Fringe benefits on stipends.** This comes from one NSF Office of Inspector General audit finding, not a written rule. It rests on that university's own rate agreement, which named salaries and wages as the fringe base, and the university disputed part of it. So the agent flags a fringe charge on a stipend for the accountant, and only when a rate term on the grant states its base. It isn't a kind of cost that isn't allowed.

Two side notes from the same reading. The two-month limit on senior salary is a proposal-budget rule and doesn't bind after the award. The federal equipment threshold is $10,000 in 2 CFR 200.1, and the policy guide's Supplement 1, item 13, raised its own figure from $5,000 to $10,000 for awards made on or after December 8, 2025.

## Evidence a charge needs

The table of usual evidence below comes from UC Davis's list (see [What the university keeps](#what-the-university-keeps)) and general practice. The default checklists after it say which parts were checked on Berkeley's own pages.

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
- **How soon evidence has to be on file.** We found no federal rule that sets a number of days. Every cost has to be adequately documented, and salaries need records that reflect the work performed. Universities set their own paperwork deadlines. FundTrail's 60 days is its own choice.

### Default checklists by account group

Verify each row in this section against Berkeley's own page before coding it.

The decision is [0016](decisions/0016-default-checklists-by-account-group.md). A default checklist hangs on a group of ledger accounts, not on each account. At Berkeley an account is a 5-digit code, and expense accounts run from 50000 to 59999. Its public account list has about 359 expense accounts, which fall into about a dozen groups. Code keeps a small table that says which account codes belong to which group.

A default holds only what every charge in the group needs. The agent adds the rest, such as a flight's itinerary when the bill doesn't show the airline and fare class. Differences inside a group, such as a flight and a hotel, are left to the agent's own items. An account in no group gets no default.

An account group only sets the default. It isn't a fixed kind of charge: the agent still adds what the charge needs, and can suggest removing a default that doesn't fit.

This list is a starting point:

| Group | Berkeley accounts | Default items |
|---|---|---|
| Salaries | 50xxx, 51xxx | Appointment letter. Certified effort report covering the month. |
| Benefits | 53xxx | Benefit rate |
| Tuition and fee remission | 538xx, 5742x | The student's appointment letter |
| Travel | 5721x, 5722x | Expense report. Bills that add up to the charge. |
| Supplies | 550xx, 553xx | A bill that adds up to the charge |
| Equipment | 542xx | A bill that adds up to the charge |
| Participant support | 5671x | Participant list. Payment record. |
| Subawards | 5781x | The partner's invoice. The professor's approval to pay. The subaward agreement. |
| Consultants and services | 5672x | A bill that adds up to the charge. The agreement or rate. |
| Printing | 564xx | A bill that adds up to the charge |
| Internal recharges | 590xx | The facility's usage statement |

- **Overlapping ranges.** Where two account ranges overlap, the more specific one wins. 538xx, fee remission, is in tuition and fee remission, not in benefits.
- **Reversals and cost transfers aren't an account group.** A line that corrects another gets two default items whatever its account, in place of its account group's default: the line it corrects, and a written justification. The line's NSF category still comes from its account's group.
- **Where each default comes from.** Checked on Berkeley's pages: the effort report's timing, receipts for travel, the participant list, and the professor's approval on a subaward invoice. From general practice, not a Berkeley page: benefits, tuition, supplies, equipment, consultants, printing and recharges.
- **Effort reports.** Berkeley certifies effort twice a year, for January to June and for July to December, within 120 days of the period's end. So the report covering January to June is expected by late October, and the checklist item carries that date. Berkeley is replacing its Effort Reporting System with a new one, Employee Compensation Compliance, whose first certification is in March 2027. Re-check the timing before building.
- **Budget lines.** A budget line in an NSF award is one of NSF's standard budget categories, or a sub-line of one (see [What an NSF award notice contains](#what-an-nsf-award-notice-contains)). So the budget line needs no category of its own, and only the ledger's account is translated. Each account group carries its NSF category, in the same table as its default list, and code compares that with the budget line the agent picked. The category matches the assigned line when it is that line, or when one contains the other: Other Direct Costs contains its six sub-lines. Each line and sub-line the notice prints is a budget line term, named as NSF prints it. Example: a laptop filed on 56712 Participant Support-Stipends, which the agent assigns to Materials and Supplies, goes to Needs a human as a likely misfiling.

**What Berkeley's pages say to keep.** These came from Berkeley's public pages on Nov 10, 2026. Pages behind a login, the University of California accounting manual and its travel policy weren't read.

- Payroll: effort is certified twice a year, within 120 days of the period's end. A new system is replacing the old one, with its first certification in March 2027.
- Travel: receipts for registration, airfare, lodging and car rental at any amount, and an expense report within 45 days of the trip.
- Procurement card: pre-approval for every purchase, itemized details, and proof of receipt.
- Subawards: an invoice detailed enough to show the costs are allowable, with the principal investigator's approval.
- Participant support: tracked separately, and a participant may not be a Berkeley employee.
- Consultants: generally not campus employees.
- Cost transfers: within 120 days of the close of the month the charge posted, with a written answer to why the correct fund wasn't charged. Salary transfers need an approval specific to the transfer.
- Recharges: records of the amount and the basis of billing.
- Thresholds: equipment at $5,000 or more, and the first $25,000 of a subaward on its own account. Whether Berkeley has moved to the federal $10,000 and $50,000 figures isn't verified.

Only the documents on the default checklists come into FundTrail for now, such as a lodging receipt at any amount. Berkeley's other rules, such as the expense report within 45 days, are out for now.

## Approvals

- **Code decides an approver's role** by matching the sender against the people named in the award letter. The agent never decides who someone is. A real award notice names NSF's officials with their email addresses, which supports matching by address.
- **NSF's standing list.** Some things need NSF's approval on every NSF grant, so FundTrail carries the list itself, and each award letter adds what's specific to its grant. Among the things a charge can show, the list is:
  - moving money out of participant support
  - a payment to a partner institution (a subaward) that wasn't in the proposal
  - faculty salary above the base salary
  - dependents' travel
  - buildings and land
  - extra participant items, such as gifts and t-shirts

  Equipment and foreign travel don't need NSF's approval. When the agent recognizes one of these on a charge, "NSF approval" goes on the charge's checklist, and a missing one is flagged right away.
- **Who approves, and how.** Requests "must be submitted via Research.gov" (GC-1 Term and Condition No. 2.b). The university's authorized representative submits them (NSF's policy guide, Chapter VII). The Program Officer approves moving money out of participant support. A Grants Officer approves most other things.
- **The approval channel.** An approval from the wrong person, through the wrong channel or after the cost is Possible conflict. One case is held back: an approval from the right NSF person that came by email, outside Research.gov, stays in Needs a human, because no source we read says whether it counts (see [Not decided yet](#not-decided-yet)). Only a Research.gov record reaches Evidence complete.
- **Example: self-approval.** A professor approving their own charge is not a prior approval.

## What an NSF award notice contains

Checked on Nov 10, 2026 against real award notices: one new-project notice to a community college, read end to end, four more notices, and NSF's own samples. No new-project notice to a research university was read, only amendments to one. These docs say "award letter" for the notice that creates the grant.

**What a notice holds, in order:**

1. The recipient.
2. Amendment information: its type, date and number, and a free-text "Amendment Description".
3. Award information: the award number, the instrument, the award date, the period of performance's start and end dates, the project title and the funding opportunity.
4. Funding information: the amount obligated by this amendment, the total intended award amount, cost share, the total obligated to date, and the expenditure limitation.
5. Project personnel: the principal investigator (PI) and any co-PIs, each with an email address and organization.
6. NSF contacts: the Managing Grants Official, the Awarding Official and the Managing Program Officer, each with an email address.
7. The general terms and conditions that govern, with their date.
8. The budget.

**What that means for FundTrail:**

- **The budget is printed in the notice, in NSF's standard categories,** in one column, not split by year. The policy guide's Chapter II names the same lines:

  | Line | Category | Sub-lines |
  |---|---|---|
  | A | Senior Personnel | |
  | B | Other Personnel | Several, by kind of staff |
  | C | Fringe Benefits | |
  | D | Equipment | |
  | E | Travel | Domestic, International |
  | F | Participant Support Costs | Stipends, Travel, Subsistence, Other |
  | G | Other Direct Costs | Materials and Supplies, Publication Costs, Consultant Services, Computer Services, Subawards, Other |
  | H | Total Direct Costs | |
  | I | Indirect Costs | |
  | J | Total | |
  | K | Fees | |
  | L | Total Amount of Request | |
  | M | Cost Sharing | |

  So Materials and Supplies is a sub-line inside Other Direct Costs, not a category beside it.
- **The notice names its solicitation,** as the funding opportunity's number and name, and sometimes in a sentence saying the award is made under that solicitation's provisions. An unsolicited award shows the policy guide's number there.
- **Special conditions are free text inside the Amendment Description.** Seen in one notice: participant support funds "may not be diverted by the awardee to other categories of expense without the prior written approval of the cognizant NSF Program Officer", entertainment and meals are unallowable except working meals at a conference, the proposed subaward is authorized, human-subjects approval is the university's responsibility, and a possible cap on indirect costs. This fits reading approval rules and other terms from the letter.
- **Every notice is an amendment,** with a number and a date. Amendment 000 is the new project. Each states its "Amendment Type". Seen: New Project, Increment, Frwd Funded, No Cost Extensions, and Other Admin No Fund Actions. Amendments end with "Except as modified by this amendment, the award conditions remain unchanged."
- **A no-cost extension** has only a few sections and states the change as dates, in the form "extend the end date from" one date "to" another.
- **A funding amendment,** such as an increment on a continuing grant or a supplement, says its purpose is to add funding. It prints a budget for that increment only, beside "Amount Obligated by this Amendment", "Total Intended Award Amount" and "Total Amount Obligated to Date" for the whole award. So a grant's budget can be the sum of several notices.

How FundTrail reads these is in [product.md](product.md#grants) and decision [0017](decisions/0017-grant-terms-from-award-notices.md).

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
| Award letter, award notice | The document that creates the grant and states its terms. NSF calls it an award notice. |
| Amendment | A later notice that changes the award: an extension, added funding, or an administrative change. NSF numbers them, and 000 is the new project. |
| Program solicitation | NSF's call for proposals for a program. It can hold terms of its own, and the award notice names it. |
| Grant General Conditions (GC-1) | NSF's standard conditions for grants. They apply to every NSF grant issued on or after October 1, 2024. |
| Research Terms and Conditions | The shared federal conditions that, with NSF's Agency Specific Requirements, governed NSF awards to universities issued before October 1, 2024 |
| Prior Approval Matrix | NSF's table of what needs its approval and who gives it |
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
| Ledger account | The expense category the university's accounting system gives each ledger line, such as Materials and Supplies. Names differ between universities. At Berkeley it's a 5-digit code. |
| Account group | FundTrail's grouping of ledger accounts, such as salaries or travel. Each group has one default evidence checklist and one NSF budget category. Reversals and cost transfers aren't a group. |
| Rulebook | The plain file of a funder's rules that the agent gets on every run, each rule with its source |
| Bill | FundTrail's working name for any document that bills for a cost: an invoice, a receipt, a card slip, a credit memo or a facility's usage statement |
| Effort report | A signed statement of how a person's time was split across projects. It backs salary charges. |
| Per diem | A daily allowance for meals and lodging at a set rate, paid instead of itemized receipts |
| Fringe benefits | Benefit costs such as health insurance and retirement, usually charged as a rate on salary |
| Ledger line | One entry in the ledger, with an ID, transaction date, posting date and amount |
| Transaction date, posting date | When the cost happened, and when the ledger recorded it |
| Reversal, cost transfer | New ledger lines that undo or move an earlier charge. The ledger never edits a line. Their default checklist items apply whatever the line's account. |
| Direct costs | Costs charged straight to the project. Indirect costs (overhead) are out of scope for now. |
| Cost sharing, in-kind | Contributions the university or a third party makes to the project. In-kind cost sharing is out of scope for now. |
| Closeout | Finishing a grant after its end date: the university's review of final charges, the final amount and reports to the funder, and the records kept for audits |

## Not decided yet

| Item | Who settles it |
|---|---|
| Whether a Program Officer's email, outside Research.gov, counts as approval. No source we read says either way. Until it's settled, such an approval stays in Needs a human. | product |
| The exact federal list for the rulebook, above all the kinds of cost that aren't allowed. The rulebook's header lists the sources still unread. Each rule is checked against its source before it goes in. | builder (W1), discussed with Alex before building |
| The exact table of which Berkeley account codes belong to which group, and each group's NSF budget category | builder (W2), discussed with Alex before building |
| Whether Berkeley has moved its equipment and subaward thresholds from $5,000 and $25,000 to the federal $10,000 and $50,000 | builder (W2), verified before coding |
| Berkeley's effort report timing under its new system, re-checked before building | builder (W2) |
| Berkeley's 120-day limit on cost transfers | product, discussed with reversals and cost transfers |
| Anything specific to program solicitations: a cap that adds up over several charges, such as twelve monthly payments that pass a yearly cap together, and noticing that an award letter names a solicitation that isn't on file | product, later |
| The university's own policies beyond the default checklists, such as an expense report within 45 days of a trip | later |
| Which universities' closeout steps to support after Berkeley | product |
| How each rule is coded, and how rules are organized per funder | builder (W2) |

## Sources

- [NSF: Award terms and conditions](https://www.nsf.gov/awards/terms-conditions)
- NSF Grant General Conditions (GC-1), and NSF's Prior Approval Matrix (October 1, 2024)
- NSF PAPPG 24-1, Chapter II (the budget lines) and Chapter X (allowability of costs)
- 2 CFR 200.1 and the cost principles in Subpart E: 200.403 to 200.406, 200.413, 200.421, 200.430, 200.461, 200.463 and 200.475
- The [NSF rulebook](../backend/app/agent/rulebooks/nsf.md), which links the source of each rule it holds, including NSF GC-1 (July 31, 2026), PAPPG 24-1 Supplements 1 and 2, and the 2026 audit behind the fringe benefits flag
- NSF Office of Inspector General audit reports, read in part: a 2022 summary of 18 audits, and two university audits from 2025 and 2026
- Real NSF award notices and NSF's sample notices, read on Nov 10, 2026
- Berkeley's public account list, and its pages on effort reporting, travel, subawards, participant support and cost principles
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
