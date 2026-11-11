// What the browser build is configured with. Every value here is public: the
// Supabase URL and its anon (publishable) key are meant for the browser. No
// secret belongs in a NEXT_PUBLIC_ variable.
//
// Two modes, never mixed:
// - Fake: NEXT_PUBLIC_FAKE=1. Synthetic data from the fake API and a fake
//   sign-in, with no backend and no Supabase project. Every screen says so.
// - Real: all three of NEXT_PUBLIC_API_URL, NEXT_PUBLIC_SUPABASE_URL and
//   NEXT_PUBLIC_SUPABASE_ANON_KEY. A missing one is an error the app shows by
//   name; it never falls back to the fake.
//
// NEXT_PUBLIC_DEV_EMAIL_SIGNIN=1 adds an email sign-in link beside Google, for
// local development (ruling 63). A production build ignores it.

export type AppConfig =
  | { mode: "fake" }
  | { mode: "real"; apiUrl: string; supabaseUrl: string; supabaseAnonKey: string; devEmailSignIn: boolean }
  | { mode: "error"; missing: string[] };

export interface PublicEnv {
  NEXT_PUBLIC_FAKE?: string;
  NEXT_PUBLIC_API_URL?: string;
  NEXT_PUBLIC_SUPABASE_URL?: string;
  NEXT_PUBLIC_SUPABASE_ANON_KEY?: string;
  NEXT_PUBLIC_DEV_EMAIL_SIGNIN?: string;
  /** Next.js's build: "production" for `next build`, "development" for `next dev`. */
  NODE_ENV?: string;
}

export function readConfig(env: PublicEnv): AppConfig {
  if (env.NEXT_PUBLIC_FAKE === "1") return { mode: "fake" };
  const required = ["NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY"] as const;
  const missing = required.filter((name) => !env[name]);
  if (missing.length > 0) return { mode: "error", missing };
  return {
    mode: "real",
    apiUrl: env.NEXT_PUBLIC_API_URL!,
    supabaseUrl: env.NEXT_PUBLIC_SUPABASE_URL!,
    supabaseAnonKey: env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    // Ruling 63: email sign-in for local development only. Never in a production build.
    devEmailSignIn: env.NEXT_PUBLIC_DEV_EMAIL_SIGNIN === "1" && env.NODE_ENV !== "production",
  };
}

// Next.js inlines NEXT_PUBLIC_ values only where they're written out in full.
export const appConfig: AppConfig = readConfig({
  NEXT_PUBLIC_FAKE: process.env.NEXT_PUBLIC_FAKE,
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  NEXT_PUBLIC_DEV_EMAIL_SIGNIN: process.env.NEXT_PUBLIC_DEV_EMAIL_SIGNIN,
  NODE_ENV: process.env.NODE_ENV,
});
