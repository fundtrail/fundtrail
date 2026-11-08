# Contracts

Contracts are the seams between workstreams. Once one is agreed, each side can build without waiting for the other.

**Status:** filled in by the contracts PR. Alex and Grant approve it together. Target freeze: **Sun Nov 8, 10 AM PT.** After that, changes follow "Changing a contract" below.

## Where contracts live

The code is the truth. This file explains it and links to it.

| Contract | Lives in |
|---|---|
| Records, charges, evidence files, the checks' interface, ledger rows, the answer key | Pydantic models in [`backend/app/contracts/`](../backend/app/contracts/) |
| Database tables | [`supabase/migrations/20261108000000_contracts.sql`](../supabase/migrations/20261108000000_contracts.sql) |
| API | The endpoint list below, with request and response models in [`api.py`](../backend/app/contracts/api.py). W4 writes the FastAPI routes in `backend/app/api/`. The frontend generates its TypeScript types from FastAPI's OpenAPI schema, so a backend change shows up as a type error instead of a silent mismatch. |
| Golden fixture | [`backend/app/contracts/fixtures/golden/`](../backend/app/contracts/fixtures/golden/) |

The contract tests run from `backend/` with `python -m pytest app/contracts`.

## Changing a contract

1. Open a PR that changes the contract. Both Alex and Grant approve it.
2. In the same PR, update the code that uses it so main stays green, or have both owners agree on who follows up.
3. If the change alters behavior or direction, add a file to [decisions/](decisions/).

## Conventions

- IDs are text. A user's ID is their Supabase auth UUID (universally unique identifier).
- Timestamps carry a time zone and are stored in UTC (Coordinated Universal Time). Show clock dates in UTC, so a line that arrives at 00:00 UTC doesn't display as the day before.
- Money is an integer number of cents, in US dollars. Credits are negative.
- Dates without a time are written `YYYY-MM-DD`.
- Every model rejects unknown fields and can't be changed after it's created.

## 1. Records

Code: [`records.py`](../backend/app/contracts/records.py).

**Decided:**

- Records are the single source of truth. A record is never edited. A correction is a new record that replaces the old one, and the old one stays.
- The agent and the accountant both write records. Every record says who wrote it and when, using the clock's date.
- A fact pulled from a document carries its citation:
  - the document
  - the passage, copied by the API and never typed by the model
  - where the passage sits: a page number, a character range or a block index, or, for photos and scans, the box Claude estimated
- Records about grant terms (dates, budget lines, people and roles, approval rules) come from the award letter and amendments. The accountant confirms them before any check uses them.
- The agent never writes a status. Status, reasons and status text all come from the checks.

**Every record has:**

| Field | Meaning |
|---|---|
| `id`, `workspace_id`, `grant_id` | Where it belongs. A split belongs to the grant it was entered from, and its parts may be on other grants. |
| `author` | `agent` or `user`. `author_user_id` is set exactly when it's `user`. |
| `written_at` | The workspace clock's "now" when it was written |
| `replaces_id` | The record this one corrects, if any |
| `data` | The fields for its kind, including `kind` |

**Kinds:**

| Kind | Fields | Typical source |
|---|---|---|
| `period_of_performance` | `start` (optional), `end` | Award letter, amendment |
| `budget_line` | `name`, `amount` | Award letter, amendment |
| `person` | `name`, `email` (optional), `role` as the document states it | Award letter, or a known sender the accountant adds |
| `approval_rule` | `applies_to`, `approver`, `channel` (optional), all as stated | Award letter |
| `link` | `file_id`, `charge_id` | The agent tying a file to the charge it supports |
| `receipt` | `vendor`, `amount`, `dated`, `description`, all optional | Receipt, invoice |
| `approval` | `approver_email`, `covers`, and optionally `approver_name`, `approved_on`, `channel` | Approval email, Research.gov record |
| `split` | `unit`, `parts` (two or more, each a charge and its units), `note` | The accountant |
| `confirmation` | `record_ids` | The accountant confirming terms |
| `sign_off` | `note` | The accountant signing off on the packet |
| `retraction` | `reason`, and `replaces_id` must be set | Removing a wrong record, such as a wrong link |

- The first four kinds are grant terms. Each term also has an optional `dated`: the date the document gives itself, such as an amendment's date.
- Only a person writes `split`, `confirmation` and `sign_off`.
- A split of "56 of 96 samples" is two parts, 56 and 40, with unit "samples". Code does the math.

**Cited values.** Every fact field is a cited value with three parts:

- `value`: the parsed value, which is text, a date or cents
- `text`: the value exactly as the source writes it. Code checks that it appears in the citation's passage (trust rule 2).
- `citation`: where it came from

Every value the agent writes has all three. A value a person enters has only `value`.

**Citations** have a `file_id`, a `passage` and a `location`. The `passage` is the API's `cited_text`, copied as is, and it's empty for photos and scans. The `location` uses the Anthropic API's own names and counting, so the agent copies it over unchanged:

| `type` | For | Fields |
|---|---|---|
| `char_location` | Plain text | `start_char_index`, `end_char_index`: from 0, end exclusive |
| `page_location` | PDFs with real text | `start_page_number`, `end_page_number`: from 1, end exclusive |
| `content_block_location` | Custom content documents | `start_block_index`, `end_block_index`: from 0, end exclusive |
| `image_box` | Photos and scans | `page` from 1, then `left`, `top`, `width`, `height` as fractions of the page, from its top left corner |

**Replacing a record.**

- A correction is a new record whose `replaces_id` points to the old one. The old one stays.
- A record is current when no visible record replaces it. `current_records()` applies this.
- At most one record replaces a given record, so corrections form a single line.
- A `retraction` replaces a record with nothing.
- An amendment isn't a correction. An extension notice adds a new `period_of_performance` record with its own `dated`, and the original stays current. The checks use `dated` to decide which terms are in force.

**Confirming terms.** A term the agent wrote counts once a current `confirmation` lists it. A term a person wrote needs no confirmation. `confirmed_term_ids()` applies this.

**Facts and charges.** Facts belong to the file they were read from. A `link` ties a file to a charge, and the file's facts then apply to that charge. A file is unlinked while no link points to it and no term cites it.

## 2. Charges

Code: `Charge` in [`charges.py`](../backend/app/contracts/charges.py).

**Decided:**

- One charge comes from one ledger line, read by code. The agent never writes charges.
- Each line is matched by its ledger line ID, so syncing or uploading the same line twice adds nothing.
- Each line has a transaction date, which the checks use, a posting date, and an arrival date, which the clock uses.
- Corrections arrive as new lines (reversals, cost transfers). Nothing is edited.

**Fields:**

| Field | Meaning |
|---|---|
| `ledger_line_id` | Unique within a workspace |
| `transaction_date` | When the cost happened. The checks use it. |
| `posting_date` | When the ledger recorded it |
| `arrived_at` | When the line reached FundTrail. The clock uses it. For an uploaded ledger file, it's 00:00 UTC on the posting date. |
| `amount_cents` | Negative for a reversal or a transfer out |
| `description`, `account` | As the ledger gives them. `account` is the expense account or category. |
| `vendor`, `reference` | Optional. `reference` is an invoice or document number. |
| `original_line_id` | For a reversal or a cost transfer (below) |

**Reversals and cost transfers.** The new line's `original_line_id` holds the `ledger_line_id` of the line it undoes or moves. It's a ledger line ID, not a charge ID, because the original may sit on another grant in the same workspace, or arrive later. A cost transfer from grant A to grant B arrives as a negative line on A and a positive line on B, and both point to the original line.

## 3. Evidence files

Code: `EvidenceFile` in [`evidence.py`](../backend/app/contracts/evidence.py).

**Decided:**

- The original file is stored as it arrived.
- Each file has a source (Gmail, Drive or upload), its own date and an arrival date.
- A file can be unlinked: it waits until the agent links it to a charge or a grant term.

**Fields:**

| Field | Meaning |
|---|---|
| `source` | `gmail`, `drive` or `upload` |
| `name`, `media_type` | The file name, and its media type, such as `application/pdf` |
| `storage_path`, `sha256` | Where the original sits, and a hash of its bytes |
| `document_date` | Its own date when the source gives one, such as an email's sent date. A date stated inside a document is a cited value on a record instead. |
| `arrived_at` | When it reached FundTrail. The clock uses it. |
| `sender` | The sender's address, for Gmail |
| `source_ref` | The Gmail message ID or Drive file ID |
| `parent_id` | For an attachment, the email file it came in |

**Storage.** Originals go in the private Supabase Storage bucket `evidence`, at `{workspace_id}/{grant_id}/{file_id}/{name}`. The migration creates the bucket.

## 4. The checks' interface

Code: [`checks.py`](../backend/app/contracts/checks.py).

**Decided:** the checks are a pure function. They take everything visible at the clock's "now" (the confirmed terms, the charges and the records) and return each charge's bucket, with its reasons and the records each reason rests on. There's no database and no model inside, so the checks can be tested from day one with hand-written records.

**Signature:**

```python
def run_checks(checks_input: ChecksInput) -> ChecksOutput
```

- `ChecksInput` holds `now`, plus the workspace's `charges`, `evidence` and `records` that are visible at `now`. The caller filters them by arrival and by `written_at`. The records include replaced ones, and the checks call `current_records()` and `confirmed_term_ids()` themselves. The input covers the whole workspace, because a split can span grants.
- `ChecksOutput.statuses` holds one `ChargeStatus` per charge: `charge_id`, `bucket` and `reasons`.
- Each `Reason` has `check` (a stable ID), `bucket` (where this check puts the charge, `evidence_complete` for a pass), `text` (status text built by code) and `record_ids` (the records it rests on). Passing checks are listed too, so an Evidence complete status can cite the new end date.
- A charge's `bucket` is the most serious bucket among its reasons, and the model enforces it. From most to least serious: `possible_conflict`, `needs_human`, `missing_evidence`, `evidence_complete`.
- The stub in `checks.py` raises `NotImplementedError`. W2 implements it in `backend/app/checks/` with the same signature, and callers import it from there.

**Status history.** A `StatusEntry` is a `ChargeStatus` plus `changed_at`, the clock time, and a `trigger`: a `record` was written, a `charge` arrived, or only the `clock` moved, with the record's or charge's ID.

## 5. Database tables

Migration: [`20261108000000_contracts.sql`](../supabase/migrations/20261108000000_contracts.sql).

| Table | Holds |
|---|---|
| `users` | One row per Supabase auth user |
| `workspaces` | The name, the owner and the clock. `clock_now` is the clock's "now", and null means the real date. |
| `grants` | The funder (NSF only for now), award number and title |
| `charges` | `Charge` |
| `evidence_files` | `EvidenceFile` |
| `records` | The record's envelope as columns, and `data` as JSONB (binary JSON). `kind` is generated from `data`. |
| `statuses` | Status history, one row per change. The view `current_statuses` gives the latest row per charge. |

- Rows match the Pydantic models field for field. A record row's `data` is `Record.data` dumped to JSON.
- `records`, `charges` and `statuses` reject updates. Deletes stay allowed so a workspace reset can clear them.
- The database also enforces one charge per ledger line ID in a workspace, at most one record replacing another, a retraction replacing something, and `author_user_id` being set exactly for `user` records.
- Row level security is on, with no policies. The backend uses the service role key, and the browser never reads the tables directly.

## 6. API

**Sign-in.** The browser signs in with Supabase Auth (Google) and sends the access token on every request as `Authorization: Bearer <token>`. The backend verifies the token, finds the user from it, and checks that the user owns the workspace.

Errors use FastAPI's default `{"detail": ...}` body. The request and response models are in [`api.py`](../backend/app/contracts/api.py).

| Method and path | Body | Returns |
|---|---|---|
| `GET /workspaces` | | `list[Workspace]` |
| `POST /workspaces` | `WorkspaceCreate` | `Workspace` |
| `POST /workspaces/{workspace_id}/reset` | | `Workspace` |
| `GET /workspaces/{workspace_id}/clock` | | `Clock` |
| `POST /workspaces/{workspace_id}/clock` | `ClockMove` | `Clock` |
| `GET /workspaces/{workspace_id}/grants` | | `list[GrantSummary]` |
| `POST /workspaces/{workspace_id}/grants` | Form with the award letter as `file` | `Grant` |
| `GET /grants/{grant_id}` | | `GrantDetail` |
| `GET /grants/{grant_id}/charges` | | `list[ChargeRow]` |
| `POST /grants/{grant_id}/ledger` | Form with the ledger file as `file` | `LedgerUploadResult` |
| `GET /grants/{grant_id}/evidence` | | `list[EvidenceCard]` |
| `POST /grants/{grant_id}/evidence` | Form with the file as `file` | `EvidenceFile` |
| `GET /grants/{grant_id}/records` | | `list[Record]`, replaced ones included |
| `POST /grants/{grant_id}/records` | `NewRecord` | `Record` |
| `GET /grants/{grant_id}/packet` | | The PDF packet |
| `GET /charges/{charge_id}` | | `ChargeDetail` |
| `GET /evidence/{file_id}/content` | | `FileUrl`, a short-lived link to the original |

- Adding a grant stores the award letter and starts the agent. The grant comes back right away, and its terms appear as the agent writes them.
- Every accountant action goes through `POST /grants/{grant_id}/records`: confirming terms, entering a split, adding a known sender, correcting or retracting a record, linking a file by hand, and signing off. The server fills in the ID, author and time.
- `POST .../clock` with no `to` moves to the next arrival. The clock only moves forward.

## 7. Ledger file

Code: `LedgerRow` in [`charges.py`](../backend/app/contracts/charges.py). Example: the golden [`ledger.csv`](../backend/app/contracts/fixtures/golden/ledger.csv).

**Decided:** CSV or Excel, one file per grant. In the hackathon build, a seeded grant's file holds its whole history, and the clock releases each line on its posting date.

The first row is a header with these names. Columns can come in any order.

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

**Mapping.** The hackathon build reads these exact header names from a CSV (comma-separated values) file, or from the first sheet of an Excel file. An empty cell is a missing value. Each row becomes one charge: `line_id` becomes `ledger_line_id`, `amount` becomes `amount_cents`, and `arrived_at` is 00:00 UTC on the posting date. A row whose `line_id` is already on file is skipped. Mapping another system's column names is a later addition.

## 8. Eval answer key

Code: [`eval.py`](../backend/app/contracts/eval.py). Example: the golden [`answer_key.json`](../backend/app/contracts/fixtures/golden/answer_key.json).

**Decided:** for each expense, the records the agent should write and the bucket the expense should have after each arrival.

**Format.** One JSON file per case:

- `case`, and `award_number`, which must start with `SYN-`
- `records`: the records the agent should write. Each has a `kind`, a `file` (the case file it cites or, for a link, the file it links) and `fields`, the expected values as strings: dates as `YYYY-MM-DD`, money in cents, text as written. A link's fields are `{"charge": "<ledger line ID>"}`.
- `buckets`: each has a `line_id`, an `at` (a clock time after the arrival it follows) and a `bucket`.

**What counts as a match.** An agent record matches an expected record when it has the same kind, cites (or links) the same file, and every listed field equals the record's value. Values are compared as strings, ignoring case and extra whitespace. Fields the key leaves out aren't compared. Each expected record matches at most one agent record. Then, over the agent's current records on the case's files:

- **Right:** an expected record with a match
- **Missing:** an expected record with no match
- **Wrong:** an agent record that matches nothing, such as a wrong value or an extra link

## 9. Golden fixture

Files: [`fixtures/golden/`](../backend/app/contracts/fixtures/golden/). Load it with `load_golden()` and `load_golden_answer_key()` from `app.contracts.fixtures`.

**Decided:** one grant's worth of hand-written terms, charges, evidence and records, based on the extension-notice example in [product.md](product.md#demo-data-examples). Every workstream tests against it.

Grant SYN-2300117 runs from February 1, 2023 to January 31, 2026. Everything in it is synthetic.

| Clock (UTC) | What happens | Records |
|---|---|---|
| 2023-01-12 | The award letter is uploaded. The agent writes 8 terms, and the accountant confirms them. | `rec-award-*`, `rec-confirm-award` |
| 2025-11-12 | Invoice INV-1001 is uploaded and waits, unlinked | `rec-receipt-1001` |
| 2025-11-14 | Ledger line L-1001 arrives: supplies bought Nov 12, 2025. The agent links the invoice. | `rec-link-1001` |
| 2026-02-21 | The principal investigator emails the sequencing invoice, and it waits | `rec-receipt-1002` |
| 2026-02-24 | Ledger line L-1002 arrives: sequencing done Feb 20, 2026, after the end date. The agent links the invoice. | `rec-link-1002` |
| 2026-04-09 | The extension notice, dated Jan 15, 2026, turns up in Drive. It moves the end date to Jan 31, 2027. | `rec-ext-period` |
| 2026-04-10 | The accountant confirms the new end date | `rec-confirm-ext` |

**Expected buckets:**

- L-1001 is Evidence complete throughout.
- L-1002 is Possible conflict once it arrives, resting on `rec-award-period`. After the confirmation it's Evidence complete, resting on `rec-ext-period`.
- The key gives no bucket between the extension's arrival and its confirmation (see "Not decided yet").

The tests in `app/contracts/tests/` check that the fixture validates, that every passage is copied exactly from its document, that every value appears in its passage, that the ledger file matches the charges, and that the answer key scores all right against the fixture's own agent records.

## Not decided yet

| Item | Who settles it |
|---|---|
| A charge's bucket between an amendment's arrival and the accountant's confirmation of its terms | product |
| A charge's bucket while its grant's terms aren't confirmed yet | product |
| How reversals and cost transfers show in buckets and at closeout | product |
| An amendment that states only a length, such as "extended 12 months". The term holds a stated end date, so this would need a new field. | contract, if a demo document needs it |
| How a file's own date is filled in for files that aren't emails | builder (W3) |
| Columns or tables for agent runs and for mail held from unknown senders | builder (W4 with W1 and W3), through a contract PR |
| The eval case's arrival schedule: when each file arrives | builder (W3) |
