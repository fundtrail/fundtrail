import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient, type FtRecord, type GrantProblemRow } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { ProblemsScreen } from "./screen";

const nav = vi.hoisted(() => ({ search: "", replace: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ grantId: "grant-sample" }),
  usePathname: () => "/grants/grant-sample/problems",
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const TEXT = "Spending is over the award's limit by $3,420.00.";
const ITEM = "item=grant%3Abudget%3Aover_limit";

function overLimit(accepted = false): GrantProblemRow {
  return {
    kind: "grant",
    problem: {
      check: "budget",
      problem: "over_limit",
      text: TEXT,
      record_ids: ["rec-notice-000"],
      flagged: true,
      accepted,
      accepted_by: accepted ? "rec-accept-grant" : null,
      amount_cents: 342_000,
    },
  };
}

/** The fake, with a grant problem first on the list, as the server sends it. */
async function clientWith(row: GrantProblemRow): Promise<ApiClient> {
  const client = createFakeApiClient();
  const { rows } = await client.getProblemList("grant-sample");
  vi.spyOn(client, "getProblemList").mockResolvedValue({ rows: [row, ...rows] });
  return client;
}

function renderPage(search: string, client: ApiClient) {
  nav.search = search;
  const auth = { state: { status: "signed_in" as const, user: FAKE_USER }, fake: true, signIn: async () => {}, signOut: async () => {}, getAccessToken: async () => null };
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StaticAuthProvider value={auth}>
        <ApiProvider client={client}>{children}</ApiProvider>
      </StaticAuthProvider>
    );
  }
  return render(<ProblemsScreen />, { wrapper: Wrapper });
}

const pane = () => screen.getByRole("region", { name: "The selected item" });

afterEach(() => {
  vi.unstubAllGlobals();
  nav.replace.mockClear();
  nav.push.mockClear();
});

describe("a problem on the grant itself (issue 301)", () => {
  it("shows the server's text with Accept with a note, and accepts it as a one-off about the grant", async () => {
    const client = await clientWith(overLimit());
    const write = vi.spyOn(client, "writeRecord");
    renderPage(ITEM, client);
    await waitFor(() => expect(within(pane()).getByText(TEXT)).toBeInTheDocument());
    expect(within(pane()).getByText("Grant")).toBeInTheDocument();
    expect(await within(pane()).findByRole("heading", { level: 2, name: "Sediment Microbiome Survey of Example Bay" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);

    fireEvent.click(within(pane()).getByRole("button", { name: "Accept with a note" }));
    expect(within(pane()).queryByText("Use the note")).toBeNull();
    fireEvent.change(within(pane()).getByLabelText("Note"), { target: { value: "Covered by the supplement in Amendment 2." } });
    fireEvent.click(within(pane()).getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    expect(write.mock.calls[0][0]).toBe("grant-sample");
    // Exactly an accepted_reason with no charge_id, record_id or file_id: an acceptance about the grant.
    expect(write.mock.calls[0][1]).toStrictEqual({
      data: {
        kind: "accepted_reason",
        reason: { check: "budget", problem: "over_limit" },
        note: "Covered by the supplement in Amendment 2.",
        reusable: false,
        rests_on: ["rec-notice-000"],
      },
    });
  });

  it("shows an accepted grant problem with its note and Reopen", async () => {
    const client = await clientWith(overLimit(true));
    const views = await client.listRecords("grant-sample");
    const accepted = {
      ...views[0].record,
      id: "rec-accept-grant",
      author: "user",
      data: { kind: "accepted_reason", reason: { check: "budget", problem: "over_limit" }, note: "Covered by the supplement in Amendment 2.", reusable: false, rests_on: [] },
    } as unknown as FtRecord;
    vi.spyOn(client, "listRecords").mockResolvedValue([...views, { record: accepted, state: "counts" }]);
    const write = vi.spyOn(client, "writeRecord").mockResolvedValue(accepted);
    renderPage(ITEM, client);
    await waitFor(() => expect(within(pane()).getByText("Accepted")).toBeInTheDocument());
    expect(await within(pane()).findByText("Your note: Covered by the supplement in Amendment 2.")).toBeInTheDocument();
    expect(within(pane()).queryByRole("button", { name: "Accept with a note" })).toBeNull();
    fireEvent.click(within(pane()).getByRole("button", { name: "Reopen" }));
    await waitFor(() => expect(write).toHaveBeenCalledWith("grant-sample", { data: { kind: "retraction", reason: null }, replaces_id: "rec-accept-grant" }));
  });

  it("opens above the list on a narrow screen, since a grant has no page of its own", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: true, media: query, addEventListener: () => {}, removeEventListener: () => {} }));
    const client = await clientWith(overLimit());
    renderPage(ITEM, client);
    await waitFor(() => expect(within(pane()).getByText(TEXT)).toBeInTheDocument());
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("picks a grant row on a narrow screen into the page, where other rows open their own page", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: true, media: query, addEventListener: () => {}, removeEventListener: () => {} }));
    const client = await clientWith(overLimit());
    renderPage("", client);
    const list = await screen.findByRole("list", { name: "Problem list" });
    fireEvent.click(within(list).getByText(TEXT));
    expect(nav.push).toHaveBeenCalledWith("/grants/grant-sample/problems?item=grant%3Abudget%3Aover_limit", { scroll: false });
  });
});
