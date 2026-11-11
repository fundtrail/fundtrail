# First run, Nov 11, 2026: who is at fault for each miss and wrong item

The run is `2026-11-11-first-run.txt`, on main at fa0cbcb with the runner from 4f2b321. It found:

| Part | Wrong | Missing |
|---|---|---|
| Records | 25 | 1 |
| Answers | 14 | 1 |
| Links | 1 | 1 |
| Budget lines | 1 | 0 |
| Buckets | 1 | 0 |

That's 42 wrong and 3 missing. Each item below gives what the key expects, what the agent did, and who's at fault: the agent, the key, or the scoring rule. Items with one cause are grouped together. No key, no agent code and no scoring rule was changed.

The verdicts are the runner builder's reading of the evidence. Where the docs don't settle one, it says so and names the call that's needed.

## 1. The GC-1 sentence read as an `other_term`, and `unusual_term` answered on every charge: 5 wrong records and 12 wrong answers

**The agent did:**

- In each case, it wrote an `other_term` from `award_letter.txt` (label "governing conditions"), with the statement "This award is subject to the NSF Grant General Conditions (GC-1) effective ...".
- Once `confirm_terms` confirmed it, code asked `unusual_term` once per charge, and the agent answered `supports` every time, 12 answers in all:
  - credit-memo-spaced-dash: 2
  - effort-report-six-months: 6
  - guest-speaker-stipend: 1
  - laptop-on-participant-stipends: 2
  - trip-airfare-and-per-diem: 1

**The key expects:** no `other_term`, and no `unusual_term` answer, in any case.

**Evidence:**

- Every case's `award_letter.txt`, lines 46 and 47: "This award is subject to the NSF Grant General Conditions (GC-1) effective October 1, 2024, and to the terms of this notice."
- contracts.md, section 1: "`other_term` holds anything an award letter or amendment says that no other kind holds, such as a principal investigator (PI) on leave."
- contracts.md, section 4: `unusual_term` is asked "Once for each confirmed `other_term` in force on the charge's date."

**Verdict: the key, by the contract's wording and ruling 81.**

- The sentence is something the letter says that no other kind holds, so the agent's reading follows the contract. The 12 answers follow from code's rule, not from the agent's choice.
- **Settled by ruling 81.** The sentence is one `other_term` marked as the standard conditions, and it never raises `unusual_term`. The keys will expect that once `OtherTerm.standard_conditions` is on main. Until then, these items count as the key's.

## 2. Notes the key doesn't list: 17 wrong records

**The agent did:** it split some documents into several notes, and read notes out of documents the key reads no note from.

- **effort-report-six-months, `appointment_letter.txt`: 6 notes.** One matched the key's single note. The 5 extra are "postdoc monthly salary", "cost-share split", "work on award", "effort certification schedule" and "appointment accepted".
- **guest-speaker-stipend, `honorarium_letter.eml`: 6 notes.** One matched. The 5 extra are "only invited speaker", "receipt to be signed", "keynote speaker honorarium", "attendees are roster participants" and "award funding the workshop".
- **guest-speaker-stipend, `award_letter.txt`: 1 note,** "project scope". The key reads no note from an award letter.
- **trip-airfare-and-per-diem, `per_diem_rates.txt`: 6 notes.** The key lists no record from this file.

**The key expects:** one `note` (fields `{}`) per supporting document, and none from the award letter or the per diem rates.

**Evidence:**

- contracts.md, section 1: "A `note` is evidence that supports or explains a charge without billing or approving it: a payment notice saying which invoices a payment covered, an appointment letter, an effort report." The examples are whole documents. Nothing says how many notes one document gives.
- `trip-airfare-and-per-diem/arrivals.json`, on `per_diem_rates.txt`: "The department's field per diem rate, the file the per diem item's rate is cited from." The key's design cites the rate in an agent-added checklist item. The key's format can't express checklist items yet (contracts.md section 14: "The key grows to cover checklist items ...").

**Verdict:**

- **The 5 + 5 extra notes from the appointment and honorarium letters, and the award letter's note: the agent.** The contract's examples treat a document as one note, and ruling 81 settles it: one note per document, with every fact cited inside it.
- **The 6 notes from `per_diem_rates.txt`: the key's format.** The case expects something read from that file (a rate on a checklist item), and the key can't say what. Whatever the agent writes from it counts as wrong.

## 3. `approval` records from an appointment letter and an effort certification: 2 wrong records

**The agent did:**

- `approval` from `appointment_letter.txt`: approver Taylor Example, approved 2025-11-14, covers "...Streams: 50 percent of salary, $4,000.00 per month".
- `approval` from `effort_report.txt`: approver "Certified by: Taylor Example, Principal Investigator", approved 2026-08-14, covers "I certify that the distribution of effort above is a reasonable estimate of ...".

**The key expects:** each file read as a `note`. The agent also wrote those notes, and they matched.

**Evidence:**

- contracts.md, section 1, names "an appointment letter, an effort report" as notes.
- An approval's link means "approves" (section 2). It's what the `covers` question and approval rules work on, such as NSF's approval for participant support.
- Neither file approves a cost. One appoints a person; the other certifies effort.

**Verdict: the agent.**

## 4. The trip's expense report read as a bill: 1 missing record and 1 wrong record

**The agent did:** it wrote a `bill` from `expense_report.txt`: total 230000, two items (airfare 180000, per diem 50000), and the traveler as vendor.

**The key expects:** a `note` from `expense_report.txt`, linked with no amount.

**Evidence:**

- contracts.md, section 1: "`bill` ... covers invoices, receipts, card slips, credit memos, and a facility's usage statement." An expense report isn't among them.
- domain.md, the travel row: "Travel | 5721x, 5722x | Expense report. Bills that add up to the charge." The expense report is its own checklist item, apart from the bills.
- `arrivals.json`: "The department's approved expense report: airfare plus 5 days of per diem."

**Verdict: the agent.** The report does claim an amount, but the docs separate it from bills. The agent did link the report with no amount, which is the key's link, and that link matched.

## 5. The per diem rates linked for $500, and the trip's bucket on Jun 24: 1 wrong link and 1 wrong bucket

**The agent did:**

- It linked `per_diem_rates.txt` to L-5201 for 50000.
- At 2026-06-24T12:00Z, the checks put L-5201 in `needs_human`.

**The key expects:**

- No link from the rates file. The per diem's rate is cited from it in an agent-added checklist item.
- `evidence_complete` at that time.

**Evidence:**

- `arrivals.json`, as in item 2: the rates file is "the file the per diem item's rate is cited from".
- domain.md: "Travel per diem | The trip's dates and the per diem rate, instead of receipts".
- This run didn't capture the checks' reason for the bucket. The runner now prints the reasons for every wrong bucket, so a rerun would show it.

**Verdict: the agent.**

- It handled the per diem as a linked note with an amount, not as a checklist item at a rate. The wrong bucket follows from items 4 and 5.
- **Not a false clear.** The error is in the safe direction: Needs a human where the key says Evidence complete.
- The exact check that fired is unconfirmed until a rerun.

## 6. The guest speaker's honorarium letter not linked: 1 missing link

**The agent did:** it read `honorarium_letter.eml` as six notes (item 2), but linked none of them to L-7101. It did link the receipt for 50000, which matched.

**The key expects:** `honorarium_letter.eml` linked to L-7101, with no amount.

**Evidence:** the case's README: "The agent's swap of 'participant list' for 'honorarium letter' waits for the accountant." The letter is the evidence the swapped item asks for.

**Verdict: the agent.**

## 7. The guest speaker's Allowable answered `unsure`: 1 missing answer and 1 wrong answer, counted as unsure

**The agent did:** it answered `allowable: unsure` on L-7101. It also answered `flag: unsure`, which matched the key.

**The key expects:** `allowable: supports` and `flag: unsure`.

**Evidence:** the case's README: "The agent flags the charge, because speakers generally aren't participants. The key expects that flag as an `unsure` answer to the `flag` question." In the key's reading, the doubt belongs to the flag, and the cost itself is allowable. The README marks these rulings as provisional.

**Verdict: the agent, by the key.**

- It's the safe direction, so it isn't counted as a false clear.
- The key's split rests on a provisional ruling. **Call needed (product):** confirm it.

## 8. The guest speaker's budget line "Stipends": 1 wrong budget line

**The agent did:** it assigned L-7101 to the "Stipends" budget line.

**The key expects:** no budget line. The key leaves it out on purpose.

**Evidence:** the case's README: "**Unverified:** which NSF budget line an honorarium belongs on. The key leaves the charge's budget line out, so the eval doesn't score it." Decision 0026 and contracts.md section 14 count any agent item that matches nothing as wrong. The key's format can't say "not scored".

**Verdict: the scoring rule and the key's format, not the agent.**

- The item shouldn't count either way.
- The same README also says "An honorarium isn't participant support, so the agent's budget line disagrees with the ledger account." The agent's "Stipends" agrees with the ledger's 56712 Participant Support-Stipends. That's worth knowing, but it isn't scored.
- **Call needed (contract):** a way for a key to leave an item unscored.

## 9. The laptop flagged: 1 wrong answer

**The agent did:** it answered `flag: unsure` on L-6102, the laptop posted to 56712 Participant Support-Stipends.

**The key expects:** only `allowable: supports` on L-6102. The agent answered that too, and it matched.

**Evidence:**

- contracts.md, section 4, lists `flag` as the agent's own question, asked whenever the agent sees something no other question covers.
- contracts.md, section 2: "a disagreement between them [the budget line and the account] is Needs a human". Code already raises the misfiled account. The bucket was `needs_human`, as the key expects.

**Verdict: the agent.**

- The flag repeats what code already raises, and the contract keeps `flag` for what no other question covers.
- Ruling 81 settles it: the agent doesn't flag what a code check already reports.

## Summary

Each wrong item is counted once.

| Cause | Wrong | Missing | At fault |
|---|---|---|---|
| 1. GC-1 as `other_term`, and `unusual_term` on every charge | 17 (5 records, 12 answers) | 0 | the key, until the keys expect the standard-conditions term (ruling 81) |
| 2a. Several notes per document, and a note from an award letter | 11 records | 0 | the agent (ruling 81: one note per document) |
| 2b. Notes from the per diem rates | 6 records | 0 | the key's format: checklist items can't be expressed |
| 3. Approvals from an appointment letter and an effort certification | 2 records | 0 | the agent |
| 4. Expense report read as a bill | 1 record | 1 record | the agent |
| 5. Per diem rates linked for $500, and the trip's bucket | 1 link, 1 bucket | 0 | the agent |
| 6. Honorarium letter not linked | 0 | 1 link | the agent |
| 7. Allowable `unsure` on the guest speaker | 1 answer | 1 answer | the agent, by a provisional key |
| 8. A budget line the key leaves unscored | 1 budget line | 0 | the scoring rule and the key's format (ruling 81 adds `not_scored`) |
| 9. Laptop flagged | 1 answer | 0 | the agent (ruling 81: no flag for what code reports) |
| **Total** | **42** | **3** | |

By part:

- Records: 5 + 11 + 6 + 2 + 1 = 25 wrong.
- Answers: 12 + 1 + 1 = 14 wrong.

**The tally of fault:**

| At fault | Wrong | Missing |
|---|---|---|
| The agent | 18 | 3 |
| The key or its format | 23 | 0 |
| The scoring rule | 1 | 0 |

Ruling 81 settled the calls this file first left open:

- The GC-1 sentence is one `other_term` marked as the standard conditions, and it never raises `unusual_term`. Until the keys expect it that way, its 17 items are the key's.
- One note per document.
- The agent doesn't flag what a code check already reports.
- The key's format gains agent-added checklist items and a way to leave items unscored.
