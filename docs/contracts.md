# Contracts

Contracts are the seams between workstreams. Once one is agreed, each side can build without waiting for the other.

**Status:** draft. This file lists what's already decided about each contract. The contracts task (phase 0 in [plan.md](plan.md)) fills in the rest. Alex and Grant approve it together. Target freeze: **Sun Nov 8, 10 AM PT.**

## Where contracts live

Once a contract is written as code, the code is the truth and this file links to it.

| Contract | Lives in |
|---|---|
| Record format | Pydantic models in `backend/app/contracts/` |
| Database tables | Supabase migrations in `supabase/migrations/` |
| API | FastAPI routes. The frontend generates its TypeScript types from FastAPI's OpenAPI schema, so a backend change shows up as a type error instead of a silent mismatch. |
| Golden fixture | Next to the record models in `backend/app/contracts/` |

## Changing a contract

1. Open a PR that changes the contract. Both Alex and Grant approve it.
2. In the same PR, update the code that uses it so main stays green, or have both owners agree on who follows up.
3. If the change alters behavior or direction, add a file to [decisions/](decisions/).

## 1. Records

**Decided:**

- Records are the single source of truth. A record is never edited. A correction is a new record that replaces the old one, and the old one stays.
- The agent and the accountant both write records. Every record says who wrote it and when, using the clock's date.
- A fact pulled from a document carries its citation:
  - the document
  - the passage, copied by the API and never typed by the model
  - where the passage sits: a page number, a character range or a block index, or, for photos and scans, the box Claude estimated
- Records about grant terms (dates, budget lines, people and roles, approval rules) come from the award letter and amendments. The accountant confirms them before any check uses them.
- The agent never writes a status. Status, reasons and status text all come from the checks.

**Open:** the record types and their fields, and how "replaces" is represented.

## 2. Charges

**Decided:**

- One charge comes from one ledger line, read by code. The agent never writes charges.
- Each line is matched by its ledger line ID, so syncing or uploading the same line twice adds nothing.
- Each line has a transaction date, which the checks use, a posting date, and an arrival date, which the clock uses.
- Corrections arrive as new lines (reversals, cost transfers). Nothing is edited.

**Open:** the fields, and how a reversal or cost transfer points to its original line.

## 3. Evidence files

**Decided:**

- The original file is stored as it arrived.
- Each file has a source (Gmail, Drive or upload), its own date and an arrival date.
- A file can be unlinked: it waits until the agent links it to a charge or a grant term.

**Open:** the fields, and where files sit in storage.

## 4. The checks' interface

**Decided:** the checks are a pure function. They take everything visible at the clock's "now" (the confirmed terms, the charges and the records) and return each charge's bucket, with its reasons and the records each reason rests on. There's no database and no model inside, so the checks can be tested from day one with hand-written records.

**Open:** the exact signature and the shape of the result.

## 5. Database tables

**Open:** all of it. It has to hold workspaces, users, grants, charges, evidence files, records, statuses and their history, and each workspace's clock.

## 6. API

**Open:** all of it. FastAPI on the backend, with types generated for the frontend.

## 7. Ledger file

**Decided:** CSV or Excel, one file per grant. In the hackathon build, a seeded grant's file holds its whole history, and the clock releases each line on its posting date.

**Open:** the columns and how they get mapped.

## 8. Eval answer key

**Decided:** for each expense, the records the agent should write and the bucket the expense should have after each arrival.

**Open:** the format, and what counts as a match when comparing records.

## 9. Golden fixture

**Decided:** one grant's worth of hand-written terms, charges, evidence and records, based on the extension-notice example in [product.md](product.md#demo-data-examples). Every workstream tests against it.

**Open:** its contents. The contracts task writes it.

## Not decided yet

Every **Open** item above is settled by **contract**: Alex and Grant together, by the freeze target.
