"use client";

import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

/** How the user signed in, as Supabase records it. */
export type SignInMethod = "google" | "email" | "fake";

export interface SignedInUser {
  /** The Supabase auth user ID. */
  id: string;
  email: string;
  name: string | null;
  /** Null when Supabase doesn't say. */
  method?: SignInMethod | null;
}

export type AuthState =
  | { status: "loading" }
  | { status: "signed_out" }
  | { status: "signed_in"; user: SignedInUser };

export interface Auth {
  state: AuthState;
  /** True in fake mode: a synthetic user, no Supabase project. */
  fake: boolean;
  signIn(): Promise<void>;
  /**
   * Local development only (ruling 63): emails a sign-in link. Present only
   * when NEXT_PUBLIC_DEV_EMAIL_SIGNIN=1 in a development build.
   */
  signInWithEmail?(email: string): Promise<void>;
  signOut(): Promise<void>;
  /** The access token sent as `Authorization: Bearer`, or null when signed out. */
  getAccessToken(): Promise<string | null>;
  /**
   * Listens on a private Realtime channel for the backend's "something
   * changed" pings, and returns the way to stop. Absent in fake mode.
   */
  listen?(topic: string, onPing: () => void): () => void;
}

const AuthContext = createContext<Auth | null>(null);

// --- Real: Google sign-in through Supabase Auth ---

let supabase: SupabaseClient | null = null;
function supabaseClient(url: string, anonKey: string): SupabaseClient {
  if (!supabase) {
    supabase = createClient(url, anonKey, {
      auth: { flowType: "pkce", persistSession: true, detectSessionInUrl: true, autoRefreshToken: true },
    });
  }
  return supabase;
}

function userFrom(session: Session): SignedInUser {
  const meta = session.user.user_metadata ?? {};
  const name = typeof meta.full_name === "string" ? meta.full_name : typeof meta.name === "string" ? meta.name : null;
  const provider = session.user.app_metadata?.provider;
  const method: SignInMethod | null = provider === "google" || provider === "email" ? provider : null;
  return { id: session.user.id, email: session.user.email ?? "", name, method };
}

function useSupabaseAuth(url: string, anonKey: string, devEmailSignIn: boolean): Auth {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    const client = supabaseClient(url, anonKey);
    const show = (session: Session | null) =>
      setState(session ? { status: "signed_in", user: userFrom(session) } : { status: "signed_out" });
    client.auth.getSession().then(({ data }) => show(data.session));
    const { data } = client.auth.onAuthStateChange((_event, session) => show(session));
    return () => data.subscription.unsubscribe();
  }, [url, anonKey]);

  return useMemo<Auth>(
    () => ({
      state,
      fake: false,
      async signIn() {
        const { error } = await supabaseClient(url, anonKey).auth.signInWithOAuth({
          provider: "google",
          options: { redirectTo: `${window.location.origin}/` },
        });
        if (error) throw error;
      },
      ...(devEmailSignIn
        ? {
            async signInWithEmail(email: string) {
              const { error } = await supabaseClient(url, anonKey).auth.signInWithOtp({
                email,
                options: { emailRedirectTo: `${window.location.origin}/` },
              });
              if (error) throw error;
            },
          }
        : {}),
      async signOut() {
        await supabaseClient(url, anonKey).auth.signOut();
      },
      async getAccessToken() {
        const { data } = await supabaseClient(url, anonKey).auth.getSession();
        return data.session?.access_token ?? null;
      },
      listen(topic: string, onPing: () => void) {
        const client = supabaseClient(url, anonKey);
        const channel = client.channel(topic, { config: { private: true } });
        let stopped = false;
        // A private channel needs the user's token before it subscribes.
        void client.realtime.setAuth().then(() => {
          if (stopped) return;
          channel.on("broadcast", { event: "*" }, () => onPing()).subscribe();
        });
        return () => {
          stopped = true;
          void client.removeChannel(channel);
        };
      },
    }),
    [state, url, anonKey, devEmailSignIn],
  );
}

// --- Fake mode: a synthetic user. The session lives in this browser's storage. ---

const FAKE_KEY = "fundtrail.fake-session";
export const FAKE_USER: SignedInUser = { id: "user-fake", email: "accountant@university.example", name: "Demo accountant", method: "fake" };

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

export function SupabaseAuthProvider({
  url,
  anonKey,
  devEmailSignIn = false,
  children,
}: {
  url: string;
  anonKey: string;
  devEmailSignIn?: boolean;
  children: ReactNode;
}) {
  return <AuthContext.Provider value={useSupabaseAuth(url, anonKey, devEmailSignIn)}>{children}</AuthContext.Provider>;
}

/** The sidebar's line on how the user signed in. */
export function signedInWith(user: SignedInUser): string {
  switch (user.method) {
    case "google":
      return "Signed in with Google";
    case "email":
      return "Signed in with an email link";
    case "fake":
      return "Fake sign-in, no Supabase project";
    default:
      return "Signed in";
  }
}

export function FakeAuthProvider({ children }: { children: ReactNode }) {
  return <AuthContext.Provider value={useFakeAuth()}>{children}</AuthContext.Provider>;
}

/** For tests: a fixed auth state. */
export function StaticAuthProvider({ value, children }: { value: Auth; children: ReactNode }) {
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth needs an auth provider");
  return auth;
}

/** The signed-in user's ID, or null. */
export function useUserId(): string | null {
  const { state } = useAuth();
  return state.status === "signed_in" ? state.user.id : null;
}
