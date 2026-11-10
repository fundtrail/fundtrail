"use client";

import { useApi, useRefresh, type Id, type NewRecordInput } from "@/lib/api";
import type { Decision } from "./Decide";

/** Sends one of the accountant's records. A write the write check refuses throws its ApiError. */
export type OnWrite = (input: NewRecordInput) => Promise<void>;

/**
 * What the accountant does on a charge or a record. Every decision is a record
 * through POST /grants/{grant_id}/records: a decision on one of the agent's
 * records is a confirmation, and accepting a dispute is confirming it, which
 * accepts the reason with the agent's reasoning as the note (contracts.md
 * section 4). Answers, checklist changes, accepted reasons and snoozes go the
 * same way. Every write refetches what's on screen afterwards, so the page
 * shows the server's new status.
 */
export function useThreadActions(grantId: Id, subject: { chargeId: Id } | { recordId: Id }) {
  const api = useApi();
  const refresh = useRefresh();
  async function write(input: NewRecordInput) {
    await api.writeRecord(grantId, input);
    await refresh();
  }
  return {
    write,
    async decide(recordId: Id, decision: Decision) {
      await write({ data: { kind: "confirmation", record_ids: [recordId], decision } });
    },
    async ask(text: string) {
      if ("chargeId" in subject) await api.postChargeMessage(subject.chargeId, text);
      else await api.postRecordMessage(subject.recordId, text);
      await refresh();
    },
  };
}
