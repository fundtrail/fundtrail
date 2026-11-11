"use client";

import { useCallback, useMemo, useState, type ReactNode } from "react";
import { ApiProvider, HttpApiClient } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { FakeAuthProvider, markSessionExpired, SupabaseAuthProvider, useAuth } from "@/lib/auth";
import { appConfig, type AppConfig } from "@/lib/config";

/** Shown on every page in fake mode, so synthetic data is never taken for real data. */
export function FakeModeBanner() {
  return (
    <div className="ft-fake-banner" role="note">
      Fake mode: synthetic data and a fake sign-in. Nothing here comes from a real ledger or account.
    </div>
  );
}

/** Real mode with a missing variable: say which, and run nothing. */
export function ConfigError({ missing }: { missing: string[] }) {
  return (
    <div className="ft-si">
      <div className="ft-si__card" role="alert">
        <div className="ft-wordmark">FundTrail</div>
        <p>This build isn&apos;t configured. These variables are missing:</p>
        <ul>
          {missing.map((name) => (
            <li key={name} className="ft-id">
              {name}
            </li>
          ))}
        </ul>
        <p className="ft-caption">
          To run on synthetic data with no backend and no Supabase project, set NEXT_PUBLIC_FAKE=1 instead.
        </p>
      </div>
    </div>
  );
}

function RealApi({ apiUrl, children }: { apiUrl: string; children: ReactNode }) {
  const { getAccessToken, signOut, state } = useAuth();
  const signedIn = state.status === "signed_in";
  // A refused or missing session signs a signed-in user out, and the shell sends
  // them to sign-in, which says the session expired. Noted only while signed in.
  const onUnauthorized = useCallback(() => {
    if (!signedIn) return;
    markSessionExpired();
    void signOut();
  }, [signedIn, signOut]);
  const client = useMemo(() => new HttpApiClient(apiUrl, getAccessToken, onUnauthorized), [apiUrl, getAccessToken, onUnauthorized]);
  return <ApiProvider client={client}>{children}</ApiProvider>;
}

export function Providers({ config = appConfig, children }: { config?: AppConfig; children: ReactNode }) {
  const [fakeClient] = useState(() => createFakeApiClient());
  switch (config.mode) {
    case "error":
      return <ConfigError missing={config.missing} />;
    case "fake":
      return (
        <FakeAuthProvider>
          <ApiProvider client={fakeClient}>
            <FakeModeBanner />
            {children}
          </ApiProvider>
        </FakeAuthProvider>
      );
    case "real":
      return (
        <SupabaseAuthProvider url={config.supabaseUrl} anonKey={config.supabaseAnonKey} devEmailSignIn={config.devEmailSignIn}>
          <RealApi apiUrl={config.apiUrl}>{children}</RealApi>
        </SupabaseAuthProvider>
      );
  }
}
