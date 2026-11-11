import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StaticAuthProvider, type Auth } from "../auth";
import { createFakeApiClient } from "./fake";
import { ApiProvider, usePings } from "./index";

function Screen({ topic }: { topic: string }) {
  usePings(topic);
  return null;
}

describe("usePings", () => {
  it("keeps one channel across a session renewal, and moves it when the topic changes", () => {
    const stop = vi.fn();
    const listen = vi.fn(() => stop);
    const client = createFakeApiClient();
    const user = { id: "u1", email: "a@university.example", name: null };
    const auth = (token: string): Auth => ({
      state: { status: "signed_in", user },
      fake: false,
      signIn: async () => {},
      signOut: async () => {},
      getAccessToken: async () => token,
      listen,
    });
    const tree = (a: Auth, topic: string) => (
      <StaticAuthProvider value={a}>
        <ApiProvider client={client}>
          <Screen topic={topic} />
        </ApiProvider>
      </StaticAuthProvider>
    );
    const { rerender } = render(tree(auth("t1"), "grant:g1"));
    // A renewed session is a new auth value with the same user and the same listener.
    rerender(tree(auth("t2"), "grant:g1"));
    expect(listen).toHaveBeenCalledTimes(1);
    expect(stop).not.toHaveBeenCalled();
    rerender(tree(auth("t2"), "grant:g2"));
    expect(listen).toHaveBeenCalledTimes(2);
    expect(stop).toHaveBeenCalledTimes(1);
  });
});
