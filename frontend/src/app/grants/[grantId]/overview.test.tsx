import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient, type ProblemRow } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { GrantScreen } from "./screen";

vi.mock("next/navigation", () => ({
  useParams: () => ({ grantId: "grant-sample" }),
  usePathname: () => "/grants/grant-sample",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

function renderOverview(client: ApiClient) {
  const auth = { state: { status: "signed_in" as const, user: FAKE_USER }, fake: true, signIn: async () => {}, signOut: async () => {}, getAccessToken: async () => null };
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StaticAuthProvider value={auth}>
        <ApiProvider client={client}>{children}</ApiProvider>
      </StaticAuthProvider>
    );
  }
  return render(<GrantScreen />, { wrapper: Wrapper });
}

const overLimit: ProblemRow = {
  kind: "grant",
  problem: { check: "budget", problem: "over_limit", text: "Spending is over the award's limit.", record_ids: [], flagged: true },
};
const noBudget: ProblemRow = {
  kind: "grant",
  problem: { check: "budget", problem: "no_budget", text: "The grant has no confirmed budget.", record_ids: [], flagged: true },
};

describe("the grant overview", () => {
  it("shows the first three rows the server sent, and counts every row it sent in one place", async () => {
    const client = createFakeApiClient();
    const { rows } = await client.getProblemList(SAMPLE_GRANT_ID);
    vi.spyOn(client, "getProblemList").mockResolvedValue({ rows: [overLimit, ...rows, noBudget] });
    renderOverview(client);

    const need = (await screen.findByRole("heading", { name: "5 things need you" })).closest("section")!;
    const links = within(need).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/grants/grant-sample/problems",
      "/grants/grant-sample/problems?item=grant%3Abudget%3Aover_limit",
      "/grants/grant-sample/problems?item=terms%3Afile-extension-notice",
      "/grants/grant-sample/problems?item=held_mail%3Aheld-inv-1001-copy",
      "/grants/grant-sample/problems",
    ]);
    expect(within(need).getByText("2 more on the problem list")).toBeInTheDocument();
    expect(within(need).getByRole("link", { name: "See all 5" })).toBeInTheDocument();
    // A grant's own problem is a row like any other: it shows once, where the server put it.
    expect(screen.getAllByText("Spending is over the award's limit.")).toHaveLength(1);
    expect(screen.queryByText("The grant has no confirmed budget.")).toBeNull();
    // Readiness is ready of total; the buckets are their own list, as the server counted them.
    const buckets = screen.getByRole("list", { name: "Charges by bucket" });
    expect(within(buckets).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["1 Evidence complete", "1 Possible conflict"]);
  });

  it("shows the summary's count only while the problem list is loading", async () => {
    const client = createFakeApiClient();
    const detail = await client.getGrant(SAMPLE_GRANT_ID);
    vi.spyOn(client, "getGrant").mockResolvedValue({ ...detail, summary: { ...detail.summary, on_problem_list: 4 } });
    vi.spyOn(client, "getProblemList").mockReturnValue(new Promise(() => {}));
    renderOverview(client);
    const need = (await screen.findByRole("heading", { name: "4 things need you" })).closest("section")!;
    expect(within(need).queryByText(/more on the problem list/)).toBeNull();
  });

  it("gives the period once, in the head, and the grant's today under the next closeout date, in the server's dates", async () => {
    renderOverview(createFakeApiClient());
    expect(await screen.findByText("Feb 1, 2023 to Jan 31, 2026")).toBeInTheDocument();
    expect(screen.getAllByText(/Feb 1, 2023 to Jan 31, 2026/)).toHaveLength(1);
    expect(screen.getByText("May 1, 2026")).toBeInTheDocument();
    expect(screen.getByText("Today Apr 9, 2026")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "The grant's period" })).toBeNull();
  });

  it("says so when nothing is on the problem list, and leaves the end date unconfirmed in the existing words", async () => {
    const client = createFakeApiClient();
    const detail = await client.getGrant(SAMPLE_GRANT_ID);
    vi.spyOn(client, "getGrant").mockResolvedValue({ ...detail, summary: { ...detail.summary, on_problem_list: 0, end_date: null, next_closeout: null } });
    vi.spyOn(client, "getProblemList").mockResolvedValue({ rows: [] });
    renderOverview(client);
    expect(await screen.findByRole("heading", { name: "Nothing on the problem list." })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open the problem list" })).toBeNull();
    expect(screen.getAllByText("End date not confirmed yet")).toHaveLength(1);
    expect(screen.getByText("Today Apr 9, 2026")).toBeInTheDocument();
  });

  it("shows the agent's progress under the head while it reads, with one filled main button on the page", async () => {
    const client = createFakeApiClient();
    const detail = await client.getGrant(SAMPLE_GRANT_ID);
    vi.spyOn(client, "getGrant").mockResolvedValue({
      ...detail,
      summary: { ...detail.summary, reading: { files_read: 3, files_total: 8, lines_read: 12, lines_total: 40 }, last_run_summary: "Read invoice_1001.txt." },
    });
    renderOverview(client);
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("The agent is reading: 3 of 8 files, 12 of 40 ledger lines.");
    expect(status.closest("header")).not.toBeNull();
    await screen.findByRole("link", { name: "Open the problem list" });
    expect(document.querySelectorAll(".ft-btn--main")).toHaveLength(1);
  });
});
