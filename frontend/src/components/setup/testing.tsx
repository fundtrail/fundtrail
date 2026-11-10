import type { ReactNode } from "react";
import { vi } from "vitest";
import { ApiProvider, type ApiClient } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { FAKE_USER, StaticAuthProvider, type Auth } from "@/lib/auth";

const signedIn: Auth = {
  state: { status: "signed_in", user: FAKE_USER },
  fake: true,
  signIn: async () => {},
  signOut: async () => {},
  getAccessToken: async () => null,
};

/** The fake API with writeRecord spied on, signed in as the fake accountant. For this area's tests. */
export function fakeHarness() {
  const client: ApiClient = createFakeApiClient();
  const writeRecord = vi.spyOn(client, "writeRecord");
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StaticAuthProvider value={signedIn}>
        <ApiProvider client={client}>{children}</ApiProvider>
      </StaticAuthProvider>
    );
  }
  return { client, writeRecord, Wrapper };
}
