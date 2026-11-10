// The checks' output for the sample grant at FAKE_NOW, as the server would send
// it (contracts.md section 15, "Expected buckets"). Shared by the problem list,
// the charges list, the charge page and the threads, so they always agree.

import type { ChargeStatus, Id, Reason } from "../types";
import { SAMPLE_GRANT_ID } from "./sample";

const pass = (check: string, text: string, record_ids: Id[] = []): Reason => ({
  check,
  problem: "pass",
  text,
  record_ids,
  bucket: "evidence_complete",
});

const STATUSES: Record<Id, ChargeStatus> = {
  // Evidence complete throughout: inside the period, its one item filled.
  "chg-l-1001": {
    grant_id: SAMPLE_GRANT_ID,
    charge_id: "chg-l-1001",
    bucket: "evidence_complete",
    reasons: [
      pass("period_of_performance", "Cost date Nov 12, 2025 is inside the grant's period, Feb 1, 2023 to Jan 31, 2026.", ["rec-period"]),
      pass("checklist", "Bills on file cover $1,240.00 of $1,240.00.", ["rec-link-l-1001"]),
      pass("allowable", "The agent's answer supports this cost.", ["rec-allowable-l-1001"]),
    ],
    checklist: [
      {
        default_item: "bill",
        added_by: "default",
        needed: "A bill that adds up to the charge",
        amount_cents: 124000,
        filled: true,
        link_ids: ["rec-link-l-1001"],
      },
    ],
    flagged: false,
  },
  // Possible conflict: work after the end date in force, resting on the award letter's period.
  "chg-l-1002": {
    grant_id: SAMPLE_GRANT_ID,
    charge_id: "chg-l-1002",
    bucket: "possible_conflict",
    reasons: [
      {
        check: "period_of_performance",
        problem: "after_end_date",
        text: "Cost date Feb 20, 2026 is after the grant's end date, Jan 31, 2026.",
        record_ids: ["rec-period"],
        bucket: "possible_conflict",
      },
      pass("checklist", "Bills on file cover $2,180.00 of $2,180.00.", ["rec-link-l-1002"]),
      pass("allowable", "The agent's answer supports this cost.", ["rec-allowable-l-1002"]),
    ],
    checklist: [
      {
        default_item: "usage_statement",
        added_by: "default",
        needed: "The facility's usage statement",
        amount_cents: 218000,
        filled: true,
        link_ids: ["rec-link-l-1002"],
      },
    ],
    flagged: true,
  },
};

/** A sample charge's status at FAKE_NOW, as a fresh copy. */
export function chargeStatusAt(chargeId: Id): ChargeStatus {
  const status = STATUSES[chargeId];
  if (!status) throw new Error(`No status for ${chargeId}`);
  return structuredClone(status);
}
