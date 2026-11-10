import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, SampleRefusalError, type ApiClient, type GrantSummary } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID, WORKSPACE_ID } from "@/lib/api/fixtures/sample";
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

describe("TimelinePanel", () => {
  it("shows the three parts where the sample stands, with the problem list count linked", async () => {
    const { Wrapper } = harness();
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    await screen.findByText("Just happened");
    expect(within(part("Just happened")).getByText("extension_notice.txt")).toBeInTheDocument();
    expect(within(part("Just happened")).getByText("The agent wrote: Period of performance.")).toBeInTheDocument();
    expect(within(part("Now")).getByText("Apr 9, 2026")).toBeInTheDocument();
    expect(within(part("Now")).getByRole("link", { name: "3 waiting on the problem list" })).toHaveAttribute("href", "/grants/grant-sample#problem-list");
    expect(within(part("Coming up")).getByText("The timeline has played to its end.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next event" })).toBeDisabled();
  });

  it("starts over only after the confirm step, then plays the next event and delivers for the user", async () => {
    const { client, Wrapper } = harness();
    const startOver = vi.spyOn(client, "startOver");
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
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
    fireEvent.click(within(deliveries).getByRole("button", { name: "Deliver for me" }));
    await waitFor(() => expect(screen.queryByRole("list", { name: "For you to deliver" })).toBeNull());

    fireEvent.click(screen.getByRole("button", { name: "Next event" }));
    const next = await screen.findByRole("list", { name: "For you to deliver" });
    expect(within(next).getByText("invoice_1001.txt")).toBeInTheDocument();
    expect(within(part("Coming up")).getAllByRole("listitem")).toHaveLength(4);
  });

  it("goes to a date only forward, and links a played ledger line to its charge", async () => {
    const { client, Wrapper } = harness();
    await client.startOver(SAMPLE_GRANT_ID, true);
    render(<TimelinePanel grantId={SAMPLE_GRANT_ID} />, { wrapper: Wrapper });
    const input = (await screen.findByLabelText("Go to a date")) as HTMLInputElement;
    expect(input.min).toBe("2023-01-13");
    fireEvent.change(input, { target: { value: "2025-11-15" } });
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    await waitFor(() => expect(within(part("Just happened")).getByText("L-1001")).toBeInTheDocument());
    expect(within(part("Just happened")).getByRole("link", { name: "Open the charge from L-1001" })).toHaveAttribute("href", "/grants/grant-sample/charges/chg-l-1001");
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
