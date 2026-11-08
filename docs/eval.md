# Eval

The eval is an automated test that measures how often FundTrail gets the right answer. It runs on synthetic grants where we already know what the right answer is.

## The process

```
1 answer key (written first) ──────────────────────────┐
2 synthetic documents ─► 3 FundTrail, same pipeline ─► records + buckets
                                                        │
                                4 compare ◄─────────────┘
                                     ▼
            5 report: false clears, wrong buckets, wrong or missing records
```

1. **Write the answer key first.** For each synthetic expense, it lists two things:
   - the records the agent should write, for example "new end date, from the extension notice" or "this invoice links to that ledger line"
   - the bucket the expense should be in after each arrival
2. **Make the documents.** These are award letters, emails, invoices, receipts and the ledger file, all matching the answer key.
3. **Run FundTrail on them** through the same pipeline as the app: the same file handling, the same agent, the same checks. Documents are read from local folders rather than through the connectors.
4. **Compare, scored in two separate parts:**
   - **The agent:** did it write the right records and links? Each one is counted as right, wrong or missing. This is the number that decides whether link confirmation is needed (trust rule 1 in [architecture.md](architecture.md#trust-rules)).
   - **The checks:** given correct, hand-written records, does code put each expense in the right bucket? This is plain code, so it should always be right, like unit tests.
5. **Report.**
   - The headline number is **false clears:** expenses marked Evidence complete that shouldn't be. That's the error that matters in an audit.
   - Results are reported as counts, never percentages.
   - Every miss is listed in the README.

## When it runs

- **During development,** after every change to the agent's prompts or logic, to show whether the change helped. It calls Claude live, since there's no response cache.
- **The blind test runs once, at the end** (example process, details later):
  - Alex writes a spec of about 12 expenses with traps.
  - A separate Claude session with no repo access generates the documents.
  - The expected answers are pushed to GitHub before the first run, so our prompts can't have been tuned to those documents, and nobody can change an answer after seeing the result.
- **The smoke test** is one real run through Gmail and Drive, just to confirm the connectors work. It isn't scored.

## Not decided yet

| Item | Who settles it |
|---|---|
| The answer-key format | contract |
| How the agent's records are compared to the answer key: what counts as a match | contract |
| The blind test's process and size | product |
| The scoring script and its output | builder (W3) |
