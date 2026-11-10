import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient, type TimelineView } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { sampleRecord, SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
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

describe("skipping the human steps (ruling 47)", () => {
  it("lets the sample accountant deliver and decide in the fake, listing its decisions", async () => {
    const api = createFakeApiClient();
    await api.startOver(SAMPLE_GRANT_ID, true);
    const view = await api.moveTimeline(SAMPLE_GRANT_ID, { to: "2025-11-14T12:00:00Z", skip_human_steps: true });
    // Both uploads were delivered for the user, and say so under Just happened.
    expect(view.now.deliveries).toEqual([]);
    expect((view.just_happened ?? []).map((p) => [p.event.name, p.delivered_by_sample_accountant])).toEqual([
      ["award_letter.txt", true],
      ["invoice_1001.txt", true],
      ["L-1001", false],
    ]);
    // The accountant's confirmation of the award terms is listed under the event it follows.
    const decisions = (view.just_happened ?? []).flatMap((p) => (p.scripted_decisions ?? []).map((d) => d.id));
    expect(decisions).toEqual(["rec-confirm-award-terms"]);
  });

  it("shows the user's own delivery under Just happened, untagged", async () => {
    const { client, Wrapper } = harness();
    await client.startOver(SAMPLE_GRANT_ID, true);
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    const deliver = await screen.findByRole("button", { name: "Deliver for me" });
    await waitFor(() => expect(deliver).toBeEnabled());
    fireEvent.click(deliver);
    await waitFor(() => expect(within(part("Just happened")).getByText("Delivered by you.")).toBeInTheDocument());
    expect(within(part("Just happened")).queryByText("Delivered for you by the sample accountant")).toBeNull();
  });

  it("sends skip_human_steps from Next event and Go to a date when chosen", async () => {
    const { client, Wrapper } = harness();
    await client.startOver(SAMPLE_GRANT_ID, true);
    const move = vi.spyOn(client, "moveTimeline");
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    const next = await screen.findByRole("button", { name: "Next event" });
    fireEvent.click(screen.getByLabelText("Skip the human steps"));
    fireEvent.click(next);
    await waitFor(() => expect(move).toHaveBeenCalledWith(SAMPLE_GRANT_ID, { skip_human_steps: true }));
    // What the sample accountant delivered shows under Just happened, not just gone from Now.
    await waitFor(() => expect(within(part("Just happened")).getAllByText("Delivered for you by the sample accountant")).toHaveLength(2));
    await waitFor(() => expect(next).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Go to a date"), { target: { value: "2025-11-15" } });
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    await waitFor(() => expect(move).toHaveBeenLastCalledWith(SAMPLE_GRANT_ID, { to: "2025-11-15T00:00:00Z", skip_human_steps: true }));
    // The date field starts empty again.
    expect((screen.getByLabelText("Go to a date") as HTMLInputElement).value).toBe("");

  });

  it("marks loaded results, lists the sample accountant's decisions, and says when the grant is off the run-through", async () => {
    const { client, Wrapper } = harness();
    const base = await client.getTimeline(SAMPLE_GRANT_ID);
    const view: TimelineView = {
      ...base,
      on_run_through: false,
      just_happened: [{ ...base.just_happened![0], loaded: true, scripted_decisions: [sampleRecord("rec-confirm-extension")] }],
    };
    vi.spyOn(client, "getTimeline").mockResolvedValue(view);
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    const just = await waitFor(() => part("Just happened"));
    expect(await within(just).findByText("Loaded from the prerun")).toBeInTheDocument();
    expect(within(within(just).getByRole("list", { name: "The sample accountant's decisions" })).getByText(/confirmed 1 record/)).toBeInTheDocument();
    expect(screen.getByText("This grant is off the run-through: from here the agent works live.")).toBeInTheDocument();
  });
});
