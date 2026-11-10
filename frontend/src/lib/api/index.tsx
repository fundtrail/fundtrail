"use client";

// The one place screens get server data from. Types come from ./types today and
// from the generated OpenAPI types later; the hooks and the client interface
// stay the same.

import { createContext, useContext, type ReactNode } from "react";
import useSWR, { SWRConfig, useSWRConfig } from "swr";
import { useUserId } from "../auth";
import type { ApiClient } from "./client";
import type { Id } from "./types";

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

/** Refetch everything on screen. The "something changed" ping will call this. */
export function useRefresh(): () => Promise<unknown> {
  const { mutate } = useSWRConfig();
  return () => mutate(() => true);
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

export function useClock(workspaceId: Id | null) {
  return useResource(workspaceId ? ["clock", workspaceId] : null, (api) => api.getClock(workspaceId!));
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

/** A sample grant's timeline. Pass null for a grant that isn't a sample: nothing is requested. */
export function useTimeline(grantId: Id | null) {
  return useResource(grantId ? ["timeline", grantId] : null, (api) => api.getTimeline(grantId!));
}
