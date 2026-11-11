import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient, type TimelineView } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { TimelinePanel } from "./TimelinePanel";

const MOVE_REASON = "Another sample is still working: Grant B.";
const HIGHLIGHT_REASON = "No highlight is coming up.";

/** The panel at the sample's start, with the server's view adjusted as given. */
async function renderAt(adjust: Partial<TimelineView>) {
  const client: ApiClient = createFakeApiClient();
  await client.startOver(SAMPLE_GRANT_ID, true);
  const base = await client.getTimeline(SAMPLE_GRANT_ID);
  vi.spyOn(client, "getTimeline").mockResolvedValue({ ...base, ...adjust });
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
  return { move };
}

const button = (name: string) => screen.getByRole("button", { name });

async function openMore() {
  fireEvent.click(await screen.findByRole("button", { name: "More" }));
}

/** Picks a date and presses Go, then presses Enter in the date field. */
function goToDate() {
  const input = screen.getByLabelText("Go to a date") as HTMLInputElement;
  fireEvent.change(input, { target: { value: "2025-11-15" } });
  fireEvent.click(button("Go"));
  fireEvent.submit(input.form!);
}

describe("blocked moves say why (ruling 79)", () => {
  it("makes Next event and Go unavailable when the server says the timeline can't move, and says why in its words", async () => {
    const { move } = await renderAt({ move_unavailable_reason: MOVE_REASON });
    const next = await screen.findByRole("button", { name: "Next event" });
    // Folded, Next event's reason shows beside it without opening More.
    expect(next).toHaveAttribute("aria-disabled", "true");
    expect(next).toHaveAccessibleDescription(MOVE_REASON);
    expect(screen.getByText(MOVE_REASON)).toBeInTheDocument();
    fireEvent.click(next);
    fireEvent.keyDown(next, { key: "Enter" });

    await openMore();
    const go = button("Go");
    expect(go).toHaveAttribute("aria-disabled", "true");
    expect(go).toHaveAccessibleDescription(MOVE_REASON);
    goToDate();
    expect(move).not.toHaveBeenCalled();
    // Next highlight has no reason of its own, so it still works.
    expect(button("Next highlight")).not.toHaveAttribute("aria-disabled");
  });

  it("makes Next highlight unavailable when the server says so, and says why in its words", async () => {
    const { move } = await renderAt({ next_highlight_unavailable_reason: HIGHLIGHT_REASON });
    await openMore();
    const next = button("Next highlight");
    expect(next).toHaveAttribute("aria-disabled", "true");
    expect(next).toHaveAccessibleDescription(HIGHLIGHT_REASON);
    fireEvent.click(next);
    fireEvent.keyDown(next, { key: "Enter" });
    expect(move).not.toHaveBeenCalled();
    // Next event and Go have no reason, so they still work.
    expect(button("Next event")).not.toHaveAttribute("aria-disabled");
    expect(button("Go")).not.toHaveAttribute("aria-disabled");
  });

  it.each([
    ["null", { move_unavailable_reason: null, next_highlight_unavailable_reason: null }],
    ["absent", {}],
  ])("with %s reasons, each control sends its request once", async (_, adjust) => {
    const { move } = await renderAt(adjust);
    await openMore();
    expect(screen.queryByText(MOVE_REASON)).toBeNull();

    const next = button("Next event");
    await waitFor(() => expect(next).toBeEnabled());
    fireEvent.click(next);
    await waitFor(() => expect(move).toHaveBeenCalledTimes(1));
    expect(move.mock.calls[0][1]).toStrictEqual({});

    const highlight = button("Next highlight");
    await waitFor(() => expect(highlight).toBeEnabled());
    fireEvent.click(highlight);
    await waitFor(() => expect(move).toHaveBeenCalledTimes(2));
    expect(move.mock.calls[1][1]).toStrictEqual({ next_highlight: true });

    await waitFor(() => expect(button("Next event")).toBeEnabled());
    const input = screen.getByLabelText("Go to a date") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "2025-11-15" } });
    fireEvent.click(button("Go"));
    await waitFor(() => expect(move).toHaveBeenCalledTimes(3));
    expect(move.mock.calls[2][1]).toStrictEqual({ to: "2025-11-15T00:00:00Z" });
  });

  it("keeps sending skip_human_steps from Next event and Go to a date when ticked", async () => {
    const { move } = await renderAt({});
    await openMore();
    fireEvent.click(screen.getByLabelText("Skip the human steps"));
    const next = button("Next event");
    await waitFor(() => expect(next).toBeEnabled());
    fireEvent.click(next);
    await waitFor(() => expect(move).toHaveBeenCalledWith(SAMPLE_GRANT_ID, { skip_human_steps: true }));
  });
});
