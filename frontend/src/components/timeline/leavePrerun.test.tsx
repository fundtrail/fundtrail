import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient, type TimelineView } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { TimelinePanel } from "./TimelinePanel";

/** The panel on a grant on a prerun's run-through, where a plain move to `leavesAt` or later would leave it. */
async function onTheRunThrough(leavesAt: (view: TimelineView) => string | null) {
  const client: ApiClient = createFakeApiClient();
  await client.startOver(SAMPLE_GRANT_ID, true);
  const base = await client.getTimeline(SAMPLE_GRANT_ID);
  const view: TimelineView = { ...base, on_run_through: true, leaves_run_through_at: leavesAt(base) };
  vi.spyOn(client, "getTimeline").mockResolvedValue(view);
  const move = vi.spyOn(client, "moveTimeline");
  const auth = { state: { status: "signed_in" as const, user: FAKE_USER }, fake: true, signIn: async () => {}, signOut: async () => {}, getAccessToken: async () => null };
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StaticAuthProvider value={auth}>
        <ApiProvider client={client}>{children}</ApiProvider>
      </StaticAuthProvider>
    );
  }
  render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
  const next = await screen.findByRole("button", { name: "Next event" });
  await waitFor(() => expect(next).toBeEnabled());
  return { view, move, next };
}

const firstComingUp = (v: TimelineView) => (v.coming_up ?? [])[0].at;

describe("asking before a move leaves the prerun", () => {
  it("asks before Next event would leave; Stay makes no move", async () => {
    const { move, next } = await onTheRunThrough(firstComingUp);
    fireEvent.click(next);
    expect(await screen.findByRole("group", { name: "Leave the prerun?" })).toBeInTheDocument();
    expect(screen.getByText(/the agent works live, which takes minutes for each file/)).toBeInTheDocument();
    // Staying is the default.
    expect(screen.getByRole("button", { name: "Stay on the prerun" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Stay on the prerun" }));
    expect(screen.queryByRole("group", { name: "Leave the prerun?" })).toBeNull();
    expect(move).not.toHaveBeenCalled();
  });

  it("makes the move once the user chooses to leave", async () => {
    const { move, next } = await onTheRunThrough(firstComingUp);
    fireEvent.click(next);
    fireEvent.click(await screen.findByRole("button", { name: "Leave the prerun" }));
    await waitFor(() => expect(move).toHaveBeenCalledWith(SAMPLE_GRANT_ID, {}));
  });

  it("doesn't ask when skipping the human steps, which keeps the grant on", async () => {
    const { move, next } = await onTheRunThrough(firstComingUp);
    fireEvent.click(await screen.findByRole("button", { name: "More" }));
    fireEvent.click(screen.getByLabelText("Skip the human steps"));
    fireEvent.click(next);
    await waitFor(() => expect(move).toHaveBeenCalledWith(SAMPLE_GRANT_ID, { skip_human_steps: true }));
    expect(screen.queryByRole("group", { name: "Leave the prerun?" })).toBeNull();
  });

  it("doesn't ask when the move passes no unmade step", async () => {
    const { move, next } = await onTheRunThrough(() => "2099-01-01T00:00:00Z");
    fireEvent.click(next);
    await waitFor(() => expect(move).toHaveBeenCalledWith(SAMPLE_GRANT_ID, {}));
    expect(screen.queryByRole("group", { name: "Leave the prerun?" })).toBeNull();
  });

  it("asks before Go to a date would leave", async () => {
    const { move } = await onTheRunThrough(firstComingUp);
    fireEvent.click(await screen.findByRole("button", { name: "More" }));
    fireEvent.change(screen.getByLabelText("Go to a date"), { target: { value: "2098-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(await screen.findByRole("group", { name: "Leave the prerun?" })).toBeInTheDocument();
    expect(move).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Leave the prerun" }));
    await waitFor(() => expect(move).toHaveBeenCalledWith(SAMPLE_GRANT_ID, { to: "2098-01-01T00:00:00Z" }));
  });

  it("shows Next highlight beside Next event on a prerun grant, without More", async () => {
    await onTheRunThrough(() => null);
    expect(screen.getByRole("button", { name: "Next highlight" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More" })).toHaveAttribute("aria-expanded", "false");
  });
});
