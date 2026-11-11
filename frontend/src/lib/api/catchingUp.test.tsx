import { render, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StaticAuthProvider, type Auth } from "../auth";
import { createFakeApiClient } from "./fake";
import { SAMPLE_GRANT_ID } from "./fixtures/sample";
import { ApiProvider, CATCHING_UP_REFRESH_MS, useTimeline, type ApiClient } from "./index";

afterEach(() => vi.useRealTimers());

const auth: Auth = {
  state: { status: "signed_in", user: { id: "u1", email: "a@university.example", name: null } },
  fake: true,
  signIn: async () => {},
  signOut: async () => {},
  getAccessToken: async () => null,
};

function Timeline() {
  const { data } = useTimeline(SAMPLE_GRANT_ID);
  return <p>{data ? String(data.catching_up) : "…"}</p>;
}

function wrapperFor(client: ApiClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StaticAuthProvider value={auth}>
        <ApiProvider client={client}>{children}</ApiProvider>
      </StaticAuthProvider>
    );
  };
}

describe("the timeline while the agent catches up", () => {
  it("refetches every few seconds until it has caught up, then stops", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const client = createFakeApiClient();
    const base = await client.getTimeline(SAMPLE_GRANT_ID);
    const get = vi
      .spyOn(client, "getTimeline")
      .mockResolvedValueOnce({ ...base, catching_up: true })
      .mockResolvedValue({ ...base, catching_up: false });
    render(<Timeline />, { wrapper: wrapperFor(client) });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    await vi.advanceTimersByTimeAsync(CATCHING_UP_REFRESH_MS + 100);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await vi.advanceTimersByTimeAsync(CATCHING_UP_REFRESH_MS * 3);
    expect(get).toHaveBeenCalledTimes(2);
  });
});
