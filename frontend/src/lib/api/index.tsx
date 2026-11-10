"use client";

// The one place screens get server data from. Types come from ./types today and
// from the generated OpenAPI types later; the hooks and the client interface
// stay the same.

import { createContext, useContext, useMemo, type ReactNode } from "react";
import useSWR, { SWRConfig, useSWRConfig } from "swr";
import { useAuth } from "../auth";
import { config, fakeApi } from "../config";
import { HttpApiClient, type ApiClient } from "./client";
import { FakeApiClient } from "./fake";
import type { Id } from "./types";

export * from "./types";
export { ApiError, type ApiClient } from "./client";

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

export function ApiProvider({ client, children }: { client?: ApiClient; children: ReactNode }) {
  const auth = useAuth();
  const getAccessToken = auth.getAccessToken;
  const value = useMemo<ApiClient>(
    () => client ?? (fakeApi ? new FakeApiClient() : new HttpApiClient(config.apiUrl!, getAccessToken)),
    [client, getAccessToken],
  );
  return (
    <ApiContext.Provider value={value}>
      <SWRConfig value={swrOptions}>{children}</SWRConfig>
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

function useResource<T>(key: readonly unknown[] | null, load: () => Promise<T>) {
  return useSWR<T>(key, load);
}

export function useWorkspaces() {
  const api = useApi();
  return useResource(["workspaces"], () => api.listWorkspaces());
}

export function useClock(workspaceId: Id | null) {
  const api = useApi();
  return useResource(workspaceId ? ["clock", workspaceId] : null, () => api.getClock(workspaceId!));
}

export function useGrants(workspaceId: Id | null) {
  const api = useApi();
  return useResource(workspaceId ? ["grants", workspaceId] : null, () => api.listGrants(workspaceId!));
}

export function useGrant(grantId: Id) {
  const api = useApi();
  return useResource(["grant", grantId], () => api.getGrant(grantId));
}

export function useProblemList(grantId: Id) {
  const api = useApi();
  return useResource(["problems", grantId], () => api.getProblemList(grantId));
}

export function useCharges(grantId: Id) {
  const api = useApi();
  return useResource(["charges", grantId], () => api.listCharges(grantId));
}
