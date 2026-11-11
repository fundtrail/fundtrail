import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, ApiProvider, type FtRecord } from "./api";
import { createFakeApiClient } from "./api/fake";
import { SAMPLE_GRANT_ID } from "./api/fixtures/sample";
import { FAKE_USER, StaticAuthProvider } from "./auth";
import { useWrite } from "./useWrite";

const body = { data: { kind: "retraction" as const } };

function setup() {
  const client = createFakeApiClient();
  const send = vi.spyOn(client, "writeRecord");
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StaticAuthProvider
        value={{ state: { status: "signed_in", user: FAKE_USER }, fake: true, signIn: async () => {}, signOut: async () => {}, getAccessToken: async () => null }}
      >
        <ApiProvider client={client}>{children}</ApiProvider>
      </StaticAuthProvider>
    );
  }
  const hook = renderHook(() => useWrite(), { wrapper: Wrapper });
  return { send, hook };
}

describe("useWrite", () => {
  it("sends one request for two calls in the same tick, and both get its result", async () => {
    const { send, hook } = setup();
    let first: FtRecord | null = null;
    let second: FtRecord | null = null;
    await act(async () => {
      const a = hook.result.current.write(SAMPLE_GRANT_ID, body);
      const b = hook.result.current.write(SAMPLE_GRANT_ID, body);
      [first, second] = await Promise.all([a, b]);
    });
    expect(send).toHaveBeenCalledTimes(1);
    expect(first).not.toBeNull();
    expect(second).toBe(first);
  });

  it("sends again once the first write has settled", async () => {
    const { send, hook } = setup();
    await act(async () => {
      await hook.result.current.write(SAMPLE_GRANT_ID, body);
    });
    await act(async () => {
      await hook.result.current.write(SAMPLE_GRANT_ID, body);
    });
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("releases the guard when a write fails, too", async () => {
    const { send, hook } = setup();
    send.mockRejectedValueOnce(new ApiError(422, ["The note is missing."]));
    await act(async () => {
      expect(await hook.result.current.write(SAMPLE_GRANT_ID, body)).toBeNull();
    });
    expect(hook.result.current.state).toEqual({ status: "failed", problems: ["The note is missing."] });
    await act(async () => {
      await hook.result.current.write(SAMPLE_GRANT_ID, body);
    });
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("sends nothing for a second call with different arguments while one is in flight", async () => {
    const { send, hook } = setup();
    await act(async () => {
      const a = hook.result.current.write(SAMPLE_GRANT_ID, body);
      const b = hook.result.current.write("another-grant", { data: { kind: "retraction" as const } });
      const [first, second] = await Promise.all([a, b]);
      expect(second).toBe(first);
    });
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith(SAMPLE_GRANT_ID, body);
  });

  it("releases the guard when the client throws synchronously", async () => {
    const { send, hook } = setup();
    send.mockImplementationOnce(() => {
      throw new ApiError(422, ["The note is missing."]);
    });
    await act(async () => {
      expect(await hook.result.current.write(SAMPLE_GRANT_ID, body)).toBeNull();
    });
    expect(hook.result.current.state).toEqual({ status: "failed", problems: ["The note is missing."] });
    let again: FtRecord | null = null;
    await act(async () => {
      again = await hook.result.current.write(SAMPLE_GRANT_ID, body);
    });
    expect(send).toHaveBeenCalledTimes(2);
    expect(again).not.toBeNull();
  });
});
