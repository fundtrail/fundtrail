import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StaticAuthProvider, type Auth, type AuthState } from "../auth";
import { ApiError, HttpApiClient, type ApiClient } from "./client";
import { ApiProvider, useWorkspaces } from "./index";
import type { Workspace } from "./types";

afterEach(() => vi.unstubAllGlobals());

describe("HttpApiClient", () => {
  it("sends the access token as a Bearer header", async () => {
    const fetchMock = vi.fn(async () => new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await new HttpApiClient("https://api.example/", async () => "token-1").listWorkspaces();
    expect(fetchMock).toHaveBeenCalledWith("https://api.example/workspaces", {
      headers: { Accept: "application/json", Authorization: "Bearer token-1" },
    });
  });

  it("never sends a request without a token", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(new HttpApiClient("https://api.example", async () => null).listWorkspaces()).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

function auth(state: AuthState): Auth {
  return { state, fake: true, signIn: async () => {}, signOut: async () => {}, getAccessToken: async () => null };
}

function signedIn(id: string): Auth {
  return auth({ status: "signed_in", user: { id, email: `${id}@university.example`, name: null } });
}

function workspace(id: string, name: string): Workspace {
  return { id, name, owner_id: id, clock_now: null };
}

function clientFor(name: string): ApiClient & { listWorkspaces: ReturnType<typeof vi.fn> } {
  return {
    listWorkspaces: vi.fn(async () => [workspace(`ws-${name}`, `${name}'s workspace`)]),
  } as unknown as ApiClient & { listWorkspaces: ReturnType<typeof vi.fn> };
}

function Names() {
  const { data } = useWorkspaces();
  return <p data-testid="names">{data ? data.map((w) => w.name).join(",") : "none"}</p>;
}

function App({ value, client }: { value: Auth; client: ApiClient }) {
  return (
    <StaticAuthProvider value={value}>
      <ApiProvider client={client}>
        <Names />
      </ApiProvider>
    </StaticAuthProvider>
  );
}

describe("data hooks", () => {
  it("request nothing until a user is signed in", async () => {
    const client = clientFor("a");
    const { rerender } = render(<App value={auth({ status: "loading" })} client={client} />);
    rerender(<App value={auth({ status: "signed_out" })} client={client} />);
    await new Promise((r) => setTimeout(r, 20));
    expect(client.listWorkspaces).not.toHaveBeenCalled();
    expect(screen.getByTestId("names")).toHaveTextContent("none");

    rerender(<App value={signedIn("a")} client={client} />);
    await waitFor(() => expect(screen.getByTestId("names")).toHaveTextContent("a's workspace"));
  });

  it("never show the last user's data after a sign-out", async () => {
    const first = clientFor("a");
    const { rerender } = render(<App value={signedIn("a")} client={first} />);
    await waitFor(() => expect(screen.getByTestId("names")).toHaveTextContent("a's workspace"));

    rerender(<App value={auth({ status: "signed_out" })} client={first} />);
    expect(screen.getByTestId("names")).toHaveTextContent("none");

    // The next user's first render has an empty cache, before their data arrives.
    const second = clientFor("b");
    let resolve: (value: Workspace[]) => void = () => {};
    second.listWorkspaces.mockImplementation(() => new Promise<Workspace[]>((r) => (resolve = r)));
    rerender(<App value={signedIn("b")} client={second} />);
    expect(screen.getByTestId("names")).toHaveTextContent("none");
    resolve([workspace("ws-b", "b's workspace")]);
    await waitFor(() => expect(screen.getByTestId("names")).toHaveTextContent("b's workspace"));
    expect(screen.getByTestId("names")).not.toHaveTextContent("a's workspace");
  });
});
