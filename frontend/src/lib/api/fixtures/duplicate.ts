// One of the agent's duplicate marks, waiting for the accountant, so fake mode
// shows the decision on the evidence card and on the charge (issue 353).
//
// The contract's sample has no copy, so this adds one synthetic file: the
// sequencing statement forwarded a second time. The agent marks it as a copy
// of sequencing_statement.eml and the mark waits. The fake shows the mark on
// L-1002, the charge the statement pays for; that charge is already in
// Possible conflict, which is more serious than the Needs a human reason the
// mark adds, so its bucket doesn't change. A confirmation naming the mark
// settles it: confirmed, the card says only what the copy is; rejected, the
// card says nothing about a copy. Either way the charge's reason goes. The
// fake has no checks, so nothing else changes.

import type { ChargeDetail, Duplicate, EvidenceFile, FtRecord, NewRecordInput, Reason, RecordState } from "../types";
import { SAMPLE_GRANT_ID, WORKSPACE_ID } from "./sample";

export const DUPLICATE_COPY_FILE: EvidenceFile = {
  id: "file-syn-sequencing-statement-forwarded",
  workspace_id: WORKSPACE_ID,
  grant_id: SAMPLE_GRANT_ID,
  source: "gmail",
  name: "sequencing_statement_forwarded.eml",
  media_type: "message/rfc822",
  storage_path: `${WORKSPACE_ID}/${SAMPLE_GRANT_ID}/file-syn-sequencing-statement-forwarded/sequencing_statement_forwarded.eml`,
  sha256: "synthetic-file-syn-sequencing-statement-forwarded",
  sender: "robin.example@university.example",
  arrived_at: "2026-02-23T15:00:00Z",
};

export const DUPLICATE_MARK: FtRecord<Duplicate> = {
  id: "rec-syn-duplicate-sequencing-forwarded",
  workspace_id: WORKSPACE_ID,
  grant_id: SAMPLE_GRANT_ID,
  author: "agent",
  written_at: "2026-02-24T00:00:00Z",
  replaces_id: null,
  data: {
    kind: "duplicate",
    copy_file_id: DUPLICATE_COPY_FILE.id,
    original_file_id: "file-sequencing-statement",
    reason: "The same usage statement, SEQ-0207, forwarded a second time.",
  },
};

/** The charge the mark shows on. */
export const DUPLICATE_CHARGE_ID = "chg-l-1002";

/** The reason code gives the charge while the mark waits, in the server's words. */
export const DUPLICATE_REASON: Reason = {
  check: "suggestion",
  problem: `waiting:${DUPLICATE_MARK.id}`,
  text: "The agent marked a file as a copy of another, waiting for the accountant.",
  record_ids: [DUPLICATE_MARK.id],
  bucket: "needs_human",
};

/** The mark's state for one fake client: waiting until a confirmation names it. */
export function duplicateFake() {
  let state: RecordState = "waiting";
  return {
    state: () => state,
    /** Settles the mark when a record written to the sample grant confirms or rejects it. */
    wrote(grantId: string, body: NewRecordInput) {
      const data = body.data;
      if (grantId !== SAMPLE_GRANT_ID || state !== "waiting" || data.kind !== "confirmation") return;
      if (!data.record_ids.includes(DUPLICATE_MARK.id)) return;
      state = data.decision === "rejected" ? "rejected" : "counts";
    },
    /** The charge's detail with the waiting mark on it, while it waits. */
    onCharge(detail: ChargeDetail): ChargeDetail {
      if (state !== "waiting" || detail.charge.id !== DUPLICATE_CHARGE_ID || !detail.status) return detail;
      return {
        ...detail,
        status: { ...detail.status, reasons: [...detail.status.reasons, DUPLICATE_REASON] },
        waiting: [...(detail.waiting ?? []), { record: DUPLICATE_MARK, replaces: null, charge_ids: [DUPLICATE_CHARGE_ID] }],
        records: { ...(detail.records ?? {}), [DUPLICATE_MARK.id]: DUPLICATE_MARK },
      };
    },
  };
}

export type DuplicateFake = ReturnType<typeof duplicateFake>;
