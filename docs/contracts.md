# Contracts

Contracts are the seams between workstreams. Once one is agreed, each side can build without waiting for the other. The design behind them is in [decisions/0009](decisions/0009-agent-judges-code-checks.md).

**Status:** written as code. Alex and Grant approve changes together.

## Where contracts live

The code is the truth. This file explains it.

| Contract | Lives in |
|---|---|
| Record format, links, judgments | [`records.py`](../backend/app/contracts/records.py) |
| Charges and the ledger file | [`charges.py`](../backend/app/contracts/charges.py) |
| Evidence files | [`evidence.py`](../backend/app/contracts/evidence.py) |
| Checks interface | [`checks.py`](../backend/app/contracts/checks.py) |
| Agent runs | [`runs.py`](../backend/app/contracts/runs.py) |
| API bodies | [`api.py`](../backend/app/contracts/api.py), and the endpoint list below. The frontend generates its TypeScript types from FastAPI's OpenAPI schema. |
| Eval answer key | [`eval.py`](../backend/app/contracts/eval.py) |
| Database tables | [`20261109000000_contracts.sql`](../supabase/migrations/20261109000000_contracts.sql) |
| Golden fixture | [`fixtures/golden/`](../backend/app/contracts/fixtures/golden/) |

## Changing a contract

1. Open a PR that changes the contract. Both Alex and Grant approve it.
2. In the same PR, update the code that uses it so main stays green, or have both owners agree on who follows up.
3. If the change alters behavior or direction, add a file to [decisions/](decisions/).

## Conventions

- IDs are strings. User IDs are Supabase auth UUIDs.
- Timestamps are timezone-aware and stored in UTC. Records carry the workspace clock's "now".
- Money is an integer number of cents in US dollars. Credits are negative.
- Contract models reject unknown fields and can't be changed after they're created.

## 1. Records

A record is one thing the agent or the accountant wrote. It's never edited. A correction is a new record whose `replaces_id` points to the old one, and the old one stays. Every record has an envelope: `id`, `workspace_id`, `grant_id`, `author` (`agent` or `user`), `author_user_id` (set exactly for `user`), `written_at` (the clock's "now") and `replaces_id`. Its `data` is one of these kinds:

| Group | Kind | Fields | Who writes it |
|---|---|---|---|
| Grant terms | `period_of_performance` | `start`, `end` | Agent or accountant |
| | `budget_line` | `name`, `amount` | Agent or accountant |
| | `person` | `name`, `email`, `role` | Agent or accountant |
| | `approval_rule` | `applies_to`, `approver`, `channel` | Agent or accountant |
| | `other_term` | `label`, `statement` | Agent or accountant |
| Facts from evidence | `receipt` | `vendor`, `total`, `dated`, `description`, `items` (each a `description` and an `amount`) | Agent or accountant |
| | `approval` | `approver_email`, `approver_name`, `approved_on`, `covers`, `channel` | Agent or accountant |
| | `note` | `label`, `statement` | Agent or accountant |
| Links and answers | `link` | See section 2 | Agent or accountant |
| | `judgment` | See section 3 | Agent or accountant |
| The accountant only | `confirmation` | `record_ids`, `decision` (`confirmed` or `rejected`) | Accountant |
| | `sign_off` | `note` | Accountant |
| Either | `retraction` | `reason`. Replaces a record with nothing. | Agent or accountant |

A record kind earns its place only if a check reads it or the evidence report shows it. Don't add kinds beyond that.

Every term also has `dated`: the date the document gives itself, such as an amendment's date. An amendment isn't a correction. It's a new term, and the checks use `dated` to decide which terms are in force. `other_term` holds anything an award letter or amendment says that no other kind holds, such as a principal investigator (PI) on leave. It's in force from its own date on, and the agent reads any dates inside its statement. A `note` is evidence that explains a charge without billing or approving it, such as a payment notice saying which invoices a payment covered.

### Cited values

A value read from a document is a cited value: `value`, `text` (the value exactly as the document writes it) and `citation`. The text has to appear in the citation's passage (trust rule 2). The agent always cites. A value the accountant enters has no citation.

A citation holds the `file_id`, the `passage` and its `location`. Locations use the Anthropic API's own names and counting, so the agent copies them over unchanged: `char_location` (plain text), `page_location` (PDFs with real text) and `content_block_location` (custom content documents). For a photo or scan, the location is an `image_box`, the box the agent estimated, as fractions of the page from its top left corner, and there's no passage.

### What counts

- **Some of the agent's records wait for the accountant.** Its grant terms, and any record that replaces an existing record (a suggested fix, including removing a link with a retraction), count only once a `confirmation` lists them with `confirmed`. The one exception: a judgment replacing the agent's own earlier judgment counts right away. The latest decision on a record wins, and a rejected record never counts. Only link fixes were discussed; applying the same rule to the agent's corrections of its own facts is an open product question (see "Not decided yet").
- **The agent can suggest a fix to one of the accountant's links,** which waits like any fix. It never replaces any other record of theirs, including their answers.
- **Several records may replace the same one,** because the agent's suggested fixes wait. The accountant confirms at most one.
- **Current records** are the records that count, minus those an effective record replaces, minus retractions.

Code: `needs_confirmation`, `decisions`, `effective_records`, `current_records` and `waiting_records` in `records.py`. Pass them only the records visible at the clock's "now".

### Checking a write

`check_new_record(new, records, charges)` returns a list of problems in plain sentences, or nothing if the record can be saved. The backend runs it on every write, and the agent sees the problems so it can fix them. It checks that:

- every quoted value appears in its passage
- the records and charges a record points to exist, and the records are current
- the agent replaces none of the accountant's records except their links, and a replacement is the same kind or a retraction
- a link points to a receipt, approval or note, has an amount exactly when it points to a receipt, and its part is in the linked record's own file
- a judgment's question is about the right kind of record
- a confirmation lists only records that wait for one

## 2. Links

A link ties a fact to a charge. It's a record of kind `link`, and it's its own concept everywhere: in the code, the API, the screens and these docs.

| Field | What it holds |
|---|---|
| `record_id` | The receipt, approval or note. The database enforces that it exists. |
| `charge_id` | The charge. The database enforces that it exists. It may be on another grant in the workspace. |
| `amount_cents` | For a receipt only: how much of the receipt this charge uses. Negative for a credit. |
| `part` | A citation: the place in the record's own file that pertains to this charge, highlighted when the user opens it. For a whole receipt, it's the total's citation. The agent always gives one. |
| `reason` | Optional: one line on why they match |

The meaning comes from the record: a receipt link means "pays for", an approval link "approves", and a note link "explains". A split is one receipt linked to several charges, each link with its amount and part, such as an itemized line. There's no separate split record. When an email gives the basis instead, such as "56 of the 96 samples are for grant 1", the email is read as a `note` and linked to each charge, because a link's part has to be in its own record's file.

**A waiting fix.** While a fix the agent suggested waits for the accountant, every charge it touches is in Needs a human, showing the suggestion. The old link stays in force until the accountant confirms the fix.

**The two sums.** Code checks them on every change:

- **Per receipt:** its links add up to at most its total.
- **Per charge:** the receipt links to it add up to the charge amount, exactly.

| | Under | Over |
|---|---|---|
| **A charge's links** | Missing evidence. Not flagged until the closeout window (section 6). | Needs a human |
| **A receipt's links** | Not a problem while the grant runs: the rest waits for a charge. From the closeout window, a grant note lists it: "Invoice 2050: $5,000 never charged." | Needs a human, on every charge using the receipt |

The agent writes the links it believes are right, even when one pushes a sum over. It never skips or shrinks a link to make a sum fit.

## 3. Judgments and questions

Code checks the clear-cut rules itself. For what it can't settle, it asks a question about a charge, and the answer is stored as a `judgment` record.

| Question | When code asks it |
|---|---|
| `allowable`: "Is this cost necessary and reasonable, and is it for this project?" | Every charge that has evidence linked |
| `covers`: "Does this approval cover this charge?" | When an approval rule applies to the charge and an approval is linked. `record_id` is the approval. Whether a rule applies depends on the charge's budget line, which the agent decides; where that's stored is still open. |
| `unusual_term`: "Does this term change anything for this charge?" | Once for each confirmed `other_term` in force on the charge's date. `record_id` is the term. |
| `flag`: the agent's own question | Whenever the agent sees something no other question covers. The agent's answer is always `unsure`, and the accountant settles it by answering it. |

A judgment holds `charge_id`, `question`, `record_id`, `text` (the question as asked), `answer`, `reasoning`, `quotes` (citations) and `rests_on` (the record IDs the answer depends on). The answers map to buckets: `supports` passes, `contradicts` is Possible conflict, and `unsure` is Needs a human. The reasoning is shown in the app and the evidence report, labeled with who wrote it.

- **Safety rule:** the agent can only clear a question code asked. A required question with no current answer is an open question, and it puts the charge in Needs a human.
- **When the agent answers again:** when something new is linked to the charge, when a record its answer rests on is corrected or retracted, or when a new `other_term` or approval rule covering the charge's date is confirmed. Not when the clock moves or an amount, a budget or a period changes.
- **Out of date.** Code treats an answer as out of date when a link to its charge was written after it, or a record it rests on is no longer current. A new question appears when a new term or rule makes one required. While the agent is answering again, the charge keeps its last answer for the bucket and is marked `rechecking`. With no answer yet, the charge is in Needs a human.
- **The accountant** answers what the agent was unsure about, and can overrule any judgment by writing their own that replaces it. Once the accountant has answered, an out-of-date answer goes back to the accountant, not the agent, and the charge is in Needs a human until they answer again.

## 4. Charges

One charge comes from one ledger line, read by code. The agent never writes charges.

| Field | Notes |
|---|---|
| `ledger_line_id` | Unique within a workspace. The same line twice adds nothing. |
| `transaction_date` | When the cost happened. The checks use this one. |
| `posting_date` | When the ledger recorded it |
| `arrived_at` | When it reached FundTrail. The clock uses this one. For an uploaded ledger file, 00:00 UTC on the posting date. |
| `amount_cents` | Negative for a reversal, a transfer out or a credit |
| `description`, `account`, `vendor`, `reference` | As the ledger gives them |
| `original_line_id` | For a reversal or cost transfer: the `ledger_line_id` of the line it undoes or moves. It's a line ID, not a charge ID, because the original may be on another grant or arrive later. |

## 5. Evidence files

The original is stored as it arrived, in the private Supabase Storage bucket `evidence`, at `{workspace_id}/{grant_id}/{file_id}/{name}`.

| Field | Notes |
|---|---|
| `grant_id` | One grant per file for now. Files move to the workspace level later. |
| `source` | `gmail`, `drive` or `upload` |
| `name`, `media_type`, `storage_path`, `sha256` | The fingerprint catches duplicates |
| `document_date` | The file's own date when the source gives one, such as an email's sent date. A date written inside the document is a cited value on a record instead. |
| `arrived_at` | When it reached FundTrail. The clock uses this one. |
| `sender`, `source_ref` | The sender's address for Gmail, and the Gmail message ID or Drive file ID |
| `parent_id` | For an attachment, the email it came with |

## 6. The checks' interface

```python
def run_checks(checks_input: ChecksInput) -> ChecksOutput
```

A pure function, with no database and no model inside. W2 implements it in `backend/app/checks/`; the contract version is a stub.

- **In:** `ChecksInput` holds `now` and everything in one workspace visible at that time: `charges`, `evidence` and `records`, including replaced, waiting and rejected records. It takes the whole workspace because a charge's links can come from another grant's files.
- **Out:** `ChecksOutput` holds:
  - `statuses`: one `ChargeStatus` per charge, with its `bucket`, every `Reason` (`check`, `bucket`, `text` built by code, and the `record_ids` it rests on), `flagged`, and `rechecking`
  - `questions`: every required question without a current answer, as an `OpenQuestion` with `answer_by` (the agent, or the accountant when they answered before)
  - `grant_notes`: anything about the grant as a whole, such as a receipt with money never charged
- **The bucket** is the most serious bucket among the reasons, in the order Possible conflict, Needs a human, Missing evidence, Evidence complete. `ChargeStatus` rejects anything else.
- **Flagged** means the charge is on the accountant's problem list. Possible conflict and Needs a human are always flagged. Missing evidence is flagged only from `CLOSEOUT_WINDOW_DAYS` (90) before the grant's end date, when Berkeley sends its first Notice of Expiration. Until then the charge sits in Missing evidence, off the problem list.
- **Status history:** a `StatusEntry` row is written each time a charge's status changes, with `changed_at` and its `trigger`: a record, a charge, a file, or the clock. For a change that comes from saving an agent run, the trigger is what started the run, for example "invoice 1001 arrived".

## 7. Agent runs

A run is one background job. It's queued each time a charge or an evidence file arrives, each time one of the accountant's records leaves a question open for the agent (for example confirming an `other_term`, or approving a fix that adds a link), and once per grant when the closeout window opens, to review all the grant's links (trigger `clock`). The agent works in a loop of actions: it looks at anything on the grant with no filtering, opens files, and writes records. Every write is checked with `check_new_record` as it happens, and problems go back to the agent. A run can't finish while an open question is waiting for the agent. Everything the run wrote is saved together at the end, so a run that fails saves nothing. Runs for one grant go one at a time, and the database enforces it.

`AgentRun` holds the `trigger`, the `status` (`queued`, `running`, `done` or `failed`), `clock_now` (the clock's "now" the run works at, which its records carry), real-time `queued_at`, `started_at` and `finished_at`, a short `summary` and any `error`. The exact actions the agent has are decided with its prompts (W1).

## 8. Database tables

Migration: [`20261109000000_contracts.sql`](../supabase/migrations/20261109000000_contracts.sql).

| Table | Holds |
|---|---|
| `users` | One row per Supabase auth user |
| `workspaces` | The name, the owner and the clock. `clock_now` null means the real date. |
| `grants` | The funder (National Science Foundation, NSF, only for now), award number and title |
| `charges` | `Charge` |
| `evidence_files` | `EvidenceFile` |
| `records` | The envelope as columns and `data` as JSONB (binary JSON). `kind`, `charge_id` and `record_id` are generated from `data`, and the last two are foreign keys, so the database enforces what links and judgments point to. |
| `statuses` | Status history, one row per change. The view `current_statuses` gives the latest row per charge. |
| `agent_runs` | `AgentRun`. The only table updated in place. |

- Rows match the Pydantic models, with these differences: a record row's `data` is `Record.data` dumped to JSON, and `kind`, `charge_id` and `record_id` are generated from it; a status row's `Trigger` is split into `trigger_kind` and `trigger_id`, and it adds `workspace_id`; `records` and `users` add a real-time `created_at`.
- `records`, `charges` and `statuses` reject updates. Deletes stay allowed so a workspace reset can clear them.
- The database also enforces: one charge per ledger line ID in a workspace, `author_user_id` set exactly for `user` records, a retraction replacing something, a link naming both its record and its charge, a judgment naming its charge, only the accountant writing confirmations and sign-offs, and one running agent run per grant.
- Row level security is on, with no policies. The backend uses the service role key, and the browser never reads the tables directly.

## 9. API

**Sign-in.** The browser signs in with Supabase Auth (Google) and sends the access token on every request as `Authorization: Bearer <token>`. The backend verifies the token, finds the user from it, and checks that the user owns the workspace.

Errors use FastAPI's default `{"detail": ...}` body. A write that `check_new_record` rejects returns 422 with `WriteRejected`, listing the problems.

| Method and path | Body | Returns |
|---|---|---|
| `GET /workspaces` | | `list[Workspace]` |
| `POST /workspaces` | `WorkspaceCreate` | `Workspace` |
| `POST /workspaces/{workspace_id}/reset` | | `Workspace` |
| `GET /workspaces/{workspace_id}/clock` | | `Clock` |
| `POST /workspaces/{workspace_id}/clock` | `ClockMove` | `Clock` |
| `GET /workspaces/{workspace_id}/grants` | | `list[GrantSummary]` |
| `POST /workspaces/{workspace_id}/grants` | Form with the award letter as `file` | `Grant` |
| `GET /grants/{grant_id}` | | `GrantDetail`: terms, the agent's waiting fixes, open questions for the accountant, grant notes |
| `GET /grants/{grant_id}/charges` | | `list[ChargeRow]` |
| `POST /grants/{grant_id}/ledger` | Form with the ledger file as `file` | `LedgerUploadResult` |
| `GET /grants/{grant_id}/evidence` | | `list[EvidenceCard]` |
| `POST /grants/{grant_id}/evidence` | Form with the file as `file` | `EvidenceFile` |
| `GET /grants/{grant_id}/records` | | `list[Record]`, replaced and waiting ones included |
| `POST /grants/{grant_id}/records` | `NewRecord` | `Record` |
| `GET /grants/{grant_id}/runs` | | `list[AgentRun]`, newest first |
| `GET /grants/{grant_id}/report` | | The PDF evidence report |
| `GET /charges/{charge_id}` | | `ChargeDetail`: status, history, links with their records and files, judgments, waiting fixes |
| `GET /evidence/{file_id}/content` | | `FileUrl`, a short-lived link to the original |

- Adding a grant stores the award letter and queues an agent run. The grant comes back right away, and its terms appear as the agent writes them.
- Every accountant action goes through `POST /grants/{grant_id}/records`: confirming or rejecting terms and the agent's fixes, answering or overruling a question, linking or splitting by hand, correcting or retracting a record, adding a known sender, and signing off. The server fills in the ID, author and time.
- `POST .../clock` with no `to` moves to the next arrival. The clock only moves forward.

## 10. Ledger file

Code: `LedgerRow` in [`charges.py`](../backend/app/contracts/charges.py). Example: the golden [`ledger.csv`](../backend/app/contracts/fixtures/golden/ledger.csv).

CSV or Excel, one file per grant. In the hackathon build, a seeded grant's file holds its whole history, and the clock releases each line on its posting date. The first row is a header with these names, in any order:

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

An empty cell is a missing value. Each row becomes one charge: `line_id` becomes `ledger_line_id`, `amount` becomes `amount_cents`, and `arrived_at` is 00:00 UTC on the posting date. A row whose `line_id` is already on file is skipped. Mapping another system's column names is a later addition.

## 11. Eval answer key

Code: [`eval.py`](../backend/app/contracts/eval.py). Example: the golden [`answer_key.json`](../backend/app/contracts/fixtures/golden/answer_key.json). One JSON file per case, written before the case's documents:

- `case`, and `award_number`, which must start with `SYN-`
- `records`: the facts and terms the agent should read. Each has a `kind`, a `file` (the case file it cites) and `fields`, the expected values by field path as strings: dates as `YYYY-MM-DD`, money in cents, text as written, for example `{"total": "124000", "items[0].description": "..."}`.
- `links`: each has the `file` the linked fact was read from, the charge's `line_id`, and for a receipt the `amount_cents`.
- `answers`: each has a `line_id`, a `question`, for `covers` and `unusual_term` the `about_file`, and the expected `answer`.
- `buckets`: each has a `line_id`, an `at` (a clock time after the arrival it follows) and a `bucket`.

**What counts as a match.** Over the agent's current records on the case's files:

- **Records:** a match has the same kind, cites the same file, and every listed field equals the record's value, compared as strings ignoring case and extra whitespace. Fields the key leaves out aren't compared.
- **Links:** a match links a fact from the same file to the same charge, with the same amount.
- **Answers:** a match answers the same question about the same charge (and the same file, when given).
- Each expected item matches at most one agent item. An expected item with a match is **right**, one with none is **missing**, and an agent item that matches nothing is **wrong**.
- **False clears** are counted on their own: an answer of `supports` where the key says `contradicts` or `unsure`, and an expense in Evidence complete where the key says otherwise.

## 12. Golden fixture

Files: [`fixtures/golden/`](../backend/app/contracts/fixtures/golden/). Load it with `load_golden()` and `load_golden_answer_key()` from `app.contracts.fixtures`. Grant SYN-2300117 runs from February 1, 2023 to January 31, 2026. Everything in it is synthetic.

| Clock (UTC) | What happens | Records |
|---|---|---|
| 2023-01-12 | The award letter is uploaded. The agent writes 8 terms, and the accountant confirms them. | `rec-award-*`, `rec-confirm-award` |
| 2025-11-12 | Invoice INV-1001 is uploaded and waits, unlinked | `rec-receipt-1001` |
| 2025-11-14 | Ledger line L-1001 arrives: supplies bought Nov 12, 2025. The agent links the invoice for $1,240 and answers Allowable: supports. | `rec-link-1001`, `rec-judge-1001-allowable` |
| 2026-02-21 | The PI emails the sequencing invoice, and it waits | `rec-receipt-1002` |
| 2026-02-24 | Ledger line L-1002 arrives: sequencing done Feb 20, 2026, after the end date. The agent links the invoice for $2,180 and answers Allowable: supports. | `rec-link-1002`, `rec-judge-1002-allowable` |
| 2026-04-09 | The extension notice, dated Jan 15, 2026, turns up in Drive. It moves the end date to Jan 31, 2027. | `rec-ext-period` |
| 2026-04-10 | The accountant confirms the new end date | `rec-confirm-ext` |

**Expected buckets:** L-1001 is Evidence complete throughout. L-1002 is Possible conflict once it arrives, resting on `rec-award-period`. After the confirmation it's Evidence complete, resting on `rec-ext-period`, with no agent call: its Allowable answer didn't rest on the end date. The key gives no bucket between the extension's arrival and its confirmation (see "Not decided yet").

The tests in `app/contracts/tests/` check that the fixture validates, that every passage is copied exactly from its document, that every record passes `check_new_record` when replayed in order, that the link sums balance, that the ledger file matches the charges, and that the answer key scores all right against the fixture's own agent records.

## Not decided yet

| Item | Who settles it |
|---|---|
| A charge's bucket between an amendment's arrival and the accountant's confirmation of its terms | product |
| A charge's bucket while its grant's terms aren't confirmed yet | product |
| How reversals and cost transfers show in buckets and at closeout | product |
| Whether a later change reopens a sign-off, and how the reviewer is recorded | product |
| Whether the agent's corrections to its own facts (not links) wait for the accountant. The contracts make them wait today. | product |
| Where the agent's choice of a charge's budget line is stored, for example a link from the `budget_line` term to the charge or a record kind of its own. The checks need it for budget room and for whether an approval rule applies, so W2 can't finish those checks until it's settled. The golden fixture's ledger accounts happen to match its budget line names; don't treat that as the rule. | contract, needs discussing |
| Whether the agent sees charges on the workspace's other grants when matching. A cost shared across grants needs it, but the agent was described as looking at "anything on the grant". If it does, how runs on two grants avoid linking the same receipt at once, since the lock is one run per grant. | contract, needs discussing |
| How trust rule 2 checks values read from photos and scans now that one receipt can pay part of a charge, or several charges. Before links had amounts, such a value had to match its ledger line. | contract, needs discussing |
| An amendment that states only a length, such as "extended 12 months". The term holds a stated end date, so this would need a new field. | contract, if a demo document needs it |
| The agent's exact actions and prompts. Needs design work, as its own task, with or without the eval (see [architecture.md](architecture.md#the-agent)). | builder (W1) |
| How a file's own date is filled in for files that aren't emails | builder (W3) |
| Columns or tables for mail held from unknown senders | builder (W4 with W3), through a contract PR |
| The eval case's arrival schedule: when each file arrives | builder (W3) |
