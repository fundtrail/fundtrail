import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient, type ProblemRow } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { sampleRecord } from "@/lib/api/fixtures/sample";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { ProblemsScreen } from "./screen";

const nav = vi.hoisted(() => ({ search: "", replace: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ grantId: "grant-sample" }),
  usePathname: () => "/grants/grant-sample/problems",
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

function renderPage(search = "", client: ApiClient = createFakeApiClient()) {
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

function narrowScreen(narrow: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: narrow, media: query, addEventListener: () => {}, removeEventListener: () => {} }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  nav.replace.mockClear();
  nav.push.mockClear();
});

describe("the problem list page", () => {
  it("shows the first row beside the list when nothing is picked, with one h1", async () => {
    renderPage();
    await waitFor(() => expect(within(pane()).getByRole("heading", { name: "extension_notice.txt" })).toBeInTheDocument());
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("has one h1 with a charge picked: the charge's title is an h2 in the pane", async () => {
    renderPage("item=charge%3Achg-l-1002");
    await waitFor(() => expect(within(pane()).getByRole("heading", { level: 2, name: "Sediment DNA sequencing run 7" })).toBeInTheDocument());
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("has one h1 with a record picked: the record's title is an h2 in the pane", async () => {
    const client = createFakeApiClient();
    const { rows } = await client.getProblemList("grant-sample");
    const recordRow: ProblemRow = {
      kind: "record",
      status: { grant_id: "grant-sample", record_id: "rec-period-extension", file_id: null, problems: [{ check: "terms", problem: "waiting", text: "A term waiting to be confirmed.", record_ids: [] }], flagged: true, accepted: false, snoozed: false },
      record: sampleRecord("rec-period-extension"),
      file: null,
    };
    vi.spyOn(client, "getProblemList").mockResolvedValue({ rows: [recordRow, ...rows] });
    renderPage("item=record%3Arec-period-extension", client);
    await waitFor(() => expect(within(pane()).getByRole("heading", { level: 2, name: "Period of performance" })).toBeInTheDocument());
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("falls back to the first row for an item that isn't on the list or on the grant", async () => {
    renderPage("item=charge%3Anope");
    await waitFor(() => expect(within(pane()).getByRole("heading", { name: "extension_notice.txt" })).toBeInTheDocument());
  });

  it("never leaves a picked row's item open when the filter hides it", async () => {
    renderPage("item=terms%3Afile-extension-notice");
    await waitFor(() => expect(within(pane()).getByRole("heading", { name: "extension_notice.txt" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Possible conflict 1" }));
    await waitFor(() => expect(within(pane()).getAllByText("Sediment DNA sequencing run 7").length).toBeGreaterThan(0));
    expect(within(pane()).queryByRole("heading", { name: "extension_notice.txt" })).toBeNull();
  });

  it("on a narrow screen loads no item beside the list, and a link to one item opens that item's own page", async () => {
    narrowScreen(true);
    renderPage("item=charge%3Achg-l-1002");
    await screen.findByRole("list", { name: "Problem list" });
    expect(screen.queryByRole("region", { name: "The selected item" })).toBeNull();
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/grants/grant-sample/charges/chg-l-1002"));
  });
});
