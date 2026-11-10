"use client";

import useSWR from "swr";
import { useApi, useRefresh, type ApiClient, type Id } from "@/lib/api";
import { useUserId } from "@/lib/auth";
import type { Decision } from "./Decide";

/** One piece of server data for these screens, keyed by the signed-in user like every other screen's. */
export function useServer<T>(key: readonly unknown[] | null, load: (api: ApiClient) => Promise<T>) {
  const api = useApi();
  const userId = useUserId();
  return useSWR<T>(userId && key ? [userId, ...key] : null, () => load(api));
}

/**
 * What the accountant does in a thread. A decision on one of the agent's
 * records is a confirmation through POST /grants/{grant_id}/records; accepting
 * a dispute is confirming it, which accepts the reason with the agent's
 * reasoning as the note (contracts.md section 4). Every write refetches what's
 * on screen afterwards, so the page shows the server's new status.
 */
export function useThreadActions(grantId: Id, subject: { chargeId: Id } | { recordId: Id }) {
  const api = useApi();
  const refresh = useRefresh();
  return {
    async decide(recordId: Id, decision: Decision) {
      await api.writeRecord(grantId, { data: { kind: "confirmation", record_ids: [recordId], decision } });
      await refresh();
    },
    async ask(text: string) {
      if ("chargeId" in subject) await api.postChargeMessage(subject.chargeId, text);
      else await api.postRecordMessage(subject.recordId, text);
      await refresh();
    },
  };
}
