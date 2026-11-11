import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, SampleRefusalError, type ApiClient, type GrantSummary, type TimelineView } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { sampleRecord, SAMPLE_GRANT_ID, WORKSPACE_ID } from "@/lib/api/fixtures/sample";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { SampleTimeline, TimelinePanel } from "./TimelinePanel";

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

/** The panel shows folded; More opens the controls and the trail these tests read. */
async function openMore() {
  fireEvent.click(await screen.findByRole("button", { name: "More" }));
}

describe("TimelinePanel", () => {
  it("shows the three parts where the sample stands, with the problem list count linked", async () => {
    const { Wrapper } = harness();
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    await openMore();
    await screen.findByText("Just happened");
    expect(within(part("Just happened")).getByText("extension_notice.txt")).toBeInTheDocument();
    expect(within(part("Just happened")).getByText("The agent wrote: Period of performance.")).toBeInTheDocument();
    expect(within(part("Now")).getByText("Apr 9, 2026")).toBeInTheDocument();
    expect(within(part("Now")).getByRole("link", { name: "3 waiting on the problem list" })).toHaveAttribute("href", "/grants/grant-sample/problems");
    expect(within(part("Coming up")).getByText("The timeline has played to its end.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next event" })).toBeDisabled();
  });

  it("starts over only after the confirm step, then plays the next event and delivers for the user", async () => {
    const { client, Wrapper } = harness();
    const startOver = vi.spyOn(client, "startOver");
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    await openMore();
    fireEvent.click(await screen.findByRole("button", { name: "Start over" }));
    expect(startOver).not.toHaveBeenCalled();
    const confirm = screen.getByRole("group", { name: "Start this sample over?" });
    expect(within(confirm).getByRole("button", { name: "Cancel" })).toHaveFocus();
    fireEvent.click(within(confirm).getByRole("button", { name: "Start over" }));
    await waitFor(() => expect(within(part("Now")).getAllByText("Jan 12, 2023").length).toBeGreaterThan(0));
    expect(startOver).toHaveBeenCalledWith(SAMPLE_GRANT_ID, true);
    // A sample starts at its first event, played: the award letter, for the user to deliver.
    expect(within(part("Coming up")).getAllByRole("listitem")).toHaveLength(5);
    const deliveries = await screen.findByRole("list", { name: "For you to deliver" });
    expect(within(deliveries).getByText("award_letter.txt")).toBeInTheDocument();
    expect(within(deliveries).getByRole("button", { name: "Get the file" })).toBeInTheDocument();
    // Each action waits until the last one has finished refetching and the buttons work again.
    const deliver = within(deliveries).getByRole("button", { name: "Deliver for me" });
    await waitFor(() => expect(deliver).toBeEnabled());
    fireEvent.click(deliver);
    await waitFor(() => expect(screen.queryByRole("list", { name: "For you to deliver" })).toBeNull());

    const nextEvent = screen.getByRole("button", { name: "Next event" });
    await waitFor(() => expect(nextEvent).toBeEnabled());
    fireEvent.click(nextEvent);
    const next = await screen.findByRole("list", { name: "For you to deliver" });
    expect(within(next).getByText("invoice_1001.txt")).toBeInTheDocument();
    expect(within(part("Coming up")).getAllByRole("listitem")).toHaveLength(4);
  });

  it("goes to a date only forward, and links a played ledger line to its charge", async () => {
    const { client, Wrapper } = harness();
    await client.startOver(SAMPLE_GRANT_ID, true);
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    await openMore();
    const input = (await screen.findByLabelText("Go to a date")) as HTMLInputElement;
    expect(input.min).toBe("2023-01-13");
    fireEvent.change(input, { target: { value: "2025-11-15" } });
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    await waitFor(() => expect(within(part("Just happened")).getByText("L-1001", { selector: ".ft-tl__name" })).toBeInTheDocument());
    expect(within(part("Just happened")).getByRole("link", { name: /open the charge from L-1001$/i })).toHaveAttribute("href", "/grants/grant-sample/charges/chg-l-1001");
  });
});

describe("a played charge's link (issue 275)", () => {
  async function playL1001(client: ApiClient) {
    await client.startOver(SAMPLE_GRANT_ID, true);
    await client.moveTimeline(SAMPLE_GRANT_ID, { to: "2025-11-15T00:00:00Z" });
  }

  it("reads the charge's ledger line ID once the charges are loaded", async () => {
    const { client, Wrapper } = harness();
    await playL1001(client);
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    await openMore();
    // What it says aloud starts with what it shows.
    const link = await screen.findByRole("link", { name: "L-1001, open the charge from L-1001" });
    expect(link).toHaveTextContent("L-1001");
    expect(link).toHaveAttribute("href", "/grants/grant-sample/charges/chg-l-1001");
  });

  it("reads \"Open the charge\" while the charges aren't loaded", async () => {
    const { client, Wrapper } = harness();
    await playL1001(client);
    vi.spyOn(client, "listCharges").mockReturnValue(new Promise(() => {}));
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    await openMore();
    const link = await screen.findByRole("link", { name: "Open the charge from L-1001" });
    expect(link).toHaveTextContent("Open the charge");
  });
});

describe("a refused move", () => {
  it("shows the refusal's message with a link to the sample that's still working", async () => {
    const { client, Wrapper } = harness();
    const [other] = await client.listGrants(WORKSPACE_ID);
    const blocking: GrantSummary = { ...other, grant: { ...other.grant, id: "grant-other", title: "Other sample" } };
    await client.startOver(SAMPLE_GRANT_ID, true);
    vi.spyOn(client, "moveTimeline").mockRejectedValueOnce(
      new SampleRefusalError({ reason: "another_sample_working", message: "Another sample is still working.", grant: blocking }),
    );
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    fireEvent.click(await screen.findByRole("button", { name: "Next event" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Another sample is still working.");
    expect(within(alert).getByRole("link", { name: "Open Other sample" })).toHaveAttribute("href", "/grants/grant-other");
  });
});

describe("the folded line", () => {
  it("shows where the clock stands, what it stopped on and what waits, and More opens every other control and the trail in place", async () => {
    const { Wrapper } = harness();
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    const more = await screen.findByRole("button", { name: "More" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    expect(more).not.toHaveAttribute("aria-controls");
    expect(screen.getByRole("heading", { name: "Sample timeline" })).toBeInTheDocument();
    expect(screen.getByText("Apr 9, 2026")).toBeInTheDocument();
    expect(screen.getByText("extension_notice.txt")).toBeInTheDocument();
    expect(screen.getByText("An extension notice")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "3 waiting on the problem list" })).toHaveAttribute("href", "/grants/grant-sample/problems");
    expect(screen.getByText("The timeline has played to its end.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next event" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Next highlight" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Just happened" })).toBeNull();
    fireEvent.click(more);
    const less = screen.getByRole("button", { name: "Less" });
    expect(less).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById(less.getAttribute("aria-controls")!)).not.toBeNull();
    expect(screen.getByRole("button", { name: "Next highlight" })).toBeInTheDocument();
    expect(screen.getByLabelText("Go to a date")).toBeInTheDocument();
    expect(screen.getByLabelText("Skip the human steps")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start over" })).toBeInTheDocument();
    expect(within(part("Just happened")).getByText("The agent wrote: Period of performance.")).toBeInTheDocument();
  });

  it("marks a stop loaded from the prerun, lists the sample accountant's decisions on it, and names what comes next, while folded", async () => {
    const { client, Wrapper } = harness();
    const base = await client.getTimeline(SAMPLE_GRANT_ID);
    const stop = base.now.stopped_on!;
    const coming = { ...stop, id: "event-next", at: "2026-04-20T12:00:00Z", name: "invoice_2002.eml", highlight: "A late bill" };
    const view: TimelineView = {
      ...base,
      finished: false,
      just_happened: [{ event: stop, loaded: true, scripted_decisions: [sampleRecord("rec-confirm-extension")] }],
      coming_up: [coming],
    };
    vi.spyOn(client, "getTimeline").mockResolvedValue(view);
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    const also = await screen.findByRole("list", { name: "About the stop and what comes next" });
    expect(within(also).getByText("Loaded from the prerun")).toBeInTheDocument();
    expect(within(also).getByText(/The sample accountant: confirmed 1 record/)).toBeInTheDocument();
    expect(within(also).getByText("invoice_2002.eml")).toBeInTheDocument();
    expect(within(also).getByText("Apr 20, 2026")).toBeInTheDocument();
    expect(within(also).getByText("A late bill")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More" })).toHaveAttribute("aria-expanded", "false");
  });

  it("shows a refused move while folded", async () => {
    const { client, Wrapper } = harness();
    await client.startOver(SAMPLE_GRANT_ID, true);
    vi.spyOn(client, "moveTimeline").mockRejectedValueOnce(new SampleRefusalError({ reason: "another_sample_working", message: "Another sample is still working.", grant: null }));
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    const next = await screen.findByRole("button", { name: "Next event" });
    await waitFor(() => expect(next).toBeEnabled());
    fireEvent.click(next);
    expect(await screen.findByRole("alert")).toHaveTextContent("Another sample is still working.");
    expect(screen.getByRole("button", { name: "More" })).toHaveAttribute("aria-expanded", "false");
  });
});

describe("SampleTimeline", () => {
  it("shows the panel only on a sample grant", async () => {
    const { client, Wrapper } = harness();
    const [sampleRow] = await client.listGrants(WORKSPACE_ID);
    const plain: GrantSummary = { ...sampleRow, grant: { ...sampleRow.grant, sample: null } };
    const { rerender } = render(<SampleTimeline summary={plain} />, { wrapper: Wrapper });
    expect(screen.queryByRole("heading", { name: "Sample timeline" })).toBeNull();
    rerender(<SampleTimeline summary={sampleRow} />);
    expect(await screen.findByRole("heading", { name: "Sample timeline" })).toBeInTheDocument();
  });
});
