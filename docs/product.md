# Product

## The problem

A university spends a research grant over several years under rules that change along the way: extensions, budget moves, approvals. When the grant ends, the university has a few months to review every charge, move off any that broke the rules, and certify that the grant is ready to close. Years later, auditors can pick any charge and ask for the proof behind it. That proof is scattered across email, shared drives, invoices and the accounting system. Today someone pieces it together by hand, after the people who remember the details have moved on.

This fits the hackathon theme, "Automate the Old Way": an old financial workflow built on spreadsheets, email chains and receipts, rebuilt with AI.

## The product

**FundTrail keeps a running evidence file for every grant.** As evidence arrives, FundTrail connects it to the charges and keeps each charge's status current. Problems show up while they can still be fixed. When the grant ends, the review the university has to do is already done, and the evidence report is ready to attach to the university's own closeout step (see [Closeout](#closeout)).

**FundTrail fits into the university's process. It doesn't replace it.** It sits beside the university's systems, reads the charges and the evidence, and hands the person doing closeout what they need at each step. It files nothing with the university or with the National Science Foundation (NSF).

**How it differs from Ramp.** Ramp's Grant Policy Agent checks a purchase when it's made. FundTrail works with evidence Ramp never sees, such as email, shared drives and amendments signed months later, and it rechecks the whole history every time something changes. We don't pitch receipt matching.

## Users and workspaces

These limits are for now. The design stays open to grow (see below).

- The only user is the person who manages a grant's money and prepares its closeout. These docs call them **the accountant**. At Berkeley, that's the department's research administrator, who prepares the Award Closeout Certification. At other universities, it can be a grant accountant in the sponsored programs office.
- Each workspace has one person. Professors and lab staff only send evidence in.
- Users sign in with Google. A workspace holds many grants.
- A new account starts with a demo workspace already loaded with grants. Users can create more workspaces.

## Grants

- To add a grant, the accountant drops in the award letter. The agent pulls out the terms as cited records: dates, budget lines, people and their roles, approval rules, and anything else the letter says that those don't hold, such as a principal investigator going on leave. The accountant confirms the terms before any check uses them. What a real NSF award letter contains is in [domain.md](domain.md#what-an-nsf-award-notice-contains).
- **Checks use only confirmed terms.** Where an older confirmed term exists, it stays in force. Where none exists, the charge is in Needs a human, with a reason such as "the grant's dates aren't confirmed yet". Checks that need no terms still run, such as the checklist and the amounts. The problem list shows the waiting terms as one item, and confirming them clears all of those charges at once.
- **The agent doesn't wait for confirmation.** It reads evidence, links it and builds checklists while the terms wait. Anything that rests on an unconfirmed term stays in Needs a human until the term is confirmed.
- **A wrong term.** The accountant rejects it and fixes it one of two ways. They type the right value, which counts as confirmed because they typed it. Or they tell the agent in the term's thread where to look, and the agent's new reading waits for confirmation like any other.
- **A term the agent missed.** Code flags a grant that has no confirmed dates or no budget, since no grant can lack those. Code can't catch anything else, because it doesn't know what the letter should contain. The accountant adds the missing term by hand or asks the agent to read the letter again. The known weak spot: when an approval rule is missed, its check never runs.
- Amendments, such as an extension notice, update the terms the same way. Until the accountant confirms an extension, the old end date stays in force, so a charge dated after it stays in Possible conflict.
- **A notice that adds money adds to the award's limit.** The limit is the "Total Amount Obligated to Date" on the latest confirmed notice. The agent reads the notice's type, the amount it adds and the running total, each with its quote. Code checks that the earlier confirmed total plus the amount added equals the notice's running total, and that no amendment number is skipped. If either fails, the grant is flagged, because a notice is missing or a number was misread. The accountant confirms the term as usual.
- **A program solicitation can be added to a grant as a source.** The agent reads its terms, and they update the grant's terms the same way, confirmed by the accountant.
- For now each grant is isolated: its evidence, links and checks don't reach other grants.
- For now, only NSF grants, and only direct costs.

## Buckets

Every charge sits in exactly one bucket.

| Bucket | Meaning |
|---|---|
| **Evidence complete** | Every check passes on verified records, every item on the charge's evidence checklist is filled, and every question about the charge is answered supports |
| **Possible conflict** | Verified evidence contradicts a rule, or an answer is contradicts |
| **Missing evidence** | Something on the charge's evidence checklist isn't on file |
| **Needs a human** | Code can't decide safely, the agent is unsure, a suggestion from the agent waits for the accountant, or the charge rests on a fact that couldn't be confirmed in its file |

When several checks fail, the charge shows the most serious bucket and lists every reason. From most to least serious: Possible conflict, Needs a human, Missing evidence.

### How a charge gets its bucket

- **Code checks the clear-cut rules.** There are six, listed under [What code checks](#what-code-checks). Five are about a charge, and one is about the grant. When terms change, code reruns instantly, with no agent call.
- **The agent decides what takes judgment.** It decides which budget line each charge belongs to, adds to each charge's checklist, and answers the questions code asks about each charge: is this cost necessary and reasonable, and is it for this project? Does this approval cover this charge? Does this unusual term change anything? The agent answers supports, contradicts or unsure, with its reasoning and quotes. Contradicts is Possible conflict, and unsure is Needs a human. The rules it applies are in the funder's rulebook, and each answer names the rule it used (see [What goes to the agent](#what-goes-to-the-agent)).
- **The agent suggests, and the accountant decides.** Anything the agent does that adds information or raises a concern takes effect right away: a comment, a link for evidence nobody has linked, a flag, a new checklist item, a first answer. Anything that would clear or weaken a problem, or change something already decided, is a suggestion that waits for the accountant: changing an answer the accountant gave, changing one of its own in a way that clears a problem, fixing a link, removing a checklist item, withdrawing its own flag, or disputing one of code's checks. There's one exception. When the agent answered unsure and new evidence settles it, its new answer counts right away. New evidence means something that arrived, or a grant term that was confirmed, after its last answer.
- **The accountant has the last word.** They answer what the agent was unsure about, can overrule any answer, accept or reject every suggestion, and can accept any reason on a charge with a note. Once they've answered a question, new evidence sends it back to them. The agent can suggest a new answer, and theirs stays in force until they decide.
- **The budget line is checked from two sides.** The ledger's own account and the agent's budget line both count. Code asks for an approval if either one says the charge needs it, and a disagreement between them goes to the accountant. A budget line in an NSF award is one of NSF's standard budget categories, or a sub-line of one, so only the ledger's account is translated: its account group carries its NSF category, and code compares that with the budget line the agent picked. The two match when they're the same line, or when one contains the other, as Other Direct Costs contains its six sub-lines. A laptop filed on a participant stipend account, which the agent assigns to Materials and Supplies, goes to Needs a human as a likely misfiling.
- **While the agent is answering again,** the charge shows its last answer marked "rechecking", or Needs a human if there's no answer yet.

### What code checks

Five checks are about a charge. One, the budget, is about the grant and never adds a reason to a charge. A charge's reasons also come from the agent's answers and flags, a suggestion waiting for the accountant, a disputed check, and a disagreement between the ledger account's category and the assigned budget line.

| # | Code checks | Example | When it fails |
|---|---|---|---|
| 1 | The cost's date is inside the grant's period in force | A charge dated Feb 20, 2026 on a grant that ended Jan 31 | Possible conflict |
| 2 | Every item on the [evidence checklist](#the-evidence-checklist) is filled, and the amounts add up | A $2,300 trip with only an $1,800 receipt | Missing evidence, or Needs a human if the amounts go over |
| 3 | A required approval is there, from the right person, through the right channel, before the cost | Stipend money moved without the Program Officer's approval | Missing evidence if there's none. Possible conflict if it's the wrong person, the wrong channel or too late. |
| 4 | The budget, on the grant: spending against each budget line and against the award's limit | $42,000 charged to a $40,000 line | An overspent line is a note on the grant. Spending over the award's limit is a problem on the grant. |
| 5 | Every value the charge rests on is confirmed | An invoice total that couldn't be found on the page | Needs a human |
| 6 | A reversal or cost transfer names the line it corrects and has a written justification | A -$400 line with no explanation | Missing evidence, reported by check 2 |

- **The cost's date** follows NSF's four zones. During the grant is fine. Up to 90 days before the start date is allowed, and the checklist asks for the university's own pre-award approval, so a missing one shows as missing evidence, not a conflict. More than 90 days before is Possible conflict unless NSF's approval is on file, which means an approval linked to the charge that the agent's Covers answer supports. After the end date is Possible conflict, and the agent can dispute it with proof that the order was placed before the end date.
- **Approvals.** FundTrail carries NSF's standing list of what needs its approval, the same for every NSF grant, and each award letter adds what's specific to that grant. The list is in [domain.md](domain.md#approvals). When the agent recognizes something on it, "NSF approval" goes on the charge's checklist, and a missing one is flagged right away. An approval that came by email stays in Needs a human, since whether it counts outside Research.gov isn't confirmed.
- **The budget.** This check runs on the grant, not on charges. NSF lets the university move money between budget lines, so an overspent line isn't a problem. The grant page shows it as a note, for example "Materials and Supplies: $42,000 of $40,000". Spending over the award's limit is a problem on the grant itself. The limit is the "Total Amount Obligated to Date" on the latest confirmed notice, and spending is the sum of the charges on the grant's ledger. Moving money out of Participant Support stays with the approvals check.
- **Reversals and cost transfers.** Check 6 has no reason of its own. The line it corrects and a written justification are the reversal's two default checklist items, and the checklist check reports them, filled or missing.

The NSF rules behind these are in [domain.md](domain.md#what-code-checks-and-what-goes-to-the-agent).

### What goes to the agent

Some rules go to the agent instead of code. They live in the agent's rulebook: one plain file per funder, starting with NSF, where each rule is a sentence or two with its source. The agent gets the whole rulebook on every run, and its answer names the rule it used, so the accountant can see why. The accountant doesn't edit the rulebook, and there's no settings screen for it.

- **Kinds of cost.** Every rule of the form "this kind of cost isn't allowed, or only under a condition" is the agent's: airfare above the least expensive unrestricted class, international flights on airlines that aren't U.S. carriers, meals and hotels for staff who aren't travelling, publication fees for unrelated work, costs that aren't allowed such as alcohol, consultants who are employees, office staff salaries charged directly, and long-term visas. The agent answers the Allowable question with the passage that shows it. A documented exception on file, such as a medical reason for a higher fare, turns the answer to supports. The agent catches only what a document shows, so the checklist has to ask for the document: through the default where every charge in the group needs it, and through the agent's own item otherwise. A flight's itinerary is the agent's item, added when the bill doesn't show the airline and fare class.
- **Purchases close to the end date.** NSF names no number of days, so code has no day count. When equipment, a computing device or a restock of supplies is bought with little time left to use it, the agent flags the charge, which sends it to Needs a human. It's a flag and not contradicts, because NSF's wording is "typically should not" and only the professor knows whether the item was used. The accountant accepts it with a note or moves it off the grant. Small supplies used right away aren't flagged. Example: a $3,800 laptop bought 11 days before the end date is flagged, and $180 of pipette tips with experiments still running isn't.
- **Participant support paid to project staff.** The agent compares who was paid with the people named on the grant, because names are written differently from page to page. A match is contradicts, citing the line on the participant list and the line in the award letter, so the charge is in Possible conflict. Someone not named on the grant is supports. The agent knows only the people the documents name, so a participant who is a university employee but appears in no document on the grant passes. Speakers and trainers generally aren't participants either, so the agent flags a payment to one unless their main purpose at the event is to learn as a participant.
- **Fringe benefits on stipends.** This rests on one audit finding and that university's own rate agreement, not a written rule. So when a rate term on the grant names salaries and wages as the base, the agent flags a fringe charge on a stipend for the accountant, and never answers contradicts.
- **A late extension notice.** The university can extend a grant once on its own by telling NSF at least 10 days before the end date, but not merely to spend the remaining balance, and not when the balance is zero. When a notice was filed later than that and no NSF approval is on file, the agent flags the notice, and the accountant sees the flag when confirming the new end date. The agent also flags a notice that extends merely to spend the balance or extends an award with a zero balance.

The university's own policies come in only through the default checklists for now, such as Berkeley's rule that lodging needs a receipt at any amount.

### The evidence checklist

Every charge has a checklist of the evidence it should have. **Bill** is our working name for any document that bills for a cost: an invoice, a receipt, a card slip, a credit memo or a facility's usage statement. For a university purchase the invoice is usually enough, because the ledger line itself shows the payment. But many charges never have a bill, such as salaries, stipends and per diem, so "the bills add up to the charge" can't be the only rule.

- **Defaults come from the ledger.** A default checklist hangs on a group of ledger accounts, such as salaries, travel or supplies, not on each account. There are about a dozen groups, starting with Berkeley's accounts, and the starting list for each is in [domain.md](domain.md#default-checklists-by-account-group). A default holds only what every charge in the group needs, and the agent adds the rest. The defaults live in the code for now, so a developer changes them, and the accountant adjusts single charges. Code works the defaults out fresh each time, so a fixed default reaches old charges too and can put them back on the list. Supplies default to a bill that adds up to the charge. Salaries default to an appointment letter and a certified effort report covering the month. A line that corrects another, a reversal or a cost transfer, defaults to the line it corrects plus a written justification, whatever its account and in place of its account group's default. An account in no group gets only the agent's items.
- **Code adds a required approval** as an item when one of the grant's approval rules applies to the charge. An approval on NSF's standing list, and the university's own pre-award approval for a cost dated up to 90 days before the start date, are items too (see [What code checks](#what-code-checks)).
- **The agent adds what this charge needs,** for example "per diem, 5 days at $100 a day" on a trip. Adding an item takes effect right away. Removing one is a suggestion that waits for the accountant.
- **The accountant can add or remove items,** and their changes take effect right away.
- **Code tracks each item** as filled or missing:
  - Bills still have to add up to the amount they cover, and the amounts on a checklist add up to the charge.
  - When an amount comes from a rate, the agent writes out the math and code re-checks it. Both numbers are cited: the quantity, such as the days of a trip, and the rate. The rate has to come from a file on the grant, such as the travel policy. A rate that isn't on file shows as a missing item like any other, and the accountant can accept it with a note.
  - An item can name a period, such as "effort report for January". Code checks that the linked document's own period covers it.
  - One document can fill items on many charges. An effort report for January to June fills six months of salary lines.
- **An item can say when it's expected.** Berkeley certifies effort twice a year, within 120 days of the period's end. So January's effort report is only signed after June ends and is expected by late October, and it isn't late before then. Each missing item shows that date.
- **A charge with an empty checklist is in Needs a human.** It can't be complete until its checklist has at least one item and every item is filled.

| Example | What happens |
|---|---|
| A $2,300 trip | The agent adds "airfare receipt, $1,800" and "per diem, 5 days at $100 a day". Code checks 5 times $100 is $500, and that $1,800 plus $500 is $2,300 |
| A $6,000 salary line for January | Defaults: appointment letter, effort report for January. The report for January to June is certified after June ends and fills all six months at once |
| A $1,500 charge posted as Participant Support Stipends, with an invoice for a laptop | The default asks for a participant list. The agent adds "invoice" and suggests removing the default. That suggestion waits, which is how the accountant sees the misfiled laptop |
| A $500 stipend paid to one guest speaker from Participant Support | The agent suggests swapping "participant list" for "honorarium letter", which waits for the accountant. Speakers generally aren't participants, so the agent flags the charge, its budget line disagrees with the ledger's account, and a missing "NSF approval" goes on the checklist. The charge stays in Needs a human |

### The problem list

The problem list is what the accountant works from. It holds charges, and records that have a problem of their own.

**Charges.**

- Possible conflict and Needs a human are on the list, unless the accountant has accepted the reason or snoozed the charge (see below).
- A charge in Missing evidence goes on the list once an item has been missing for 60 days past the date it was expected, which for most items is the charge's posting date, the day the ledger recorded it. When a grant is added partway through its life, old charges with no evidence are flagged right away, because they really are late. It also goes on the list 90 days before the grant's end date, when Berkeley sends its first Notice of Expiration, whichever comes first. Bills often arrive weeks after a charge posts, so a charge isn't a problem on day one.
- Inside that 90-day window every missing item is listed, even one that isn't due yet, as a reminder to chase it before the grant ends. Each one shows when it's expected, so a reminder doesn't read as a late item.
- A missing approval is on the list right away.
- The 60 days is our own choice. No federal rule sets it. It's the same for every grant, and there's no settings page for now.

**Records.** Some problems aren't about one charge.

| Who raises it | Problem |
|---|---|
| Code | A bill linked for more than its total |
| Code | A bill with money nobody charged, 60 days after it arrived |
| Code | A term waiting for the accountant to confirm it |
| Code | Confirmed terms that disagree |
| Code | The exact same file on the grant twice |
| The agent | Anything else, with its reasoning: a photo and a PDF of the same invoice, evidence for another grant, a file that can't be read, an extension notice filed too late |

A new kind of problem starts as the agent's flag. If it keeps coming up, code gets a check for it later.

When a bill arrives, code looks for likely matches among the bills already on the grant, and the agent compares them. It flags the newer copy as a duplicate and doesn't link it. Both files are kept, and the accountant confirms or rejects the flag. A rejected flag means the agent matches the file normally. A confirmed copy stays in the evidence list, marked as a duplicate of the original, and stays out of matching. The accountant can undo it. If the newer copy is the clearer one, the agent can suggest switching the link to it. If two charges match the same invoice, the charges are flagged too, since that may be a double payment.

**The grant itself.** Some problems are about the whole grant. Code flags a grant that has no confirmed dates or no budget, spending over the award's limit, and a funding notice whose totals don't add up or that skips an amendment number. An overspent budget line isn't a problem. It shows as a note on the grant page.

**How a problem leaves the list.** There's no resolve button, so the list can never disagree with the checks.

1. **It fixes itself.** The missing bill arrives and the agent links it. The checks pass, with no click. A problem the agent flagged doesn't clear this way: its flag stays until the accountant settles it.
2. **Snooze until a date.** The accountant expects it to fix itself: "refund coming, check Mar 1." The charge keeps its bucket, since the checks still say it isn't done, and it's hidden from the list. It comes back on that date if it isn't fixed. A new problem brings it back early. Every snooze ends when the 90-day closeout window opens. Inside the window a snooze can still be set, up to the grant's end date.
3. **Accept with a note.** It will never fix itself, and the accountant is fine with it: "duplicate, refunded in March." The charge shows as **Accepted**, with the note. Underneath it keeps the bucket the checks gave it. It comes off the list and is counted on its own in the evidence report, never as Evidence complete. The acceptance covers the problem as it stood, so the charge comes back if the facts change later. The accountant can also reopen it, which puts it back on the list.

**Reusing a note.** When accepting, the accountant chooses a one-off note or a note to reuse on similar charges. A one-off note is never reused. A reusable note applies on its own to a later charge inside three limits:

1. The same problem: the same check failing for the same reason.
2. The same ledger account and the same vendor.
3. An amount no larger than the largest the accountant has accepted under that note.

A charge that's similar but outside the limits goes on the list as usual, with the note offered: "Looks like your March note. Accept the same way?" That takes one click. A charge gets the offer when it has the same problem and the same ledger account but fails the vendor limit or the amount limit. The accountant chooses again whether it's just this charge, which leaves the amount limit alone, or this and similar charges, which raises it. Just this charge is the suggested default. A charge with no vendor, such as a salary line, only ever gets the offer.

| A note on a $400 monthly facility fee with no invoice | What happens |
|---|---|
| April's $400 fee | Accepted on its own, shown as "accepted under the accountant's note" |
| June's fee, now $420 | On the list with the offer |
| A $40,000 charge from the same facility | On the list with the offer. The accountant sees the amount before clicking. |
| The facility bills under a new vendor name | On the list with the offer |

Code does the matching, not the agent. A note excuses only its one problem, and every other check still runs. The grant page lists each reusable note with the charges it covered, and withdrawing a note brings those charges back.

### Review threads

Every charge can have a thread, and so can a record with a problem. It reads top to bottom like a chat: code's reasons, the agent's comments and suggestions, and the accountant's replies.

- **Suggestions.** Each suggestion from the agent names the change and waits for Accept or Reject.
- **Disputes.** When the agent thinks one of code's checks is wrong for a charge, it disputes it with its reasoning and a quote. While the dispute waits, the disputed reason counts as Needs a human, so the charge moves from Possible conflict to Needs a human. Accepting the dispute works like accept with a note, with the agent's reasoning as the note. Example: a January charge fails the start-date check, and the agent quotes the amendment that allows costs from January 1.
- **Asking the agent.** The accountant can ask a question in the thread. The agent answers for that charge, and a question goes ahead of the agent's queued work. If the accountant tells the agent to change something, the change comes back as a suggestion to accept, so every change is seen before it happens.
- **No nagging.** After the accountant rejects a suggestion or a dispute, the agent can't raise it again unless new evidence arrives: something that arrived, or a grant term that was confirmed, after the agent's last answer. Linking something that was already on file doesn't count.
- **What's kept.** Messages are kept with the charge but stay out of the evidence report. The report shows the decisions.

## What the user sees

The docs decide what the app does and what each screen holds. Grant's design system and clickable screens (pull request 11) are inspiration for the look and the general layout. Where they differ from the docs, the docs win. Nothing waits on the mockup.

- **Evidence cards.** Each piece of evidence gets a card listing the facts pulled from it. Every fact shows its quoted passage and page number, and whether it's confirmed or unconfirmed. A value the accountant confirmed shows "confirmed by the accountant" with the date, instead of "confirmed on the page".
- **Viewer.** Clicking a fact opens the full original in a viewer, scrolled and zoomed to the right spot.
  - **PDFs with real text, email, .docx:** the exact line is highlighted.
  - **Photos and scans:** a box is outlined around the value. There's no OCR (optical character recognition).
  - **A fact that couldn't be placed:** the viewer opens the page and shows the quote beside it, with no guessed highlight. The fact is unconfirmed, and anything that rests on it is in Needs a human until the accountant confirms the value or types the right one.
- **Confirmed values.** A value counts as confirmed in three ways: its quote was found in the file, the accountant confirmed the record it's in, or the accountant typed it. So confirming a grant term also confirms the values in it, and the accountant is never asked twice about the same value. When a record has several values that couldn't be found, the confirm screen lists each one. Only a value that a check or an answer depends on sends a charge to Needs a human. Any other unconfirmed value, such as a vendor name, just shows that way on its evidence card.
- **Correcting a value.** When the accountant types the right value, the links to that record carry over to the corrected one on their own, and the checks rerun. If the links now add up to more than the bill, the charges go to Needs a human.
- **The evidence checklist.** Each charge shows what it should have, which items are filled or missing, who added each one, and any removal still waiting.
- **The review thread.** Each charge shows its thread, with the agent's suggestions and a box for asking the agent.
- **Status history.** Every status change records what triggered it and links to it. Example: "Apr 10, 2026 · new end date confirmed · Possible conflict → Evidence complete."
- **Bills covering a charge.** Each charge lists the bills that pay for it, with how much of each it uses, for example "invoice 2050, $5,000 of $10,000". Clicking one opens the bill with the part for that charge highlighted. Approvals and explaining emails show the same way.
- **The agent's answers.** Each answer shows the question, the answer, the agent's reasoning, the rule it used and its quotes, labeled as the agent's.
- **Suggestions waiting.** Anything the agent suggests waits in the charge's thread, with its reason, until the accountant accepts or rejects it.
- **Reusable notes.** The grant page lists each reusable note: what it excuses, who wrote it and when, and every charge it covered.
- **People as sources.** Example: "Link corrected by the accountant, May 22, 2026."
- **Status text comes from code.** Every status explanation is built by code from the check and its records. The agent's reasoning appears next to it, labeled as the agent's.

### Layout ideas

These are ideas to start the screens from, not designs.

- **The review thread.** A header with the charge (ledger line, vendor, amount, date) and its bucket as a badge. Entries run top to bottom, each with a small icon and label for who wrote it: a check, the agent or the accountant. A suggestion is an outlined box inside the agent's entry, naming the change, with Accept and Reject. A reply box sits at the bottom.
- **The evidence checklist.** The charge header shows its ledger account and bucket. Below it, each item shows whether it's filled or missing, who added it (default or agent), and any removal still waiting. The agent's suggestion sits underneath with Accept and Reject.

## Closeout

What really happens at the end of a grant, and the rules behind it, are in [domain.md](domain.md#closeout).

### Where FundTrail fits: Berkeley as the first example

Every university has its own closeout step, with its own forms and deadlines, but the rules underneath are the same federal and NSF rules. FundTrail's checks follow those shared rules. Only the evidence report's format and labels follow the university. Berkeley is the first template and the demo example.

| Berkeley's step | Today | With FundTrail |
|---|---|---|
| **90 days before the end date.** Berkeley sends a Notice of Expiration and asks for a review of every charge. | Reviewed by hand | The review is already done. The accountant works a short list of problem charges. |
| **Adjustment period**, from the end date until the books close two months later. Problem charges get moved off the grant. Each move needs a written explanation. | Written by hand | FundTrail drafts each explanation from the evidence it holds (optional feature). The accountant edits it and makes the move in Berkeley's own system. |
| **Award Closeout Certification**, due at the close of the 2nd month. The accountant files a form with a ledger report and supporting documents, and their supervisor approves it. | The ledger report shows totals, not proof | The accountant also attaches FundTrail's evidence report. |
| **Final financial report**, filed by central accounting by day 90. For NSF, that's one amount entered in ACM$ (Award Cash Management Service). | Unchanged | Not involved. The amount is cleaner because problem charges are already gone. |
| **Audit, years later.** Auditors pick charges and ask for the proof. | Dug up from old email and files | Pulled from FundTrail |

### What the user gets

- **Closeout view in the app:** every expense with its bucket, its evidence and its history.
- **Evidence report: a PDF per grant.** It shows why each charge was allowed. It's attached to the university's closeout step, next to the university's own ledger report, which shows only what was spent. NSF doesn't require it and never receives it. Example layout, to decide later:
  1. Summary: the award, its dates, the total of all charges (matching the ledger report), how many charges are in each bucket, and how many the accountant accepted.
  2. A table with one row per charge: date, description, amount, bucket and a one-line reason.
  3. A section per charge: the checks, the evidence quoted from its source, the accountant's decisions, and its status history.
  4. Sign-off: who prepared it, who reviewed it, and when. At Berkeley this mirrors the preparer and the supervisor who approves the certification.
- **The report shows decisions, not conversations.** It includes every decision that changed what a charge needed or how it was judged: an accepted reason with its note (reusable notes too), an accepted dispute with the agent's reasoning, a default checklist item the accountant agreed to remove, a confirmed duplicate, and an answer the accountant changed, shown with the earlier answer. It leaves out thread messages, rejected suggestions and snoozes that have ended.
- **Drafted explanations (optional).** For each charge that has to move off the grant, a draft that answers the university's questions, such as Berkeley's: why the move is needed, why the wrong fund was charged, and how the expense relates to the project.
- **Audit export (optional).** The same records, filtered to the charges an auditor picked.

**One-line pitch:** at Berkeley, every grant ends with a Closeout Certification due two months after the end date. FundTrail has the proof for every charge ready to attach, so the review is done before the deadline and any audited charge can be answered right away.

## Demo data (examples)

Everything in this section is an example. The actual grants, people, amounts, dates and documents get decided later, when we build the seed data. All of it is synthetic.

The seeded workspace has a few NSF grants. At least two of them share a cost, so a split shows up on both.

| Example situation | What FundTrail does |
|---|---|
| A professor's conference fee is charged to participant support with no approval. Later the professor forwards their own "approved" email | **Possible conflict**, and it stays there: wrong approver, wrong channel |
| A charge is for work done after the grant's end date. Later an extension notice, signed before the old end date, turns up in Drive | **Possible conflict**, then **Evidence complete** once the accountant confirms the new end date, citing it |
| One purchase is shared with a second grant and split across both ledgers | The invoice arrives on both grants. On each grant, the agent links it to that grant's charge for its part, from the invoice's itemized lines, or from an email giving the basis, for example "56 of 96 samples", which it also links. **Evidence complete** on both. If nothing gives the basis, **Needs a human** until the accountant enters it |
| A bill arrives before its ledger line posts | It waits unlinked, then links when the line arrives |
| A new grant is built from scratch from a seed pack: award letter, ledger file, emails, invoices, a receipt photo | Create the grant, confirm its terms, upload the ledger, add the evidence, watch the statuses fill in |

## Scope

**Core: has to ship**

- Sign-in, workspaces and the seeded workspace
- The clock
- The demo situations
- Adding a grant from its award letter, including the from-scratch seed pack
- The agent and the checks
- Review threads, including asking the agent a question
- Provenance, with the viewer and highlights
- Ledger upload, the Gmail and Drive connectors, and uploads
- Text, email, PDF and photo formats
- The evidence report with sign-off, in Berkeley's terms
- The eval, with the minimum blind test
- Hosting

**Optional: if there's time**

- Chat
- Creating extra workspaces
- .docx files
- A bigger blind test
- Report styling and a zip of the originals
- Drafted explanations for charges moved off the grant
- Audit export for the charges an auditor picks
- Workspace members

**Designed to grow.** These are out for now, but nothing in the design should block them later:

- more users and roles: workspace members, and a read-only view for professors
- more funders, with rules organized per funder, starting with NSF
- more universities, each with its own evidence report template, starting with Berkeley
- grants that share evidence and links, with files that belong to the workspace instead of the grant they arrived on
- limits specific to a program solicitation, such as a yearly cap that several charges pass together
- the university's own policies beyond the default checklists, such as an expense report within 45 days of a trip
- indirect costs
- in-kind cost sharing (third-party contributions that never appear on the ledger)
- a real-time card feed, like Ramp's, that shows charges before they post
- users connecting their own Google accounts
- chat, drafted follow-up emails, and OCR if it's ever needed

## Not decided yet

| Item | Who settles it |
|---|---|
| Demo data specifics: grants, people, amounts, dates, documents, including a situation only the agent's judgment catches | product |
| How to demo: how the clock and the seeded workspace get used in the pitch | product |
| The evidence report's name, its layout, and the sign-off flow (preparer and reviewer) | product |
| Whether checks and reasons use the university's cost criteria as labels, for example Berkeley's | product |
| How drafted explanations are written: by code from the records, or by the agent with citations | product, if the feature is built |
| The clock controls the user sees | product |
| What a workspace reset clears, and how the seed is copied on sign-up | product |
| The screens for confirming terms, the problem list, the checklist and the thread. The layout ideas above are a starting point. | product |
| How a problem on the grant itself and a note on the grant are shown | product, with the screens |
| How reversals and cost transfers show in buckets and at closeout, beyond their default checklist. Berkeley's 120-day limit on cost transfers is discussed with it. | product |
| Whether a Program Officer's email, outside Research.gov, counts as approval. Until it's settled, such an approval stays in Needs a human. | product |
| Whether a later change reopens a sign-off | product |
| A cost shared by two grants while each grant is isolated: each grant's copy of the invoice shows the other grant's part as money never charged at closeout. How to show that without a false alarm. | product |
| Whether the agent's corrections to its own facts, such as a misread receipt total, wait for the accountant like its link fixes do. The contracts make every correction the agent writes wait, except a new answer to its own question, which [0010](decisions/0010-agent-suggests-accountant-decides.md) narrows. | product |
| How the evidence report shows the agent's answers next to code's reasons | product |
| How the optional chat relates to review threads | product, if chat is built |
| How the budget check treats indirect costs. They're out for now, so comparing spending with the award's limit is only as complete as the ledger. | product, later |
| The scope lists above disagree in three places. A general chat and workspace members each appear as optional and as out for now. Creating extra workspaces is optional in one list and described as built elsewhere. | product |
| How charges and records are sorted together on the problem list. A simple start: most serious first, then oldest. | product, with the screens |
| How reusable notes, the offer on a similar charge, and confirmed duplicates are laid out | product, with the screens |
| Screen layouts, and how emails are displayed | builder |
