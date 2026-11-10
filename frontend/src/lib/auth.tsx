"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { config, fakeAuth } from "./config";

export interface SignedInUser {
  email: string;
  name: string | null;
}

export type AuthState =
  | { status: "loading" }
  | { status: "signed_out" }
  | { status: "signed_in"; user: SignedInUser };

export interface Auth {
  state: AuthState;
  /** True when sign-in is faked because no Supabase project is configured. */
  fake: boolean;
  signIn(): Promise<void>;
  signOut(): Promise<void>;
  /** The access token sent as `Authorization: Bearer`, or null when signed out. */
  getAccessToken(): Promise<string | null>;
}

const AuthContext = createContext<Auth | null>(null);

// --- Supabase: Google sign-in through Supabase Auth ---

let supabase: SupabaseClient | null = null;
function supabaseClient(): SupabaseClient {
  if (!supabase) {
    supabase = createClient(config.supabaseUrl!, config.supabaseAnonKey!, {
      auth: { flowType: "pkce", persistSession: true, detectSessionInUrl: true, autoRefreshToken: true },
    });
  }
  return supabase;
}

function useSupabaseAuth(): Auth {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    const client = supabaseClient();
    const show = (session: { user: { email?: string; user_metadata?: Record<string, unknown> } } | null) => {
      if (!session) {
        setState({ status: "signed_out" });
        return;
      }
      const meta = session.user.user_metadata ?? {};
      const name = typeof meta.full_name === "string" ? meta.full_name : typeof meta.name === "string" ? meta.name : null;
      setState({ status: "signed_in", user: { email: session.user.email ?? "", name } });
    };
    client.auth.getSession().then(({ data }) => show(data.session));
    const { data } = client.auth.onAuthStateChange((_event, session) => show(session));
    return () => data.subscription.unsubscribe();
  }, []);

  return useMemo<Auth>(
    () => ({
      state,
      fake: false,
      async signIn() {
        const { error } = await supabaseClient().auth.signInWithOAuth({
          provider: "google",
          options: { redirectTo: `${window.location.origin}/` },
        });
        if (error) throw error;
      },
      async signOut() {
        await supabaseClient().auth.signOut();
      },
      async getAccessToken() {
        const { data } = await supabaseClient().auth.getSession();
        return data.session?.access_token ?? null;
      },
    }),
    [state],
  );
}

// --- The fake: no Supabase project needed. The session lives in this browser tab's storage. ---

const FAKE_KEY = "fundtrail.fake-session";
const FAKE_USER: SignedInUser = { email: "accountant@university.example", name: "Demo accountant" };

function readFakeSession(): boolean {
  try {
    return window.localStorage.getItem(FAKE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeFakeSession(signedIn: boolean) {
  try {
    if (signedIn) window.localStorage.setItem(FAKE_KEY, "1");
    else window.localStorage.removeItem(FAKE_KEY);
  } catch {
    // Storage is blocked. The session lasts until the page reloads.
  }
}

function useFakeAuth(): Auth {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    // Read once on mount: storage isn't available while rendering on the server.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState(readFakeSession() ? { status: "signed_in", user: FAKE_USER } : { status: "signed_out" });
  }, []);

  const signIn = useCallback(async () => {
    writeFakeSession(true);
    setState({ status: "signed_in", user: FAKE_USER });
  }, []);
  const signOut = useCallback(async () => {
    writeFakeSession(false);
    setState({ status: "signed_out" });
  }, []);

  return useMemo<Auth>(
    () => ({
      state,
      fake: true,
      signIn,
      signOut,
      async getAccessToken() {
        return readFakeSession() ? "fake-access-token" : null;
      },
    }),
    [state, signIn, signOut],
  );
}

function SupabaseAuthProvider({ children }: { children: ReactNode }) {
  return <AuthContext.Provider value={useSupabaseAuth()}>{children}</AuthContext.Provider>;
}

function FakeAuthProvider({ children }: { children: ReactNode }) {
  return <AuthContext.Provider value={useFakeAuth()}>{children}</AuthContext.Provider>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  return fakeAuth ? <FakeAuthProvider>{children}</FakeAuthProvider> : <SupabaseAuthProvider>{children}</SupabaseAuthProvider>;
}

/** For tests: a fixed auth state. */
export function StaticAuthProvider({ value, children }: { value: Auth; children: ReactNode }) {
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth needs an AuthProvider");
  return auth;
}
