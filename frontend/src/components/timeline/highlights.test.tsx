import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { TimelinePanel } from "./TimelinePanel";

/** These tests read the folded line, so the fake's view goes without the guide's fields (the guide has its own tests). */
function unguided(client: ApiClient): ApiClient {
  const getTimeline = client.getTimeline.bind(client);
  client.getTimeline = async (grantId) => ({ ...(await getTimeline(grantId)), highlight_total: null });
  return client;
}


function harness() {
  const client: ApiClient = unguided(createFakeApiClient());
  const auth = { state: { status: "signed_in" as const, user: FAKE_USER }, fake: true, signIn: async () => {}, signOut: async () => {}, getAccessToken: async () => null };
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StaticAuthProvider value={auth}>
        <ApiProvider client={client}>{children}</ApiProvider>
      </StaticAuthProvider>
    );
  }
  return { client, Wrapper };
}

const part = (name: string) => screen.getByRole("heading", { name }).closest("section")!;

/** The panel shows folded; More opens the controls and the trail these tests read. */
async function openMore() {
  fireEvent.click(await screen.findByRole("button", { name: "More" }));
}

describe("highlights (ruling 58)", () => {
  it("marks highlights in Coming up, and Next highlight asks the server for the next one (ruling 77)", async () => {
    const { client, Wrapper } = harness();
    await client.startOver(SAMPLE_GRANT_ID, true);
    // The fake doesn't know next_highlight yet; it stands in for the server by moving to the highlight.
    const real = client.moveTimeline.bind(client);
    const move = vi
      .spyOn(client, "moveTimeline")
      .mockImplementation((grantId, body) => real(grantId, body.next_highlight ? { to: "2026-02-21T17:30:00Z", skip_human_steps: true } : body));
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    await openMore();
    await screen.findByRole("heading", { name: "Coming up" });
    const coming = part("Coming up");
    expect(within(coming).getByText("Highlight: A bill by email")).toBeInTheDocument();
    expect(within(coming).getByText("Highlight: Work after the end date")).toBeInTheDocument();

    const next = screen.getByRole("button", { name: "Next highlight" });
    // It says what it does, whatever the Skip checkbox says.
    expect(next).toHaveAccessibleDescription("Moves to the next highlight; the steps before it are done for you, the highlight's own step is yours.");
    expect(screen.getByLabelText("Skip the human steps")).not.toBeChecked();
    await waitFor(() => expect(next).toBeEnabled());
    fireEvent.click(next);
    // Exactly this body: no date and no skip flag; the server finds the stop.
    await waitFor(() => expect(move).toHaveBeenCalledWith(SAMPLE_GRANT_ID, { next_highlight: true }));
    expect(move.mock.calls[0][1]).toStrictEqual({ next_highlight: true });
    // The highlight it moved to is marked under Just happened too.
    await waitFor(() => expect(within(part("Just happened")).getByText("Highlight: A bill by email")).toBeInTheDocument());
    expect(within(part("Coming up")).queryByText("Highlight: A bill by email")).toBeNull();
  });

  it("doesn't decide on its own that no highlight is left: only the server's reason makes it unavailable", async () => {
    const { Wrapper } = harness();
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    await openMore();
    // Where the fake stands, everything has played, and the fake gives no reason.
    const next = await screen.findByRole("button", { name: "Next highlight" });
    await waitFor(() => expect(next).toBeEnabled());
    expect(next).not.toHaveAttribute("aria-disabled");
  });
});
