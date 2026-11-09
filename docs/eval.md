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

1. **Write the answer key first.** For each synthetic expense, it lists:
   - the facts and terms the agent should read, for example "new end date, from the extension notice"
   - the links it should write, with amounts, for example "invoice 2050 pays $5,000 of this ledger line"
   - its answers to the questions code asks, for example "Allowable: contradicts" for a break-room espresso machine
   - the bucket the expense should be in after each arrival

   The format is in [contracts.md](contracts.md#11-eval-answer-key).
2. **Make the documents.** These are award letters, emails, invoices, receipts and the ledger file, all matching the answer key.
3. **Run FundTrail on them** through the same pipeline as the app: the same file handling, the same agent, the same checks. Documents are read from local folders rather than through the connectors.
4. **Compare, scored in two separate parts:**
   - **The agent:** did it write the right records, links and answers? Each one is counted as right, wrong or missing. The link count decides whether first links need confirmation too (trust rule 1 in [architecture.md](architecture.md#trust-rules)).
   - **The checks:** given correct, hand-written records, does code put each expense in the right bucket? This is plain code, so it should always be right, like unit tests.
5. **Report.**
   - The headline number is **false clears:** expenses marked Evidence complete that shouldn't be. That's the error that matters in an audit. The agent's own false clears are counted separately too: answers of supports where the right answer is contradicts or unsure.
   - Results are reported as counts, never percentages.
   - Every miss is listed in the README.

## When it runs

- **During development,** after every change to the agent's prompts or logic, to show whether the change helped. It calls Claude live, since there's no response cache. Whether the agent's prompts get tuned against it is up to whoever designs them (W1).
- **The blind test runs once, at the end** (example process, details later):
  - Alex writes a spec of about 12 expenses with traps.
  - A separate Claude session with no repo access generates the documents.
  - The expected answers are pushed to GitHub before the first run, so our prompts can't have been tuned to those documents, and nobody can change an answer after seeing the result.
- **The smoke test** is one real run through Gmail and Drive, just to confirm the connectors work. It isn't scored.

## Not decided yet

| Item | Who settles it |
|---|---|
| The blind test's process and size | product |
| The scoring script and its output | builder (W3) |
