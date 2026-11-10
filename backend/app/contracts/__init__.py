"""The contracts: the seams between areas, written from docs/contracts.md.

Import from the module that holds each contract:

- base: the base model and the conventions
- records: the record envelope, every record kind, citations and cited values
- rules: what counts (current records, what waits, pointers that follow a
  correction) and the write check, check_new_record
- charges: charges and the ledger file
- evidence: evidence files
- checks: the checks' interface, run_checks, which W2 implements
- runs: agent runs
- threads: review thread messages
- workspaces: users, workspaces and grants
- api: the API bodies that are settled
- eval: the eval answer key
- fixtures: the sample grant every area tests against
"""
