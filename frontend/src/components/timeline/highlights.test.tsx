import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { TimelinePanel } from "./TimelinePanel";

function harness() {
  const client: ApiClient = createFakeApiClient();
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

describe("highlights (ruling 58)", () => {
  it("marks highlights in Coming up, and Next highlight moves to the next one with the human steps skipped", async () => {
    const { client, Wrapper } = harness();
    await client.startOver(SAMPLE_GRANT_ID, true);
    const move = vi.spyOn(client, "moveTimeline");
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    await screen.findByRole("heading", { name: "Coming up" });
    const coming = part("Coming up");
    expect(within(coming).getByText("Highlight: A bill by email")).toBeInTheDocument();
    expect(within(coming).getByText("Highlight: Work after the end date")).toBeInTheDocument();

    const next = screen.getByRole("button", { name: "Next highlight" });
    // It says it skips the human steps, since the Skip checkbox stays unticked.
    expect(next).toHaveAccessibleDescription("Always skips the human steps.");
    expect(screen.getByLabelText("Skip the human steps")).not.toBeChecked();
    await waitFor(() => expect(next).toBeEnabled());
    fireEvent.click(next);
    await waitFor(() => expect(move).toHaveBeenCalledWith(SAMPLE_GRANT_ID, { to: "2026-02-21T17:30:00Z", skip_human_steps: true }));
    // The highlight it moved to is marked under Just happened too.
    await waitFor(() => expect(within(part("Just happened")).getByText("Highlight: A bill by email")).toBeInTheDocument());
    expect(within(part("Coming up")).queryByText("Highlight: A bill by email")).toBeNull();
  });

  it("can't move to a highlight when none is coming up", async () => {
    const { Wrapper } = harness();
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    // Where the fake stands, everything has played.
    expect(await screen.findByRole("button", { name: "Next highlight" })).toBeDisabled();
  });
});
