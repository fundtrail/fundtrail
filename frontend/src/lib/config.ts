// What the browser build is configured with. Every value here is public: the
// Supabase URL and its anon (publishable) key are meant for the browser. No
// secret belongs in a NEXT_PUBLIC_ variable.
//
// Without NEXT_PUBLIC_API_URL the screens read the synthetic fake API. Without
// the two Supabase values sign-in is faked. Both fakes need no account.

export const config = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL || null,
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL || null,
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || null,
};

export const fakeAuth = !(config.supabaseUrl && config.supabaseAnonKey);
export const fakeApi = !config.apiUrl;
