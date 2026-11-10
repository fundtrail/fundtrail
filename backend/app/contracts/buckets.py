"""The four buckets a charge can be in (docs/contracts.md section 8).

Kept on their own so a sign-off's snapshot can name a bucket without importing the
checks' interface.
"""

from enum import StrEnum


class Bucket(StrEnum):
    EVIDENCE_COMPLETE = "evidence_complete"
    POSSIBLE_CONFLICT = "possible_conflict"
    MISSING_EVIDENCE = "missing_evidence"
    NEEDS_HUMAN = "needs_human"
