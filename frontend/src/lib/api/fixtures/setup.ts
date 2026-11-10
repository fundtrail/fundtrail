// Adding a grant and uploading its ledger. Owned by the grant setup screens'
// builder.
//
// Adding a grant returns a new grant with no award number or title yet, as the
// server does before the agent reads the letter; the fake has no agent, so it
// stays that way. A ledger upload counts each row by its line ID against the
// sample's charges, and rejects a row with no line ID. Nothing new appears on
// the charges list.

import type { ApiClient } from "../client";
import type { Grant, LedgerUploadResult, RowError } from "../types";
import { fakeId, sample, served, SAMPLE_GRANT_ID, WORKSPACE_ID } from "./sample";

/** The sample's own ledger file (backend/app/contracts/fixtures/golden/ledger.csv). */
export const SAMPLE_LEDGER_CSV = [
  "line_id,transaction_date,posting_date,amount,description,account,vendor,reference,original_line_id",
  "L-1001,2025-11-12,2025-11-14,1240.00,Sediment core liners,55016 Lab Instruments and Supplies,Example Lab Supply Co.,INV-1001,",
  "L-1002,2026-02-20,2026-02-24,2180.00,Sediment DNA sequencing run 7,59009 Recharge-Other Expenses,Example Sequencing Core,SEQ-0207,",
].join("\n");

export function countLedger(csv: string): LedgerUploadResult {
  const known = new Set(sample.charges.map((c) => c.ledger_line_id));
  const lines = csv.split(/\r?\n/).filter((l) => l.trim() !== "");
  const header = (lines.shift() ?? "").split(",");
  const idColumn = header.indexOf("line_id");
  const result: LedgerUploadResult = { added: 0, already_present: 0, rejected: [] };
  lines.forEach((line, i) => {
    const id = idColumn >= 0 ? line.split(",")[idColumn]?.trim() : "";
    if (!id) {
      const error: RowError = { row: i + 1, message: "The row has no line_id." };
      result.rejected.push(error);
    } else if (known.has(id)) result.already_present += 1;
    else result.added += 1;
  });
  return result;
}

export function setupFake(): Pick<ApiClient, "createGrant" | "uploadLedger"> {
  return {
    createGrant: (workspaceId) => {
      if (workspaceId !== WORKSPACE_ID) return served<Grant>(undefined);
      return served<Grant>({ id: fakeId("grant"), workspace_id: workspaceId, funder: "NSF", award_number: null, title: null });
    },
    uploadLedger: async (grantId, ledger) => {
      if (grantId !== SAMPLE_GRANT_ID) return served<LedgerUploadResult>(undefined);
      return served(countLedger(await ledger.text()));
    },
  };
}
