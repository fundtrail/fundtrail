"""The contracts: the seams between areas, written from docs/contracts.md.

Import from the module that holds each contract:

- base: the base model and the conventions
- records: the record envelope, every record kind, citations and cited values
- rules: what counts (current records, what waits, pointers that follow a
  correction) and the write check, check_new_record
- charges: charges and the ledger file
- evidence: evidence files
- buckets: the four buckets
- checks: the checks' interface, run_checks, which W2 implements, and ready_for_closeout
- corrections: netting a charge with the lines that correct it (decision 0020)
- signoff: a sign-off's snapshot and what changed since (decision 0022)
- mail: held mail and the Gmail and Drive checker's progress (decision 0025)
- runs: agent runs, and which charges a charge-triggered run covers
- threads: review thread messages
- workspaces: users, workspaces and grants
- api: the API (application programming interface) bodies, the screens' included
- eval: the eval answer key
- fixtures: the sample grant every area tests against
"""
