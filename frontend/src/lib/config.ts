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

export type AppConfig =
  | { mode: "fake" }
  | { mode: "real"; apiUrl: string; supabaseUrl: string; supabaseAnonKey: string }
  | { mode: "error"; missing: string[] };

export interface PublicEnv {
  NEXT_PUBLIC_FAKE?: string;
  NEXT_PUBLIC_API_URL?: string;
  NEXT_PUBLIC_SUPABASE_URL?: string;
  NEXT_PUBLIC_SUPABASE_ANON_KEY?: string;
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
  };
}

// Next.js inlines NEXT_PUBLIC_ values only where they're written out in full.
export const appConfig: AppConfig = readConfig({
  NEXT_PUBLIC_FAKE: process.env.NEXT_PUBLIC_FAKE,
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
});
