import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { EvidenceScreen } from "./screen";

const nav = vi.hoisted(() => ({ search: "", replace: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ grantId: "grant-sample" }),
  usePathname: () => "/grants/grant-sample/files",
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
  return render(<EvidenceScreen />, { wrapper: Wrapper });
}

const pane = () => screen.getByRole("region", { name: "The selected file" });
const rowNames = () => within(screen.getByRole("list", { name: "Files" })).getAllByRole("link").map((a) => a.textContent);

function narrowScreen(narrow: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: narrow, media: query, addEventListener: () => {}, removeEventListener: () => {} }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  nav.replace.mockClear();
  nav.push.mockClear();
});

describe("the Evidence page", () => {
  it("lists every file in the server's order, with one h1 and the first file's card beside the list", async () => {
    const cards = await createFakeApiClient().listEvidence("grant-sample");
    renderPage();
    await waitFor(() => expect(within(pane()).getByRole("heading", { level: 2, name: cards[0].file.name })).toBeInTheDocument());
    expect(rowNames()).toEqual(cards.map((c) => c.file.name));
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Evidence" })).toBeInTheDocument();
    expect(screen.getByText(`${cards.length} files`)).toBeInTheDocument();
    // The list shows no quotes: those are the card's.
    expect(within(screen.getByRole("list", { name: "Files" })).queryByText(/Amendment Date:/)).toBeNull();
  });

  it("shows the file the search param picks, and the first file for one that isn't on the grant", async () => {
    const view = renderPage("file=file-syn-boat-receipt");
    await waitFor(() => expect(within(pane()).getByRole("heading", { level: 2, name: "boat_rental_receipt.jpg" })).toBeInTheDocument());
    const list = screen.getByRole("list", { name: "Files" });
    expect(within(list).getByRole("link", { name: "boat_rental_receipt.jpg" })).toHaveAttribute("aria-current", "true");
    expect(within(list).getByRole("link", { name: "extension_notice.txt" })).not.toHaveAttribute("aria-current");
    view.unmount();
    renderPage("file=file-nope");
    await waitFor(() => expect(within(pane()).getByRole("heading", { level: 2, name: "extension_notice.txt" })).toBeInTheDocument());
  });

  it("picks a file with a plain click, keeping the page", async () => {
    renderPage();
    const link = await screen.findByRole("link", { name: "invoice_1001.txt" });
    fireEvent.click(link);
    expect(nav.push).toHaveBeenCalledWith("/grants/grant-sample/files?file=file-invoice-1001", { scroll: false });
  });

  it("makes the address true when it names a file that isn't on the grant, with no new history entry", async () => {
    renderPage("file=file-nope");
    await waitFor(() => expect(within(pane()).getByRole("heading", { level: 2, name: "extension_notice.txt" })).toBeInTheDocument());
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/grants/grant-sample/files?file=file-extension-notice", { scroll: false }));
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("leaves a known file in the address alone", async () => {
    renderPage("file=file-syn-boat-receipt");
    await waitFor(() => expect(within(pane()).getByRole("heading", { level: 2, name: "boat_rental_receipt.jpg" })).toBeInTheDocument());
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("offers no filter: the server says nothing a filter could rest on", async () => {
    renderPage();
    await screen.findByRole("list", { name: "Files" });
    expect(screen.queryByRole("group", { name: /Show on/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Not linked/ })).toBeNull();
  });

  it("names the file list once for a screen reader", async () => {
    renderPage();
    await screen.findByRole("list", { name: "Files" });
    expect(screen.getAllByLabelText("Files")).toHaveLength(1);
  });

  it("on a narrow screen loads no card beside the list, rows open the file's page, and a link with a file opens it", async () => {
    narrowScreen(true);
    renderPage("file=file-syn-boat-receipt");
    await screen.findByRole("list", { name: "Files" });
    expect(screen.queryByRole("region", { name: "The selected file" })).toBeNull();
    expect(screen.getByRole("link", { name: "invoice_1001.txt" })).toHaveAttribute("href", "/grants/grant-sample/files/file-invoice-1001");
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/grants/grant-sample/files/file-syn-boat-receipt"));
    fireEvent.click(screen.getByRole("link", { name: "invoice_1001.txt" }));
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("says so, calmly, when the grant has no files", async () => {
    const client = createFakeApiClient();
    vi.spyOn(client, "listEvidence").mockResolvedValue([]);
    renderPage("", client);
    expect(await screen.findByText("No evidence on this grant yet.")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});

describe("deciding the agent's duplicate mark on the Evidence page (issue 353)", () => {
  it("after a saved decision whose refetch fails, shows the error and Try again, which reloads without writing", async () => {
    const client = createFakeApiClient();
    const writeRecord = vi.spyOn(client, "writeRecord");
    const listEvidence = vi.spyOn(client, "listEvidence");
    renderPage("file=file-syn-sequencing-statement-forwarded", client);
    const group = await within(await screen.findByRole("region", { name: "The selected file" })).findByRole("group", { name: "The agent's duplicate mark" });
    // The write goes through; the refetch after it fails.
    listEvidence.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    fireEvent.click(within(group).getByRole("button", { name: "Confirm" }));
    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull();
    // Try again only loads: the card comes back in the server's new state, and nothing is written again.
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() =>
      expect(within(screen.getByRole("region", { name: "The selected file" })).getByText("Copy of sequencing_statement.eml")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("group", { name: "The agent's duplicate mark" })).toBeNull();
    expect(writeRecord).toHaveBeenCalledTimes(1);
  });
});

describe("the build's lines in the evidence screens", () => {
  const read = (p: string) => readFileSync(resolve(process.cwd(), "src/app/grants/[grantId]/files", p), "utf8");

  it("keeps the pings on both screens and the four-argument findCitation on the viewer's", () => {
    expect(read("screen.tsx")).toContain("usePings(`grant:${grantId}`);");
    const viewer = read("[fileId]/screen.tsx");
    expect(viewer).toContain("usePings(`grant:${grantId}`);");
    expect(viewer).toContain("findCitation(cards, recordId, path, records.data?.map((r) => r.record))");
  });
});
