import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient, type GuideStep, type TimelineView } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { TimelinePanel } from "./TimelinePanel";

/** The panel showing the guide, at highlight `index` of 14 with `step` waiting (or none). */
async function guide(index: number, step: GuideStep | null, extra: Partial<TimelineView> = {}) {
  const client: ApiClient = createFakeApiClient();
  await client.startOver(SAMPLE_GRANT_ID, true);
  const base = await client.getTimeline(SAMPLE_GRANT_ID);
  const event = { ...(base.coming_up ?? [])[0], highlight: "Receipt photo you deliver", file_id: "file-receipt", charge_id: null };
  const view: TimelineView = {
    ...base,
    highlight_index: index,
    highlight_total: 14,
    highlight_event: event,
    your_step: step,
    sign_off_at: "2027-03-09T00:00:00Z",
    ...extra,
  };
  vi.spyOn(client, "getTimeline").mockResolvedValue(view);
  const move = vi.spyOn(client, "moveTimeline");
  const deliver = vi.spyOn(client, "deliverForMe");
  const auth = { state: { status: "signed_in" as const, user: FAKE_USER }, fake: true, signIn: async () => {}, signOut: async () => {}, getAccessToken: async () => null };
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StaticAuthProvider value={auth}>
        <ApiProvider client={client}>{children}</ApiProvider>
      </StaticAuthProvider>
    );
  }
  render(<TimelinePanel grantId={SAMPLE_GRANT_ID} workspaceId="ws-sample" />, { wrapper: Wrapper });
  await screen.findByText(`Highlight ${index} of 14`);
  return { move, deliver };
}

const next = () => screen.getByRole("button", { name: "Next highlight" });

describe("the timeline guide", () => {
  it("says where you are, what happened, and the progress", async () => {
    await guide(2, null);
    expect(screen.getByText("Receipt photo you deliver")).toBeInTheDocument();
    expect(screen.getByText(/phone photo of a taxi receipt/)).toBeInTheDocument();
    expect(document.querySelectorAll(".ft-guide__seg")).toHaveLength(14);
    expect(document.querySelectorAll(".ft-guide__seg--done")).toHaveLength(2);
  });

  it("with nothing waiting, Next highlight is the one filled button and moves", async () => {
    const { move } = await guide(2, null);
    expect(screen.getByText("Nothing for you to do here.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the file" })).not.toHaveClass("ft-btn--main");
    expect(next()).toHaveClass("ft-btn--main");
    expect(document.querySelectorAll(".ft-btn--main")).toHaveLength(1);
    fireEvent.click(next());
    await waitFor(() => expect(move).toHaveBeenCalledWith(SAMPLE_GRANT_ID, { next_highlight: true }));
  });

  it("with a step waiting, the step's button is filled and Next highlight waits for it", async () => {
    const { deliver } = await guide(2, { action: "deliver_file", open: "delivery", id: "event-receipt" });
    expect(screen.getByText(/bring the photo in/)).toBeInTheDocument();
    const step = screen.getByRole("button", { name: "Deliver for me" });
    expect(step).toHaveClass("ft-btn--main");
    expect(screen.getByRole("button", { name: "Get the file" })).toBeInTheDocument();
    expect(next()).toBeDisabled();
    expect(next()).not.toHaveClass("ft-btn--main");
    expect(screen.getByText("Do your step first")).toBeInTheDocument();
    fireEvent.click(step);
    await waitFor(() => expect(deliver).toHaveBeenCalledWith(SAMPLE_GRANT_ID, "event-receipt"));
  });

  it.each([
    [{ action: "confirm_terms", open: "terms" } as GuideStep, "Go to Grant terms", "/grants/grant-sample/terms"],
    [{ action: "let_in_mail", open: "held_mail" } as GuideStep, "Go to Held mail", "/w/ws-sample/mail"],
    [{ action: "decide_suggestion", open: "charge", id: "chg-1" } as GuideStep, "Open the suggestion", "/grants/grant-sample/charges/chg-1"],
    [{ action: "accept_reason", open: "problems" } as GuideStep, "Open the problem", "/grants/grant-sample/problems"],
  ])("takes the user to the step: %s", async (step, name, href) => {
    await guide(3, step);
    const link = screen.getByRole("link", { name });
    expect(link.getAttribute("href")).toContain(href.split("/").slice(-1)[0]);
    expect(link).toHaveClass("ft-btn--main");
  });

  it("while the agent is still reading, Next highlight waits and says so", async () => {
    await guide(2, null, { catching_up: true });
    expect(next()).toBeDisabled();
    expect(screen.getByText("The agent is still reading what arrived.")).toBeInTheDocument();
  });

  it("after the last highlight, moves to the sign-off's date with the human steps skipped", async () => {
    const { move } = await guide(14, null);
    expect(screen.getByText(/Every highlight is played. To close out, move to Mar 9, 2027 and sign off./)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Move to Mar 9, 2027" }));
    await waitFor(() => expect(move).toHaveBeenCalledWith(SAMPLE_GRANT_ID, { to: "2027-03-09T00:00:00Z", skip_human_steps: true }));
    expect(screen.getByRole("link", { name: "Go to Closeout" })).toBeInTheDocument();
  });

  it("keeps the other controls under More", async () => {
    await guide(2, null);
    expect(screen.queryByRole("button", { name: "Next event" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(await screen.findByRole("button", { name: "Next event" })).toBeInTheDocument();
    expect(screen.getByLabelText("Go to a date")).toBeInTheDocument();
    expect(screen.getByLabelText("Skip the human steps")).toBeInTheDocument();
  });
});
