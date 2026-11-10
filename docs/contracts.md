# Contracts

Contracts are the seams between areas of the repo. Once one is agreed, each side can build without waiting for the other. The design behind them is in decisions [0009](decisions/0009-agent-judges-code-checks.md), [0010](decisions/0010-agent-suggests-accountant-decides.md), [0011](decisions/0011-evidence-checklist.md), [0012](decisions/0012-checked-quotes-and-highlights.md), [0013](decisions/0013-stack-additions-and-repo-structure.md), [0015](decisions/0015-six-code-checks-and-the-agents-rulebook.md), [0016](decisions/0016-default-checklists-by-account-group.md), [0017](decisions/0017-grant-terms-from-award-notices.md) and [0018](decisions/0018-agent-works-from-saved-facts.md).

**Status:** a design, not yet code ([decisions/0014](decisions/0014-contracts-are-a-document-first.md)). This file is the source of truth for the contracts until the contract code is written. From then on the code is the truth and this file explains it. Changes to it need the product owner's agreement.

Two parts aren't settled:

- **The newer records,** marked "new" below. What each one is for is agreed. Its exact names and fields aren't, and for some of them, neither is everything it has to hold.
- **What each screen gets from the server.** The docs decide what each screen holds, and that part isn't written yet.

Both are listed under [Not decided yet](#not-decided-yet).

The contract code for records, checks and the agent side is written first ([decisions/0019](decisions/0019-build-order.md)).

## Where the contracts will live

| Contract | Will live in |
|---|---|
| Record format, links, checklists, judgments, decisions | `backend/app/contracts/records.py` |
| Charges and the ledger file | `backend/app/contracts/charges.py` |
| Evidence files | `backend/app/contracts/evidence.py` |
| Checks interface | `backend/app/contracts/checks.py` |
| Agent runs | `backend/app/contracts/runs.py` |
| Review threads | `backend/app/contracts/threads.py` |
| API (application programming interface) bodies | `backend/app/contracts/api.py`, and the endpoint list below. The frontend generates its TypeScript types from FastAPI's OpenAPI schema. |
| Users, workspaces and grants | `backend/app/contracts/workspaces.py` |
| The base every model shares | `backend/app/contracts/base.py` |
| Eval answer key | `backend/app/contracts/eval.py` |
| Database tables | A migration in `supabase/migrations/` |
| Sample grant | `backend/app/contracts/fixtures/golden/` |

## Changing a contract

1. A contract changes only with the product owner's agreement. Contract files have one writer at a time.
2. Open a pull request (PR) that changes the contract. Once the contract code exists, update the code that uses it in the same PR so main stays green, or open an issue for the follow-up.
3. If the change alters behavior or direction, add a file to [decisions/](decisions/).

## Conventions

- IDs are strings. User IDs are Supabase auth UUIDs.
- Timestamps are timezone-aware and stored in UTC. Records carry their grant clock's "now". The clock belongs to the grant ([0028](decisions/0028-one-clock-per-grant.md)). Only what belongs to the machine stays on real time: the order records were stored in, background timers, logs and sign-in expiry.
- Money is an integer number of cents in US dollars. Credits are negative.
- Contract models reject unknown fields and can't be changed after they're created.
- For now each grant is isolated: a record's charge and the records it points to are on its own grant, and the agent works on one grant at a time.
- Names in `code style` are the names the contract code uses. For the parts marked new, they're working names.

## 1. Records

A record is one thing the agent or the accountant wrote. It's never edited. A correction is a new record whose `replaces_id` points to the old one, and the old one stays. Every record has an envelope: `id`, `workspace_id`, `grant_id`, `author` (`agent` or `user`), `author_user_id` (set exactly for `user`), `written_at` (the clock's "now") and `replaces_id`. Its `data` is one of these kinds:

| Group | Kind | What it holds | Who writes it |
|---|---|---|---|
| Grant terms | `period_of_performance` | `start` (optional: an amendment may state only the new end date), `end` | Agent or accountant |
| | `budget_line` | `name`, `amount`. One line or sub-line of the budget, in the standard categories of the National Science Foundation (NSF). | Agent or accountant |
| | `person` | `name`, `email` (optional), `role` as the document states it. Someone named in the award letter, or a known sender the accountant adds. | Agent or accountant |
| | `approval_rule` | `applies_to`, `approver`, `channel` (optional) | Agent or accountant |
| | A rate (new) | A rate that applies across the grant, such as a fringe benefit rate, and its name | Agent or accountant |
| | A funding notice's amounts (new) | The notice's amendment number and type, the amount it adds and the award's running total. See section 8. | Agent or accountant |
| | `other_term` | `label`, `statement` | Agent or accountant |
| Facts from evidence | `bill` | `total`, and optionally `vendor`, `dated`, `description`, a document number (new) and `items` (each a `description` and an `amount`). A credit has a negative total. | Agent or accountant |
| | `approval` | `approver_email` (for a forwarded email, the original sender's), `covers`, and optionally `approver_name`, `approved_on` and `channel` | Agent or accountant |
| | `note` | `label`, `statement`, and an optional period (new) | Agent or accountant |
| Links and answers | `link` | See section 2 | Agent or accountant |
| | `budget_assignment` | `charge_id`, `record_id` (the `budget_line` term), `reason` | Agent or accountant |
| | `judgment` | See section 4 | Agent or accountant |
| The evidence checklist | A checklist item (new), and removing one | See section 3 | Agent or accountant |
| The agent's suggestions | A dispute (new) | See section 4 | Agent |
| | A duplicate mark (new) | The copy and what it copies. See section 5. | Agent |
| The accountant only | `confirmation` | `record_ids` (at least one), `decision` (`confirmed` by default, or `rejected`) | Accountant |
| | An accepted reason (new) | See section 5 | Accountant |
| | A snooze (new) | See section 5 | Accountant |
| | `sign_off` | `note` (optional) | Accountant |
| Either | `retraction` | `reason` (optional). Replaces a record with nothing, so it always names the record it replaces. | Agent or accountant |

A record kind earns its place only if a check reads it or the evidence report shows it. Don't add kinds beyond that.

Rules every record follows:

- `author_user_id` is set exactly when the author is `user`.
- A record can't replace itself.
- Every value read from a document is a cited value (below), except the `label` on an `other_term` and a `note`, which is a plain short name.
- The agent's values always carry a citation, its link always has a `part`, and its flag is always `unsure`.
- The agent never writes the kinds marked "Accountant".

- **`bill`** is the working name for any document that bills for a cost. It covers invoices, receipts, card slips, credit memos, and a facility's usage statement.
- **A bill's document number** is its invoice or order number. The ledger line often carries the same number, which makes it the strongest match. The agent puts anything else that identifies a document in its description: names, order numbers, and the project or award number it mentions.
- **Terms come from the award letter, an amendment, or a program solicitation** added to the grant as a source. A solicitation's terms use the same kinds. It has no record kind of its own.
- **A `budget_line`** is one line or sub-line the award letter's budget prints, named as NSF prints it. Each one is its own term: Other Direct Costs is a term, and so is Materials and Supplies inside it.
- **Every term also has `dated`:** the date the document gives itself, such as an amendment's date. An amendment isn't a correction. It's a new term, and the checks use `dated` to decide which terms are in force.
- **`other_term`** holds anything an award letter or amendment says that no other kind holds, such as a principal investigator (PI) on leave. It's in force from its own date on, and the agent reads any dates inside its statement.
- **A `note`** is evidence that supports or explains a charge without billing or approving it: a payment notice saying which invoices a payment covered, an appointment letter, an effort report. A document that covers a stretch of time states it as a period, so code can check it against the checklist item it fills.
- **A `retraction`** is also how an accepted reason is reopened, a duplicate mark undone, and a reusable note withdrawn. Nothing is deleted.

### Cited values

A value read from a document is a cited value: `value`, `text` (the value exactly as the document writes it) and `citation`. The text has to appear in the citation's passage (trust rule 2). The agent always cites. A value the accountant enters has no citation.

A citation holds the `file_id`, the `passage` and its `location`. Locations use the Anthropic API's own names and counting, so the agent copies them over unchanged: `char_location` (plain text), `page_location` (PDFs with real text) and `content_block_location` (custom content documents). For a photo or a scanned page there's no passage, and the location is an `image_box`: a box around the value, with its page (1 for a single image), as fractions of the page from its top left corner.

New with [0012](decisions/0012-checked-quotes-and-highlights.md):

- **A citation stores how it was matched against its file:** exact, close or not found. For a PDF it also stores where the highlight goes, found once when the record is saved.
- **A box on a photo or scan** comes back from the agent in pixels on the image we sent, at a size we control. Code scales it back to the original. A second look reads only the boxed area and has to see the same value.
- **A value is confirmed in three ways:** its citation was found in its file, the accountant confirmed the record it's in, or the accountant typed it. Code works this out each time, and nothing stores it. So confirming a term confirms its values.
- **An unconfirmed value** that a check or an answer rests on sends its charge to Needs a human. Any other unconfirmed value, such as a vendor name, only shows that way on its evidence card.

### What counts

- **What goes with the flow takes effect, and what goes against it waits** ([0010](decisions/0010-agent-suggests-accountant-decides.md)). These records of the agent's count only once a `confirmation` lists them with `confirmed`:
  - its grant terms
  - any record that replaces or retracts an existing record: a suggested fix to a link, a withdrawn flag, a correction. Link fixes, changed answers and withdrawn flags wait for the accountant. Whether the agent's corrections to its own facts wait is open (see "Not decided yet"), and this design makes them wait.
  - a second link between a bill and a charge that already have one in force. It's saved and waits like a fix.
  - removing a checklist item
  - a dispute
  - a duplicate mark
- **A new answer over one of the agent's own** counts right away, unless it clears a problem. Contradicts turning into anything milder waits. Unsure turning into supports waits unless new evidence has arrived. A refreshed answer that says the same thing, and any change toward a concern, count right away.
- **New evidence** means something that arrived after the agent's last answer, or a grant term confirmed after it. Something the agent links later from what was already on file doesn't count. Code checks this.
- **The agent can suggest a fix to one of the accountant's links, and a new answer to one of theirs.** Both wait, and theirs stays in force meanwhile. It never replaces any other record of theirs. It also can't write a second answer beside theirs.
- **A waiting suggestion keeps its charge with the accountant.** While any suggestion of the agent's waits, every charge it touches has a Needs a human reason that shows the suggestion, so the charge is in Needs a human unless a more serious reason applies. That holds for a link fix, a checklist item removal, a duplicate mark, a replacement for the accountant's answer, and a withdrawal of the agent's own flag. What was in force stays in force meanwhile. A waiting dispute is the special case: the disputed reason itself counts as Needs a human, which moves the charge from Possible conflict to Needs a human unless another reason keeps it there (section 4).
- **No repeats.** After the accountant rejects a suggestion or a dispute, the same one is refused unless new evidence has arrived.
- **The latest decision on a record wins,** and a rejected record never counts. Only the accountant's confirmations that nothing has replaced are counted.
- **Several records may replace the same one,** because the agent's suggestions wait. The accountant confirms at most one.
- **Current records** are the records that count, minus those an effective record replaces, minus retractions.
- **A pointer follows a correction.** When a record is corrected, links to the old one aren't rewritten. They follow it to the record that replaced it, and the checks rerun.

The contract code provides functions for these rules, so every area applies them the same way. Pass them only the records and files visible at the clock's "now". The exact list of the agent's writes that wait, as code enforces it, is still to settle (see "Not decided yet").

### Checking a write

The write check (`check_new_record`) returns a list of problems in plain sentences, or nothing if the record can be saved. The backend runs it on every write, and the agent sees the problems so it can fix them. It checks that:

- every quoted value appears in its passage, and every citation has been matched against its file
- the records and charges a record points to exist, and the records are current
- the agent replaces none of the accountant's records except their links and answers, and a replacement is the same kind or a retraction
- a link points to a bill, approval or note, carries an amount only when the checklist item it fills carries one, and its part is in the linked record's own file
- a link doesn't point at a copy the accountant has confirmed as a duplicate
- the agent doesn't write a second answer beside one of the accountant's. It suggests a replacement, which waits.
- a judgment's question is about the right kind of record
- a confirmation lists only records that wait for one, or that have an unconfirmed value. Confirming a value this way is a working choice (see "Not decided yet").
- a budget assignment points to a `budget_line`, and its charge has no other current assignment
- a suggestion the accountant rejected isn't repeated without new evidence
- for now, the charge and the records a record points to are on the record's own grant

## 2. Links

A link ties a fact to a charge. It's a record of kind `link`, and it's its own concept everywhere: in the code, the API, the screens and these docs.

| Field | What it holds |
|---|---|
| `record_id` | The bill, approval or note. The database enforces that it exists. |
| `charge_id` | The charge. The database enforces that it exists. For now it's on the link's own grant. |
| `amount_cents` | How much of the bill this charge uses. Negative for a credit. A link carries an amount only when the checklist item it fills carries one, which in practice means a link to a bill. |
| `part` | A citation: the place in the record's own file that pertains to this charge, highlighted when the user opens it. For a whole bill, it's the total's citation. The agent always gives one. |
| The checklist item it fills (new) | An item someone added, or one of the charge's defaults. See section 3. |
| `reason` | Optional: one line on why they match |

The meaning comes from the record: a bill link means "pays for", an approval link "approves", and a note link "supports" or "explains". A split is one bill linked to several charges, each link with its amount and part, such as an itemized line. There's no separate split record. When an email gives the basis instead, such as "56 of the 96 samples are for grant 1", the email is read as a `note` and linked to each charge, because a link's part has to be in its own record's file.

**Budget lines.** The agent decides which budget line each charge belongs to and writes a `budget_assignment`: the charge, the `budget_line` term and a one-line reason. A charge has at most one current assignment, so a change replaces it, and the accountant can replace the agent's. The checks read it for whether an approval rule applies, and the budget check on the grant reads it for spending on each line. They also read the ledger's own account. A budget line is already one of NSF's budget categories, so only the account is translated: its account group carries an NSF category, and code compares that with the assigned line. They match when the category is that line, or when one contains the other, as Other Direct Costs contains its six sub-lines. An approval is required if either one says so, and a disagreement between them is Needs a human.

**A waiting fix.** While a fix the agent suggested waits for the accountant, every charge it touches is in Needs a human, showing the suggestion. The old link stays in force until the accountant confirms the fix.

**The sums.** Code checks them on every change:

- **Per bill:** its links add up to at most its total.
- **Per checklist item that carries an amount:** the bills linked to it add up to the item's amount.
- **Per charge:** the amounts on its checklist add up to the charge.

| | Under | Over |
|---|---|---|
| **A charge's items** | Missing evidence. Flagged as section 8 says. | Needs a human |
| **A bill's links** | Not a problem at first: the rest waits for a charge. A bill with money nobody charged becomes a problem on the bill 60 days after it arrived. | Needs a human, on every charge using the bill |

The agent writes the links it believes are right, even when one pushes a sum over. It never skips or shrinks a link to make a sum fit.

## 3. The evidence checklist

New with [0011](decisions/0011-evidence-checklist.md). Every charge has a checklist of the evidence it should have. Code works it out and tracks each item as filled or missing.

- **Default items aren't stored.** Code works them out each time from the charge's ledger account, like statuses, so a fixed default reaches old charges too.
- **Defaults hang on groups of accounts** ([0016](decisions/0016-default-checklists-by-account-group.md)). A small table in the code says which account codes belong to which group, and gives each group its default list and its NSF budget category. It covers Berkeley's accounts first, and the starting lists are in [domain.md](domain.md#default-checklists-by-account-group). An account in no group gets only the items the agent adds.
- **A required approval is a default item too.** Code adds it when one of the grant's approval rules applies to the charge. "NSF approval" also goes on the checklist when the agent recognizes something on NSF's standing list.
- **A cost dated up to 90 days before the start date** gets an item for the university's own pre-award approval.
- **A reversal or cost transfer** defaults to the line it corrects plus a written justification. These two items apply to any line that corrects another, whatever its account. A line that takes money off the grant gets these two in place of its account group's default. A line that adds money to the grant keeps its account group's default and gets these two as well ([0020](decisions/0020-reversals-and-cost-transfers.md)). The line's NSF category still comes from its account's group. Check 6 is these two items and nothing more. It has no reason of its own: the checklist check reports each item as filled or missing.
- **An added item is a record** on the charge: what's needed, and who added it. It takes effect right away.
- **Removing an item** is a record too. The agent's removal waits for the accountant. The accountant's takes effect right away.
- **An item can carry an amount.** Either the bills linked to it add up to that amount, or the amount comes from a rate: a quantity times a rate, both cited, with the math re-checked by code. The rate has to come from a file on the grant or from a confirmed rate term.
- **An item can name a period,** such as one month. Code checks that the linked document's own period covers it. One document can fill items on many charges.
- **An item can say when it's expected.** It isn't late before then (section 8).
- **A charge with an empty checklist is Needs a human.** It can't be complete until its checklist has at least one item and every item is filled.

## 4. Judgments and questions

Code checks the clear-cut rules itself. For what it can't settle, it asks a question about a charge, and the answer is stored as a `judgment` record.

| Question | When code asks it |
|---|---|
| `allowable`: "Is this cost necessary and reasonable, and is it for this project?" | Every charge that has evidence linked |
| `covers`: "Does this approval cover this charge?" | When an approval rule applies to the charge and an approval is linked, or when an approval is linked to a charge dated more than 90 days before the start date (section 8). `record_id` is the approval. Whether a rule applies depends on the charge's `budget_assignment` and on the ledger's account. |
| `unusual_term`: "Does this term change anything for this charge?" | Once for each confirmed `other_term` in force on the charge's date. `record_id` is the term. |
| `flag`: the agent's own question | Whenever the agent sees something no other question covers. The agent's answer is always `unsure`, and the accountant settles it by answering it. A flag can be about a charge, a record, or a file that has no record, such as one that can't be read. |

A judgment holds `charge_id`, `question`, `record_id`, `text` (the question as asked), `answer`, `reasoning`, `quotes` (citations) and `rests_on` (the record IDs the answer depends on). The answers map to buckets: `supports` passes, `contradicts` is Possible conflict, and `unsure` is Needs a human. The reasoning is shown in the app and the evidence report, labeled with who wrote it.

- **The rulebook.** The agent answers from its funder's rulebook, and each answer names the rule it used ([0015](decisions/0015-six-code-checks-and-the-agents-rulebook.md)).
- **Safety rule:** the agent can only clear a question code asked. A required question with no current answer is an open question, and it puts the charge in Needs a human.
- **When the agent answers again:** when something new is linked to the charge, when a record its answer rests on is corrected or retracted, or when a new `other_term` or approval rule covering the charge's date is confirmed. Not when the clock moves or an amount, a budget or a period changes.
- **Out of date.** Code treats an answer as out of date when a link to its charge was written after it, or a record it rests on is no longer current. A new question appears when a new term or rule makes one required. While the agent is answering again, the charge keeps its last answer for the bucket and is marked `rechecking`. With no answer yet, the charge is in Needs a human.
- **Which of the agent's new answers wait** is in section 1, under "What counts".
- **The accountant** answers what the agent was unsure about, and can overrule any judgment by writing their own that replaces it. Once the accountant has answered, an out-of-date answer goes back to the accountant, not the agent, and the charge is in Needs a human until they answer again. The agent can suggest a new answer, which waits.

**Disputes.** When the agent thinks one of code's checks is wrong for a charge, it writes a dispute: the charge, the check, its reasoning and quotes. The dispute waits for the accountant. While it waits, the disputed reason counts as Needs a human. Confirming it accepts the reason, with the agent's reasoning as the note. Rejecting it puts the charge back, and the agent can't dispute the same check on that charge again without new evidence.

## 5. The accountant's decisions

New with [0010](decisions/0010-agent-suggests-accountant-decides.md), except the confirmation and the sign-off.

**Confirmation.** Confirms or rejects the agent's records that wait. It also confirms a record that has a value nobody could confirm in its file.

**An accepted reason.** The accountant accepts one reason on a charge, a record or a file, with a note. It holds what it's about, the check and its reason, the note, and whether the note is one-off or reusable.

- It covers the problem as it stood. If the facts under it change, it no longer applies and the charge comes back.
- An accepted charge keeps the bucket the checks gave it. It shows as Accepted, comes off the problem list, and is counted on its own, never as Evidence complete.
- Reopening it is a retraction.
- **A one-off note** is never reused.
- **A reusable note** applies on its own to a later charge inside three limits: the same check failing for the same reason, the same ledger account and vendor, and an amount no larger than the largest the accountant has accepted under that note. Code does the matching, and nothing stores it per charge. Every other check still runs.
- **Outside the limits,** a charge with the same problem and ledger account that fails the vendor or amount limit is flagged as usual, with the note offered. Accepting the offer takes one click, as just this charge, which leaves the amount limit alone, or as this and similar charges, which raises it. Just this charge is the suggested default.
- A charge with no vendor only ever gets the offer.
- Withdrawing a reusable note is a retraction, and it brings the charges it covered back.

**A snooze.** Hides a problem from the list until a date: what it's about, the date and a note. The checks still say it isn't done, so the charge keeps its bucket. A new problem brings it back early. Every snooze ends when the closeout window opens. Inside the window a snooze can still be set, up to the grant's end date.

**A duplicate mark.** The agent marks a copy of something already on file, such as a photo and a PDF of the same invoice, and the mark waits. Whether the mark joins two facts or two files is still to settle. The agent leaves the copy unlinked meanwhile. Once the accountant confirms it, the copy stays in the evidence list marked as a duplicate, stays out of matching, and can be undone with a retraction. A rejected mark means the agent matches the file normally.

**Sign-off.** The accountant signs off on the grant's evidence report.

## 6. Charges

One charge comes from one ledger line, read by code. The agent never writes charges.

| Field | Notes |
|---|---|
| `ledger_line_id` | Unique within a workspace. The same line twice adds nothing. |
| `transaction_date` | When the cost happened. The checks use this one. |
| `posting_date` | When the ledger recorded it. The 60 days for missing evidence count from here. |
| `arrived_at` | When it reached FundTrail. The clock uses this one. For an uploaded ledger file, 00:00 UTC on the posting date if that's still ahead of the grant's "now", and otherwise now ([0023](decisions/0023-the-clock.md)). |
| `amount_cents` | Negative for a reversal, a transfer out or a credit |
| `description`, `account`, `vendor`, `reference` | As the ledger gives them. `account` is the ledger's own expense category. |
| `original_line_id` | For a reversal or cost transfer: the `ledger_line_id` of the line it undoes or moves. It's a line ID, not a charge ID, because the original may be on another grant or arrive later. |

## 7. Evidence files

The original is stored as it arrived, in the private Supabase Storage bucket `evidence`, at `{workspace_id}/{grant_id}/{file_id}/{name}`.

| Field | Notes |
|---|---|
| `grant_id` | One grant per file for now. Files move to the workspace level later. |
| `source` | `gmail`, `drive` or `upload` |
| `name`, `media_type`, `storage_path`, `sha256` | The fingerprint catches the exact same file arriving twice |
| `document_date` | The file's own date when the source gives one, such as an email's sent date. A date written inside the document is a cited value on a record instead. On a sample grant, a live email or Drive file is dated to the simulated time, and the stored original is unchanged ([0028](decisions/0028-one-clock-per-grant.md)). |
| `arrived_at` | When it reached FundTrail. The clock uses this one. |
| `sender`, `source_ref` | The sender's address for Gmail, and the Gmail message ID or Drive file ID |
| `parent_id` | For an attachment, the email it came with |

## 8. The checks' interface

```python
def run_checks(checks_input: ChecksInput) -> ChecksOutput
```

A pure function, with no database and no model inside. W2 implements it in `backend/app/checks/`.

- **In:** `now` and everything in one workspace visible at that time: the charges, the evidence files and the records, including replaced, waiting and rejected records. It takes the whole workspace. For now each grant is isolated, so the checks can also run one grant at a time. Each grant has its own clock ([0028](decisions/0028-one-clock-per-grant.md)), so `now` is a grant's "now", and how the input reconciles that with a whole workspace is open (see "Not decided yet").
- **Out:**
  - **A status for each charge:** its `bucket`, every reason (the check, its bucket, text built by code, and the records it rests on), its evidence checklist, whether it's `flagged`, whether it's `rechecking`, and whether it's accepted or snoozed.
  - **A status for each record or file that has a problem of its own** (new).
  - **The open questions:** every required question without a current answer, and who answers it (the agent, or the accountant when they answered before).
  - **Problems on the grant itself** (new): a problem about the whole grant, which goes on the problem list, such as spending over the award's limit.
  - **Grant notes:** anything else about the grant as a whole that isn't about one charge or record, such as an overspent budget line. A note isn't a problem.
- **Confirmed terms only.** The checks read only confirmed terms. Where an older confirmed term exists, it stays in force. Where none exists, each charge is in Needs a human, with a reason that says which terms aren't confirmed. Checks that need no terms still run.
- **The code checks.** There are six ([0015](decisions/0015-six-code-checks-and-the-agents-rulebook.md), and [product.md](product.md#what-code-checks) for what each one fails to).
  - **Five are about a charge:** the cost's date against the period in force, the evidence checklist and its sums, required approvals, that every value the charge rests on is confirmed, and that a reversal or cost transfer names the line it corrects and has a written justification. The last has no reason of its own. It's the reversal's two default checklist items (section 3), and the checklist check reports them, filled or missing.
  - **One is about the grant:** the budget. It never adds a reason to a charge.
- **The cost's date.** A cost dated more than 90 days before the start date is in Possible conflict unless NSF's approval is on file. That means an `approval` record linked to the charge that the agent's `covers` answer supports.
- **The buckets,** as the code and the answer key write them: `evidence_complete`, `possible_conflict`, `missing_evidence` and `needs_human`.
- **A reason** holds the check's stable ID, such as `period_of_performance`, the bucket that check puts the charge in, text built by code, and the records it rests on. A charge's reasons include the checks that pass. A pass is `evidence_complete`.
- **Where a charge's reasons come from:** the checks about a charge, the agent's answers and flags, a suggestion waiting for the accountant, a disputed check, and a disagreement between the ledger account's category and the assigned budget line. That last one is a reason of its own, in Needs a human, and belongs to none of the numbered checks. The budget check never adds a reason to a charge.
- **The bucket** is the most serious bucket among the reasons, in the order Possible conflict, Needs a human, Missing evidence, Evidence complete. It's the bucket the checks give, whether or not the accountant accepted a reason.
- **Flagged** means on the accountant's problem list.
  - Possible conflict and Needs a human are flagged, unless the accountant accepted the reason or snoozed the charge.
  - Missing evidence is flagged `MISSING_EVIDENCE_DAYS` (60) past the date an item was expected. For most items that's the charge's posting date.
  - From `CLOSEOUT_WINDOW_DAYS` (90) before the grant's end date, when Berkeley sends its first Notice of Expiration, every missing item is flagged, even one that isn't due yet. Each reason carries the date the item is expected.
  - A missing approval is flagged right away.
- **Problems on records and files.** Code raises the clear-cut ones: a bill linked for more than its total, a bill with money nobody charged 60 days after it arrived, a term waiting to be confirmed, confirmed terms that disagree, and the exact same file on the grant twice. The agent raises anything else with a flag.
- **Problems on the grant itself.** Code raises four:
  - the grant has no confirmed dates, or no budget
  - spending is over the award's limit
  - a funding notice's totals don't add up: the earlier confirmed total plus the amount the notice adds has to equal the notice's running total
  - an amendment number is skipped
- **The budget.** This check runs on the grant. An overspent budget line is a grant note. Spending over the award's limit is a problem on the grant. The limit is the "Total Amount Obligated to Date" on the latest confirmed notice, so a notice that adds money raises it once the accountant confirms it. Spending is the sum of the charges on the grant's ledger.
- **Status history:** a row is written each time a status changes, with when it changed and its trigger: a record, a charge, a file, a message in a thread, or the clock. For a change that comes from saving an agent run, the trigger is what started the run, for example "invoice 1001 arrived".

## 9. Agent runs

A run is one background job. It's queued each time a charge or an evidence file arrives, each time one of the accountant's records leaves a question open for the agent (for example confirming an `other_term`, or approving a fix that adds a link), each time the accountant writes in a thread, and once per grant when the closeout window opens, to review all the grant's links and every checklist item still missing.

- The agent works in a loop of actions: it looks at anything on the grant, opens files, and writes records. It gets what just arrived in full, and the rest of the grant as lists built from the saved facts, one line per charge and one per document. Code hides nothing: the agent can search the lists and open any file ([0018](decisions/0018-agent-works-from-saved-facts.md)). Every write goes through the write check as it happens, and problems go back to the agent.
- A run can't finish while an open question is waiting for the agent.
- Everything the run wrote is saved together at the end, so a run that fails saves nothing.
- Runs for one grant go one at a time. A run started by a message in a thread goes ahead of the other queued runs and waits only for the run in progress.
- Code hands each run what needs attention, so the agent doesn't have to remember: the checklist items still missing on the grant, the checks failing on the charges in the run, the bills already on file that look like a new one, and for a thread message, that thread.
- Every run also gets its funder's whole rulebook, and the end date in force.

A run holds its `trigger`, its `status` (`queued`, `running`, `done` or `failed`), `clock_now` (the grant clock's "now" the run works at, which its records carry), real-time `queued_at`, `started_at` and `finished_at`, a short `summary` and any `error`. The exact actions the agent has are decided with its prompts (W1).

## 10. Review threads

New with [0010](decisions/0010-agent-suggests-accountant-decides.md). Every charge can have a thread, and so can a record with a problem. A message holds what the thread is about, who wrote it, the text, the time, and for the agent's message, the run that wrote it.

- Messages live in their own table, outside the records, and are never edited.
- A message changes nothing on its own. Anything the agent wants changed is a record that waits.
- The evidence report shows decisions, which are records, and leaves messages out.

## 11. Database tables

| Table | Holds |
|---|---|
| `users` | One row per Supabase auth user: the ID, email and name |
| `workspaces` | The name and the owner. The clock isn't here: it belongs to the grant. |
| Workspace members (new) | The membership list: workspace, user and role. The owner and the workspace's sample accountant are members ([0029](decisions/0029-workspace-members-and-one-access-check.md)). |
| `grants` | The workspace, the funder (NSF only for now), award number and title. The last two are empty until the award letter is read. Each grant has its own clock: the real time, or a sample grant's simulated "now" ([0028](decisions/0028-one-clock-per-grant.md)). Its fields are open. |
| `charges` | Section 6 |
| `evidence_files` | Section 7 |
| `records` | The envelope as columns and `data` as JSONB (binary JSON). The record's kind, its charge and the record it points to are generated from `data`, and the last two are foreign keys, so the database enforces what links and judgments point to. |
| `statuses` | Status history, one row per change. A view gives the latest row for each charge, record or file. |
| `agent_runs` | Section 9. The only table updated in place. |
| Thread messages (new) | Section 10 |

- Rows match the models, with these differences: a record row's `data` is the record's data as JSON, with `kind`, `charge_id` and `record_id` as columns generated from it. A status row splits its trigger into `trigger_kind` (`record`, `charge`, `file`, `clock`, and a thread message) and `trigger_id`, and adds `workspace_id`. `records` and `users` add a real-time `created_at`, which also orders records written at the same clock time. The view of the latest status is `current_statuses`.
- `records`, `charges`, `statuses` and thread messages reject updates. Deletes stay allowed so starting a sample grant over can clear them ([0027](decisions/0027-sample-grants.md), first version).
- The database also enforces: one charge per ledger line ID in a workspace, one file per storage path, `author_user_id` set exactly for `user` records, a user-written record's author being a member of the record's workspace ([0029](decisions/0029-workspace-members-and-one-access-check.md)), a record not replacing itself, a retraction replacing something, a link or budget assignment naming both its record and its charge, only the accountant writing confirmations, accepted reasons, snoozes and sign-offs, and one running agent run per grant.
- Row level security is on, with no policies. The backend uses the service role key, and the browser never reads the tables directly.
- There's no old data to convert. Nothing real is stored yet.

## 12. API

**Sign-in.** The browser signs in with Supabase Auth (Google) and sends the access token on every request as `Authorization: Bearer <token>`. The backend verifies the token, finds the user from it, and asks the one access check whether the user may reach the workspace or grant ([0029](decisions/0029-workspace-members-and-one-access-check.md)).

Errors use FastAPI's default `{"detail": ...}` body. A write that the write check rejects returns 422 with the list of problems.

| Method and path | Body | Returns |
|---|---|---|
| `GET /workspaces` | | The user's workspaces |
| `POST /workspaces` | A name | The workspace |
| `GET /workspaces/{workspace_id}/grants` | | Each grant with its bucket counts, how many are on the problem list, and how many of the agent's records wait |
| `POST /workspaces/{workspace_id}/grants` | Form with the award letter as `file` | The grant |
| Opening a sample (new) | | Paths to settle ([0027](decisions/0027-sample-grants.md)) |
| Reading and moving a grant's clock, and its timeline (new) | | Paths to settle, per grant ([0028](decisions/0028-one-clock-per-grant.md)) |
| Starting a sample grant over (new) | | Path to settle ([0027](decisions/0027-sample-grants.md), first version) |
| `GET /grants/{grant_id}` | | The grant's terms and their state, the agent's waiting suggestions, open questions for the accountant, problems on records and files, reusable notes, grant notes |
| `GET /grants/{grant_id}/charges` | | Each charge with its status |
| `POST /grants/{grant_id}/ledger` | Form with the ledger file as `file` | How many lines were added, already present, or rejected with the row and the reason |
| `GET /grants/{grant_id}/evidence` | | Each file with the facts and terms read from it and the links to them |
| `POST /grants/{grant_id}/evidence` | Form with the file as `file` | The file |
| `GET /grants/{grant_id}/records` | | Every record, replaced and waiting ones included |
| `POST /grants/{grant_id}/records` | The record's `data` and an optional `replaces_id` | The record |
| `GET /grants/{grant_id}/runs` | | The grant's agent runs, newest first |
| `GET /grants/{grant_id}/report` | | The PDF evidence report |
| `GET /charges/{charge_id}` | | The charge's status with its checklist, its history, its links with their records and files, the answers about it, the suggestions waiting on it, and its thread |
| `GET /evidence/{file_id}/content` | | A short-lived link to the original |
| Reading and posting a thread's messages (new) | | Paths to settle |

- Adding a grant stores the award letter and queues an agent run. The grant comes back right away, and its terms appear as the agent writes them.
- Every accountant action that decides something goes through `POST /grants/{grant_id}/records`: confirming or rejecting terms and the agent's suggestions, answering or overruling a question, linking or splitting by hand, changing a checklist, accepting a reason, snoozing, correcting or retracting a record, adding a known sender, and signing off. The server fills in the ID, author and time.
- Thread messages aren't records, so they have their own routes.
- The clock belongs to the grant. A real grant's clock is the real time and can't be moved. A sample grant's clock only moves forward: to the next event, or to a chosen date, with everything between played in order ([0027](decisions/0027-sample-grants.md), first version).
- What each of these returns in detail depends on what each screen holds, which the docs haven't settled yet (see "Not decided yet").

## 13. Ledger file

CSV or Excel, one file per grant. In the hackathon build, a sample grant's file holds its whole history, and the clock releases each line on its posting date. The first row is a header with these names, in any order:

| Column | Required | Format |
|---|---|---|
| `line_id` | Yes | The ledger line ID |
| `transaction_date` | Yes | `YYYY-MM-DD` |
| `posting_date` | Yes | `YYYY-MM-DD` |
| `amount` | Yes | Dollars with up to two decimals, negative for credits, for example `-1240.00` |
| `description` | Yes | |
| `account` | Yes | The expense account or category |
| `vendor` | No | |
| `reference` | No | An invoice or document number |
| `original_line_id` | No | For a reversal or cost transfer, the line it corrects |

An empty cell is a missing value. Each row becomes one charge: `line_id` becomes `ledger_line_id`, `amount` becomes `amount_cents`, and `arrived_at` is 00:00 UTC on the posting date if that's still ahead of the grant's "now", and otherwise now ([0023](decisions/0023-the-clock.md)). A row whose `line_id` is already on file is skipped. Mapping another system's column names is a later addition.

## 14. Eval answer key

One JSON file per case, written before the case's documents:

- `case`, and `award_number`, which must start with `SYN-`
- `records`: the facts and terms the agent should read. Each has a `kind`, a `file` (the case file it cites) and `fields`, the expected values by field path as strings: dates as `YYYY-MM-DD`, money in cents, text as written, for example `{"total": "124000", "items[0].description": "..."}`.
- `links`: each has the `file` the linked fact was read from, the charge's `line_id`, and for a bill the `amount_cents`.
- `budget_lines`: each has a charge's `line_id` and the `budget_line` name as the award letter writes it.
- `answers`: each has a `line_id`, a `question`, for `covers` and `unusual_term` the `about_file`, and the expected `answer`.
- `buckets`: each has a `line_id`, an `at` (a clock time after the arrival it follows) and a `bucket`.

The key grows to cover checklist items, suggestions, disputes, unconfirmed values and accepted charges. How it expresses them isn't settled.

**What counts as a match.** Over the agent's current records on the case's files:

- **Records:** a match has the same kind, cites the same file, and every listed field equals the record's value, compared as strings ignoring case and extra whitespace. Fields the key leaves out aren't compared.
- **Links:** a match links a fact from the same file to the same charge, with the same amount.
- **Budget lines:** a match assigns the same charge to a budget line with the same name.
- **Answers:** a match answers the same question about the same charge (and the same file, when given).
- Each expected item matches at most one agent item. An expected item with a match is **right**, one with none is **missing**, and an agent item that matches nothing is **wrong**.
- **False clears** are counted on their own: an answer of `supports` where the key says `contradicts` or `unsure`, and an expense in Evidence complete where the key says otherwise. A charge the accountant accepted is never Evidence complete.

## 15. The sample grant

One small synthetic grant that every area tests against. It's a test fixture, not one of the samples a user can open ([0027](decisions/0027-sample-grants.md)). It follows the extension-notice example in [product.md](product.md#demo-data-examples). The contract code carries it as a fixture, with its four documents, and tests that check the contracts against it.

**The grant:** award SYN-2300117, "Sediment Microbiome Survey of Example Bay", funded by NSF. It runs from February 1, 2023 to January 31, 2026. The award letter, dated January 10, 2023, is laid out like a real NSF award notice (see [domain.md](domain.md#what-an-nsf-award-notice-contains)). It gives:

- its funding amounts: amendment 000, a new project, with $120,000 obligated by this amendment and $120,000 obligated to date
- a budget. Only the lines that hold money are shown:

  | Line | Amount |
  |---|---|
  | F. Participant Support Costs | $20,000 |
  | G. Other Direct Costs | $100,000 |
  | Materials and Supplies, a sub-line of G | $40,000 |
  | Other, a sub-line of G | $60,000 |
  | H. Total Direct Costs | $120,000 |

  Each line and sub-line is a `budget_line` term, so there are four: Participant Support Costs $20,000, Other Direct Costs $100,000, Materials and Supplies $40,000, and Other $60,000. The sample treats Total Direct Costs as a sum, not a term. It has no indirect costs, which FundTrail doesn't cover for now.
- three people: Dr. Robin Example, Principal Investigator. Dr. Jesse Sample, Program Officer. Casey Placeholder, Grants Officer.
- one approval rule: Participant Support Costs need the Program Officer's approval through Research.gov

That's 10 terms: the period, four budget lines, three people, one approval rule and the funding amounts.

**The ledger:**

| Line | Cost date | Posted | Amount | Description | Account | Vendor | Reference |
|---|---|---|---|---|---|---|---|
| L-1001 | Nov 12, 2025 | Nov 14, 2025 | $1,240.00 | Sediment core liners | 55016 Lab Instruments and Supplies | Example Lab Supply Co. | INV-1001 |
| L-1002 | Feb 20, 2026 | Feb 24, 2026 | $2,180.00 | Sediment DNA sequencing run 7 | 59009 Recharge-Other Expenses | Example Sequencing Core | SEQ-0207 |

The sequencing core is a campus core facility, so L-1002 is an internal recharge. The sample assumes recharges fall under Other, the sub-line of Other Direct Costs.

**The documents.** Four plain-text files. Text and email are cited by character range, so every citation is a `char_location`:

| File | How it arrives | What it is |
|---|---|---|
| `award_letter.txt` | Upload | The award letter, with the terms above |
| `invoice_1001.txt` | Upload | Invoice INV-1001 from Example Lab Supply Co., dated November 12, 2025: "Sediment core liners, 50 count", total $1,240.00 |
| `sequencing_statement.eml` | Gmail, from the PI | An email carrying usage statement SEQ-0207 from Example Sequencing Core, dated February 20, 2026: "Sediment DNA sequencing, run 7, 48 samples", total $2,180.00. It states an amount, so it's read as a `bill`. |
| `extension_notice.txt` | Drive | The extension notice, dated January 15, 2026 |

The people's email addresses are `robin.example@university.example`, `jesse.sample@funder.example` and `casey.placeholder@funder.example`.

**The checklists.** Each charge's checklist has one item, its account group's default, and the charge's link fills it.

| Line | Account group | Default item | Filled by | Assigned budget line |
|---|---|---|---|---|
| L-1001 | Supplies | A bill that adds up to the charge | The invoice, linked for $1,240 | Materials and Supplies |
| L-1002 | Internal recharges | The facility's usage statement | The statement, linked for $2,180 | Other |

The sample has the usage statement item carry the charge's amount, so its link carries $2,180 and the sums balance.

**What the sample leaves out.** The extension notice carries no amendment number, because where a notice that adds no money records it isn't settled.

**What happens:**

| Clock (UTC) | What happens |
|---|---|
| 2023-01-12 | The award letter is uploaded. The agent writes 10 terms, and the accountant confirms them. |
| 2025-11-12 | Invoice INV-1001 is uploaded and waits, unlinked. |
| 2025-11-14 | Ledger line L-1001 arrives. The agent links the invoice for $1,240, assigns it to Materials and Supplies, and answers Allowable: supports. |
| 2026-02-21 | The PI emails the sequencing core's usage statement, and it waits. |
| 2026-02-24 | Ledger line L-1002 arrives, for work done after the end date. The agent links the statement for $2,180, assigns it to Other, the sub-line of Other Direct Costs, and answers Allowable: supports. |
| 2026-04-09 | The extension notice, dated January 15, 2026, turns up in Drive. It moves the end date to January 31, 2027. |
| 2026-04-10 | The accountant confirms the new end date. |

**Expected buckets,** checked at noon UTC on November 14, 2025 and February 24, 2026, and at 17:00 UTC on April 10, 2026:

- **L-1001 is Evidence complete throughout.** Its date is inside the period, its one item is filled and adds up, no approval rule applies, and its account group's category, Materials and Supplies, is the line it's assigned to.
- **L-1002 is Possible conflict once it arrives,** resting on the award letter's period. Its item is filled, and its account group's category, Other, is the line it's assigned to, so the date is its only failing check. Between the extension's arrival and its confirmation it stays Possible conflict, because the old end date stays in force until the new one is confirmed. After the confirmation it's Evidence complete, resting on the extension, with no agent call: its Allowable answer didn't rest on the end date.
- **The grant has no problem of its own.** Spending of $3,420 is under the $120,000 limit, and no budget line is overspent. The agent has no reason to flag the extension notice, which is dated 16 days before the old end date.

**What the tests check:** that the sample grant fits the contracts, that every passage is copied exactly from its document, that every record passes the write check when replayed in order, that the sums balance, that the ledger file matches the charges, and that the answer key scores all right against the sample grant's own agent records. Everything in it is synthetic.

## Not decided yet

| Item | Who settles it |
|---|---|
| The names and fields of the newer records: the rate term, the funding notice's amounts, the checklist item and its removal, the accepted reason, the snooze, the dispute, the duplicate mark, the flag on a record or file, and the thread messages table | contract |
| The newer fields on existing records: how a link names the checklist item it fills, how a link or a removal names a default item that isn't stored, the note's period, the bill's document number, the citation's match and highlight position, and how a box on a photo is stored | contract |
| How a `budget_line` records that it's a sub-line of a category, and whether the totals a notice prints, such as Total Direct Costs, are terms. The sample grant treats them as sums. | contract |
| Where a notice that adds no money, such as a no-cost extension, records its amendment number | contract |
| How the budget check treats indirect costs. They're out for now, so comparing spending with the award's limit is only as complete as the ledger. | product, later |
| How a funding notice's own budget lines combine with the lines already confirmed | contract |
| How a problem on the grant itself is carried in the checks' output | contract |
| How the agent's recognizing something on NSF's standing list is recorded, so the approval item goes on the checklist, and how an answer names the rule it used | contract |
| The exact list of the agent's writes that wait, as code enforces it | contract |
| How the accountant confirming or retyping an unconfirmed value is stored. A confirmation that lists the record is the working choice. | contract |
| Whether a duplicate mark joins two facts or two files | contract |
| What each screen gets from the server: a charge page, the grant page, an evidence card and a thread. The docs decide it, and nothing waits on the mockup. | product, then contract |
| How Procrastinate's jobs relate to the `agent_runs` table. Procrastinate keeps its own job tables, and `agent_runs` is the app's own record of each run. | contract |
| Whether new evidence has to be something the agent's new answer points at, by quoting it or resting on it, or whether anything that arrived since is enough | contract |
| Whether a correction to a record the agent's answer rested on also counts as new evidence. The rule as decided doesn't count it. | product |
| Whether a question has one answer in force at a time. A charge could still have several flags. | contract |
| What a snooze and an accepted reason record so code can tell a new problem and changed facts apart. Suggested: the reasons a snooze covered, and the records an accepted reason rested on. | contract |
| A bill and a charge have one link in force at a time. Still open: whether the same bill can have a second link in force to the same charge when it fills a different checklist item. | contract |
| Whether a copy can still be linked while its duplicate mark waits | contract |
| Whether a thread can be about a file that has no record | contract |
| How reasons name "the same problem", so a reusable note can be matched to a later charge | contract |
| How the answer key expresses checklist items, suggestions, disputes and unconfirmed values | contract |
| The exact table of account codes, groups and NSF budget categories (see [domain.md](domain.md#not-decided-yet)) | builder (W2), discussed with Alex before building |
| How reversals and cost transfers show in buckets and at closeout, beyond their default checklist. Berkeley's 120-day limit on cost transfers is discussed with it. | product |
| Whether a later change reopens a sign-off, and how the reviewer is recorded | product |
| Whether the agent's corrections to its own facts (not links) wait for the accountant. This design makes them wait. | product |
| A cost shared by two grants while each grant is isolated: the invoice arrives on both grants as two files, and each grant links its own copy for its part. Each copy then shows the other grant's part as money never charged. How to show that without a false alarm. | product, needs discussing |
| Letting grants share evidence and links instead of being isolated | later |
| How code matches an approval rule's `applies_to`, as the award letter words it, to the charge's assigned budget line | builder (W2) |
| The details behind who decides what, which questions code asks, and when an `other_term` is in force. Agreed for now, to look at in more detail later. | product, later |
| An amendment that states only a length, such as "extended 12 months". The term holds a stated end date, so this would need a new field. | contract, if a demo document needs it |
| The agent's exact actions and the wording of its prompts. Needs design work, as its own task, with or without the eval (see [architecture.md](architecture.md#the-agent)). | builder (W1), discussed with Alex before building |
| How a file's own date is filled in for files that aren't emails | builder (W3) |
| Columns or tables for mail held from unknown senders | builder (W4 with W3), through a contract PR |
| The eval case's arrival schedule: when each file arrives | builder (W3) |
| The clock's routes and fields, per grant: where a grant's clock and a sample grant's simulated "now" are stored, and the routes that read and move it ([0028](decisions/0028-one-clock-per-grant.md)) | contract |
| How the checks' input, which takes a whole workspace at one `now`, works when each grant has its own clock | contract |
| The membership list: its names, fields and roles ([0029](decisions/0029-workspace-members-and-one-access-check.md)) | contract |
| A sample grant's timeline and its items to deliver: how the scheduled events are stored and released, and what the timeline panel reads ([0027](decisions/0027-sample-grants.md)) | contract |
| The saved prerun and its copy: what's saved, and how opening it copies the grant into a workspace and points past decisions at that workspace's sample accountant ([0027](decisions/0027-sample-grants.md)) | contract |
