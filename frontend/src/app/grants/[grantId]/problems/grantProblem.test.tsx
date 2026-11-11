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

/**
 * A grant problem as the server lists it. A grant row is listed only while the
 * grant has an open problem, so its `accepted` (about the whole grant) is
 * always false; which problem is accepted is its own `accepted_by`.
 */
function overLimit(accepted = false): GrantProblemRow {
  return {
    kind: "grant",
    problem: {
      check: "budget",
      problem: "over_limit",
      text: TEXT,
      record_ids: ["rec-notice-000"],
      flagged: true,
      accepted: false,
      accepted_by: accepted ? "rec-accept-grant" : null,
      amount_cents: 342_000,
    },
  };
}

const NO_DATES = "The grant has no confirmed period of performance.";

function noDates(): GrantProblemRow {
  return {
    kind: "grant",
    problem: { check: "period_of_performance", problem: "missing", text: NO_DATES, record_ids: [], flagged: true, accepted: false, accepted_by: null },
  };
}

/** The fake, with grant problems first on the list, as the server sends them. */
async function clientWith(...grantRows: GrantProblemRow[]): Promise<ApiClient> {
  const client = createFakeApiClient();
  const { rows } = await client.getProblemList("grant-sample");
  vi.spyOn(client, "getProblemList").mockResolvedValue({ rows: [...grantRows, ...rows] });
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

  it("shows an accepted grant problem, as the server sends it (accepted_by set), with its note and Reopen", async () => {
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

  it("with two grant problems, one accepted: the accepted one shows its note and Reopen, the open one offers Accept for itself only", async () => {
    const client = await clientWith(overLimit(true), noDates());
    const views = await client.listRecords("grant-sample");
    const accepted = {
      ...views[0].record,
      id: "rec-accept-grant",
      author: "user",
      data: { kind: "accepted_reason", reason: { check: "budget", problem: "over_limit" }, note: "Covered by the supplement in Amendment 2.", reusable: false, rests_on: [] },
    } as unknown as FtRecord;
    vi.spyOn(client, "listRecords").mockResolvedValue([...views, { record: accepted, state: "counts" }]);
    const write = vi.spyOn(client, "writeRecord");
    const first = renderPage(ITEM, client);
    await waitFor(() => expect(within(pane()).getByText("Accepted")).toBeInTheDocument());
    expect(await within(pane()).findByText("Your note: Covered by the supplement in Amendment 2.")).toBeInTheDocument();
    expect(within(pane()).getByRole("button", { name: "Reopen" })).toBeInTheDocument();
    expect(within(pane()).queryByRole("button", { name: "Accept with a note" })).toBeNull();
    // The row says so too, from the problem's own accepted_by.
    const list = screen.getByRole("list", { name: "Problem list" });
    expect(within(within(list).getByText(TEXT).closest("li")!).getByText("Accepted")).toBeInTheDocument();
    expect(within(within(list).getByText(NO_DATES).closest("li")!).queryByText("Accepted")).toBeNull();
    first.unmount();

    renderPage("item=grant%3Aperiod_of_performance%3Amissing", client);
    await waitFor(() => expect(within(pane()).getByText(NO_DATES)).toBeInTheDocument());
    expect(within(pane()).queryByText("Accepted")).toBeNull();
    expect(within(pane()).queryByRole("button", { name: "Reopen" })).toBeNull();
    fireEvent.click(within(pane()).getByRole("button", { name: "Accept with a note" }));
    fireEvent.change(within(pane()).getByLabelText("Note"), { target: { value: "Dates are in the award letter." } });
    fireEvent.click(within(pane()).getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    expect(write.mock.calls[0][1]).toStrictEqual({
      data: {
        kind: "accepted_reason",
        reason: { check: "period_of_performance", problem: "missing" },
        note: "Dates are in the award letter.",
        reusable: false,
        rests_on: [],
      },
    });
  });

  it("lands on the list's first row, calmly, when accepting the grant's only open problem takes its row off the list", async () => {
    const client = await clientWith(overLimit());
    const { rows } = await client.getProblemList("grant-sample");
    const views = await client.listRecords("grant-sample");
    const write = vi.spyOn(client, "writeRecord").mockImplementation(async () => {
      // The server lists grant rows only while the grant has an open problem.
      vi.spyOn(client, "getProblemList").mockResolvedValue({ rows: rows.filter((r) => r.kind !== "grant") });
      return views[0].record;
    });
    renderPage(ITEM, client);
    await waitFor(() => expect(within(pane()).getByText(TEXT)).toBeInTheDocument());
    fireEvent.click(within(pane()).getByRole("button", { name: "Accept with a note" }));
    fireEvent.change(within(pane()).getByLabelText("Note"), { target: { value: "Covered by the supplement in Amendment 2." } });
    fireEvent.click(within(pane()).getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    // The row is gone; the pane shows the list's first row, as for any row that leaves the list.
    await waitFor(() => expect(within(pane()).getByRole("heading", { level: 2, name: "extension_notice.txt" })).toBeInTheDocument());
    expect(screen.queryByText(TEXT)).toBeNull();
    expect(screen.queryByLabelText("Note")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("picks a grant row from the keyboard: its text is a real button", async () => {
    const client = await clientWith(overLimit());
    renderPage("", client);
    const list = await screen.findByRole("list", { name: "Problem list" });
    const row = within(list).getByRole("button", { name: TEXT });
    row.focus();
    expect(row).toHaveFocus();
    fireEvent.click(row);
    expect(nav.push).toHaveBeenCalledWith("/grants/grant-sample/problems?item=grant%3Abudget%3Aover_limit", { scroll: false });
  });

  it("opens above the list on a narrow screen, since a grant has no page of its own, and moves focus to its heading", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: true, media: query, addEventListener: () => {}, removeEventListener: () => {} }));
    const client = await clientWith(overLimit());
    renderPage(ITEM, client);
    await waitFor(() => expect(within(pane()).getByText(TEXT)).toBeInTheDocument());
    expect(nav.replace).not.toHaveBeenCalled();
    const heading = await within(pane()).findByRole("heading", { level: 2, name: "Sediment Microbiome Survey of Example Bay" });
    await waitFor(() => expect(heading).toHaveFocus());
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
