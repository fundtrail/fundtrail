import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, ApiProvider, type ApiClient } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { FAKE_USER, StaticAuthProvider, type Auth } from "@/lib/auth";
import Home from "./page";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

const auth: Auth = {
  state: { status: "signed_in", user: FAKE_USER },
  fake: true,
  signIn: async () => {},
  signOut: async () => {},
  getAccessToken: async () => null,
};

function renderHome(client: ApiClient) {
  return render(
    <StaticAuthProvider value={auth}>
      <ApiProvider client={client}>
        <Home />
      </ApiProvider>
    </StaticAuthProvider>,
  );
}

describe("the home page (ruling 64)", () => {
  it("opens the first workspace", async () => {
    replace.mockClear();
    renderHome(createFakeApiClient());
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/w/ws-sample"));
  });

  it("treats a signed-in user with no workspace as an error, with Try again", async () => {
    const client = createFakeApiClient();
    const list = vi.spyOn(client, "listWorkspaces").mockResolvedValueOnce([]);
    renderHome(client);
    expect(await screen.findByRole("alert")).toHaveTextContent("Your workspace wasn't set up when you signed in.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });

  it("says so when the request fails", async () => {
    const client = createFakeApiClient();
    vi.spyOn(client, "listWorkspaces").mockRejectedValueOnce(new ApiError(500, "boom"));
    renderHome(client);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load your workspace.");
  });
});
