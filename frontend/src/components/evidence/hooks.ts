"use client";

// The evidence screens' server data. Keyed by the signed-in user like the
// shared hooks in lib/api, so one user's data is never served to another.

import useSWR from "swr";
import { useApi, type Id } from "@/lib/api";
import { useUserId } from "@/lib/auth";

/** GET /grants/{grant_id}/evidence: every file's card. */
export function useEvidence(grantId: Id) {
  const api = useApi();
  const userId = useUserId();
  return useSWR(userId ? [userId, "evidence", grantId] : null, () => api.listEvidence(grantId));
}

/**
 * GET /evidence/{file_id}/content: a short-lived link to the original. Not
 * refetched on focus: a new link would reload the open file and lose the spot.
 */
export function useFileLink(fileId: Id) {
  const api = useApi();
  const userId = useUserId();
  return useSWR(userId ? [userId, "file-link", fileId] : null, () => api.getFileLink(fileId), {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
  });
}
