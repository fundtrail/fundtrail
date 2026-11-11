import { describe, expect, it } from "vitest";
import { readConfig } from "./config";

const real = {
  NEXT_PUBLIC_API_URL: "https://api.example",
  NEXT_PUBLIC_SUPABASE_URL: "https://project.supabase.example",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: "public-anon-key",
};

describe("readConfig", () => {
  it("is fake only when NEXT_PUBLIC_FAKE is 1", () => {
    expect(readConfig({ NEXT_PUBLIC_FAKE: "1" })).toEqual({ mode: "fake" });
    expect(readConfig({ ...real, NEXT_PUBLIC_FAKE: "1" })).toEqual({ mode: "fake" });
  });

  it("is real when all three settings are there", () => {
    expect(readConfig(real)).toEqual({
      mode: "real",
      apiUrl: real.NEXT_PUBLIC_API_URL,
      supabaseUrl: real.NEXT_PUBLIC_SUPABASE_URL,
      supabaseAnonKey: real.NEXT_PUBLIC_SUPABASE_ANON_KEY,
      devEmailSignIn: false,
    });
  });

  it("offers email sign-in only when asked for, and never in a production build (ruling 63)", () => {
    const on = (env: Record<string, string>) => {
      const config = readConfig({ ...real, ...env });
      return config.mode === "real" && config.devEmailSignIn;
    };
    expect(on({ NEXT_PUBLIC_DEV_EMAIL_SIGNIN: "1", NODE_ENV: "development" })).toBe(true);
    expect(on({ NEXT_PUBLIC_DEV_EMAIL_SIGNIN: "1", NODE_ENV: "production" })).toBe(false);
    expect(on({ NODE_ENV: "development" })).toBe(false);
    expect(on({ NEXT_PUBLIC_DEV_EMAIL_SIGNIN: "true", NODE_ENV: "development" })).toBe(false);
  });

  it("is an error naming every missing setting, never a fallback to the fake", () => {
    expect(readConfig({})).toEqual({
      mode: "error",
      missing: ["NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY"],
    });
    expect(readConfig({ ...real, NEXT_PUBLIC_API_URL: "" })).toEqual({ mode: "error", missing: ["NEXT_PUBLIC_API_URL"] });
    expect(readConfig({ ...real, NEXT_PUBLIC_FAKE: "0", NEXT_PUBLIC_SUPABASE_ANON_KEY: undefined })).toEqual({
      mode: "error",
      missing: ["NEXT_PUBLIC_SUPABASE_ANON_KEY"],
    });
  });
});
