"use client";

// The one place screens get server data from. Types come from ./types today and
// from the generated OpenAPI types later; the hooks and the client interface
// stay the same.

import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";
import useSWR, { SWRConfig, useSWRConfig } from "swr";
import { useAuth, useUserId } from "../auth";
import type { ApiClient } from "./client";
import type { Id, TimelineView } from "./types";

export * from "./types";
export { ApiError, HttpApiClient, SampleRefusalError, type ApiClient } from "./client";

const ApiContext = createContext<ApiClient | null>(null);

/**
 * Screen updates. Until the "something changed" ping lands (architecture.md,
 * Stack), every screen refetches when the window regains focus and when the
 * browser reconnects. Supabase doesn't promise every ping arrives, so these
 * stay on after the ping lands too. A ping then calls useRefresh() below.
 */
const swrOptions = {
  revalidateOnFocus: true,
  revalidateOnReconnect: true,
  focusThrottleInterval: 2000,
  shouldRetryOnError: false,
} as const;

/**
 * Serves `client` to the screens. Each signed-in user gets a fresh cache, so
 * after a sign-out nothing the last user loaded is left to show.
 */
export function ApiProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  const userId = useUserId();
  return (
    <ApiContext.Provider value={client}>
      <SWRConfig key={userId ?? "signed-out"} value={{ ...swrOptions, provider: () => new Map() }}>
        {children}
      </SWRConfig>
    </ApiContext.Provider>
  );
}

export function useApi(): ApiClient {
  const api = useContext(ApiContext);
  if (!api) throw new Error("useApi needs an ApiProvider");
  return api;
}

/** Refetch everything on screen. The "something changed" ping calls this. */
export function useRefresh(): () => Promise<unknown> {
  const { mutate } = useSWRConfig();
  return () => mutate(() => true);
}

/**
 * Listens for the backend's "something changed" pings on a private Realtime
 * channel (`grant:{id}` or `workspace:{id}`, backend/app/db/pings.py) and
 * refetches everything on screen when one arrives (architecture.md, Stack).
 * Supabase doesn't promise every ping arrives, so the refetch on focus and on
 * reconnect stays. Nothing happens in fake mode, or with no topic.
 */
export function usePings(topic: string | null) {
  const { listen } = useAuth();
  const userId = useUserId();
  const refresh = useRefresh();
  const latest = useRef(refresh);
  useEffect(() => {
    latest.current = refresh;
  });
  useEffect(() => {
    if (!topic || !listen || !userId) return;
    return listen(topic, () => void latest.current());
  }, [topic, listen, userId]);
}

/**
 * One piece of server data. Nothing is requested until a user is signed in
 * (the request carries their token), and the key names the user, so one
 * user's data is never served to another.
 */
function useResource<T>(key: readonly unknown[] | null, load: (api: ApiClient) => Promise<T>) {
  const api = useApi();
  const userId = useUserId();
  return useSWR<T>(userId && key ? [userId, ...key] : null, () => load(api));
}

export function useWorkspaces() {
  return useResource(["workspaces"], (api) => api.listWorkspaces());
}


export function useGrants(workspaceId: Id | null) {
  return useResource(workspaceId ? ["grants", workspaceId] : null, (api) => api.listGrants(workspaceId!));
}

export function useGrant(grantId: Id) {
  return useResource(["grant", grantId], (api) => api.getGrant(grantId));
}

export function useProblemList(grantId: Id) {
  return useResource(["problems", grantId], (api) => api.getProblemList(grantId));
}

export function useCharges(grantId: Id) {
  return useResource(["charges", grantId], (api) => api.listCharges(grantId));
}

export function useRecords(grantId: Id) {
  return useResource(["records", grantId], (api) => api.listRecords(grantId));
}

export function useEvidence(grantId: Id) {
  return useResource(["evidence", grantId], (api) => api.listEvidence(grantId));
}

export function useCharge(chargeId: Id) {
  return useResource(["charge", chargeId], (api) => api.getCharge(chargeId));
}

export function useChargeThread(chargeId: Id) {
  return useResource(["charge-thread", chargeId], (api) => api.getChargeThread(chargeId));
}

export function useRecordThread(recordId: Id) {
  return useResource(["record-thread", recordId], (api) => api.getRecordThread(recordId));
}

/** The Sample dropdown's choices. They don't depend on a workspace. */
export function useSamples() {
  return useResource(["samples"], (api) => api.listSamples());
}

/**
 * A sample grant's timeline. Pass null for a grant that isn't a sample: nothing
 * is requested. While the agent is still catching up, it refetches every few
 * seconds too, so the notice clears even if a ping is lost.
 */
export function useTimeline(grantId: Id | null) {
  const api = useApi();
  const userId = useUserId();
  return useSWR<TimelineView>(userId && grantId ? [userId, "timeline", grantId] : null, () => api.getTimeline(grantId!), {
    refreshInterval: (view) => (view?.catching_up ? CATCHING_UP_REFRESH_MS : 0),
  });
}

/** How often the timeline refetches while the agent is catching up. */
export const CATCHING_UP_REFRESH_MS = 5000;
