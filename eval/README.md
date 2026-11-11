# eval

The eval cases, their answer keys, and the runner. See [docs/eval.md](../docs/eval.md) and [decision 0026](../docs/decisions/0026-eval-scoring-and-the-blind-test.md).

| Path | What |
|---|---|
| `cases/<case>/` | One case: its documents, `ledger.csv`, `arrivals.json` (when each file and ledger line arrives, and the accountant's steps), `answer_key.json` (contracts.md section 14), and sometimes a README on its trap |
| `test_cases.py` | Checks the cases and keys against the contract (standard library only) |
| `run.py` | The runner: plays each case through the app and scores it |
| `results/` | Each real run's report and its results as JSON |

## Running it

From `backend/`, with a Postgres server where the user may create databases:

```
cd backend
uv run python ../eval/run.py --cap-usd 10                 # every case, the real model
uv run python ../eval/run.py --case trip-airfare-and-per-diem --cap-usd 2
uv run python ../eval/run.py --fake                       # a fake model: no calls, no cost
```

- The server comes from `--database-url` or `TEST_DATABASE_URL`. The runner makes a throwaway database there with every migration, and drops it at the end.
- The model key is read from the environment, the same way the app reads it. It's never printed. When `ANTHROPIC_BASE_URL` is set, calls go there, for example to a local counting proxy.
- **Nothing hosted.** The runner refuses any database server that isn't on this machine: localhost, 127.0.0.1, ::1 or a socket. It drops `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and `SUPABASE_JWT_SECRET` from its own environment before it starts. Don't source a whole `.env` to get the key. Take only the key, for example:

  ```
  export ANTHROPIC_API_KEY="$(sed -n 's/^ANTHROPIC_API_KEY=//p' ../.env)"
  ```
- **The spend cap.** Before each model call, the runner adds the largest call so far (or $0.25 before the first) to what's been spent. If that would pass the cap, it refuses the call. That fails the run, and the eval stops there. Cost is estimated from each call's token use at claude-opus-5-5's prices: $4 per million input tokens, $20 output, $0.20 cache read, $5 cache write.
- `--out results.json` saves the results.
- CI runs the runner on every case with a fake model (`backend/tests/ev_runner/`), so no paid calls are made there.

## What it does

Each case gets its own grant, played through the app's ordinary paths, the way a sample grant's timeline is played:

- Each file arrives the way its channel stores it: an upload, or a Gmail message through the known-sender hold.
- Each ledger line arrives the way a ledger upload reads it.
- The grant's clock replays each arrival in order (decision 0023), and the job worker runs the real agent on every run the clock queues.
- The accountant's scripted step (`confirm_terms`) is resolved the way the sample script resolves it. It's then written through the records route's path, with its write check.
- At each time the key names a bucket, the real checks put the charge in one.
- At the end, the agent's current records are compared with the key.

Scoring follows contracts.md section 14 and decision 0026. Each expected item is **right** if it has a match, or **missing** if it has none. An item the agent wrote that matches nothing is **wrong**. There's no partial credit, so a link with the wrong amount is one missing link and one wrong link.

These are scored:

- buckets
- links with their amounts
- budget lines
- answers
- facts and terms read from documents

These are counted on their own:

- **false clears:** a bucket of Evidence complete where the key says otherwise
- **the agent's false clears:** an answer of supports where the key says contradicts or unsure
- unsure answers where the key has an answer
- values whose citation couldn't be found in their file

A wrong bucket is listed with the checks' reasons for it. Which checks fail for a charge, checklist items and suggestions aren't scored yet, because the key's format doesn't cover them (contracts.md, "Not decided yet").

## First run, Nov 11, 2026

One run, the real agent (claude-opus-5-5) on all five cases. Calls went through a local counting proxy, capped at $10. The report is `results/2026-11-11-first-run.txt`.

It ran on main at fa0cbcb (the app, the agent, the checks and the cases), with the runner as committed in 4f2b321. The one difference is that the runner didn't yet print the checks' reasons for a wrong bucket.

| Case | Buckets | Links | Budget lines | Answers | Records | Calls | Est. cost |
|---|---|---|---|---|---|---|---|
| credit-memo-spaced-dash | 5 / 0 / 0 | 3 / 0 / 0 | 2 / 0 / 0 | 2 / 0 / 2 | 11 / 0 / 1 | 41 | $1.17 |
| effort-report-six-months | 12 / 0 / 0 | 12 / 0 / 0 | 6 / 0 / 0 | 6 / 0 / 6 | 13 / 0 / 8 | 59 | $1.94 |
| guest-speaker-stipend | 2 / 0 / 0 | 1 / 1 / 0 | 0 / 0 / 1 | 1 / 1 / 2 | 13 / 0 / 7 | 25 | $0.75 |
| laptop-on-participant-stipends | 3 / 0 / 0 | 2 / 0 / 0 | 2 / 0 / 0 | 2 / 0 / 3 | 12 / 0 / 1 | 27 | $0.78 |
| trip-airfare-and-per-diem | 1 / 0 / 1 | 2 / 0 / 1 | 1 / 0 / 0 | 1 / 0 / 1 | 11 / 1 / 8 | 44 | $1.15 |
| **All cases** | **23 / 0 / 1** | **20 / 1 / 1** | **11 / 0 / 1** | **12 / 1 / 14** | **60 / 1 / 25** | **196** | **$5.80** |

Each cell is right / missing / wrong.

- **False clears:** 0. **The agent's false clears:** 0.
- **Unsure where the key has an answer:** 1. **Values not found in their file:** 0.
- **Tokens:**
  - input: 524
  - output: 117,341
  - cache read: 6,346,083
  - cache write: 435,990
- The proxy's own count agreed: 196 calls, $5.80.

### Every miss and wrong item, and who's at fault

Whether the agent or the key is at fault is the runner's builder's reading of the evidence. No key was changed.

**The award letter's GC-1 sentence: 5 wrong records and 14 wrong answers.** Every case's award letter says "This award is subject to the NSF Grant General Conditions (GC-1) effective ...". The agent read that sentence as an `other_term` each time. Once that term was confirmed, code asked `unusual_term` once per charge, as contracts.md section 4 says, and the agent answered `supports` each time. The 14 answers are:

- credit-memo-spaced-dash: 2
- effort-report-six-months: 6
- guest-speaker-stipend: 1
- laptop-on-participant-stipends: 2
- trip-airfare-and-per-diem: 1

None of the keys lists that term.

- **At fault: unclear.** contracts.md says an `other_term` holds "anything an award letter or amendment says that no other kind holds", and that wording covers this sentence. So the agent followed the contract, and the keys may be missing the term.
- If standard conditions incorporated by reference aren't meant to be an `other_term`, the agent is at fault, and the docs need to say so.
- This is a product call. Settling it settles 19 of the 39 wrong items.

**effort-report-six-months: 7 other wrong records.**

- 5 extra notes from `appointment_letter.txt`: the salary, the cost-share split, the work on the award, the effort schedule, and the acceptance. The key expects one note from that file, and one of the agent's six matched it.
- 2 `approval` records:
  - the cost-share line in the appointment letter
  - the PI's certification on `effort_report.txt`
- **At fault: the agent, for the approvals.** A certification of effort isn't an approval of a cost, and the effort report is already read as a note.
- **At fault for the extra notes: unclear.** The contract doesn't say how many notes one document gives.
- Buckets and links in this case were all right.

**guest-speaker-stipend.**

- **Missing link `honorarium_letter.eml` -> L-7101.** The agent read the letter as five notes, but linked none of them to the charge. At fault: the agent.
- **Allowable answered `unsure`, where the key says `supports`.** This is one missing answer and one wrong one, counted as unsure, not as a false clear. The key's README treats the doubt about a speaker on participant support as the agent's `flag`, which the agent did answer `unsure`, and that matched. At fault: the agent, by the key. The key's ruling is provisional, from the build's coordinator.
- **Wrong budget line "Stipends" for L-7101.** The case's README says the key leaves this charge's budget line out "so the eval doesn't score it". The key's format can't say "not scored", so the runner counts any budget line as wrong. At fault: neither. This is a gap in the key's format.
- **5 extra notes from `honorarium_letter.eml`, and 1 from `award_letter.txt` (the project scope).** At fault: unclear, as above.

**laptop-on-participant-stipends.**

- **Extra `flag` on L-6102, answered `unsure`.** That's the laptop posted to 56712 Participant Support-Stipends. The key expects only `allowable: supports`. Code already puts the charge in Needs a human for the account, and the bucket was right.
- **At fault: unclear.** The flag is a reasonable question, and the key may be incomplete. Whether the agent should flag what code already raises is a product call.

**trip-airfare-and-per-diem.**

- **The expense report was read as a `bill`, and the key expects a `note`.** The agent read `expense_report.txt` as a bill of $2,300.00, with an airfare item and a per diem item. That gives one missing record (the note) and one wrong one (the bill). domain.md lists "Expense report" and "Bills that add up to the charge" as separate items on travel. contracts.md's `bill` covers invoices, receipts, card slips, credit memos and usage statements. At fault: the agent.
- **6 extra notes from `per_diem_rates.txt`.** At fault: unclear, as above.
- **Wrong link `per_diem_rates.txt` -> L-5201 for $500.00.** The key expects the per diem to be covered by the expense report's link, with no amount. At fault: the agent.
- **Wrong bucket: L-5201 on Jun 24, 2026 was Needs a human, where the key says Evidence complete.** It follows from the two readings above. This run didn't capture the checks' reason. The runner now prints the reasons for every wrong bucket, so the next run will show it. At fault: the agent, most likely. Not a false clear.

**Steps left for the user:** none. Every `confirm_terms` step found terms to confirm.
