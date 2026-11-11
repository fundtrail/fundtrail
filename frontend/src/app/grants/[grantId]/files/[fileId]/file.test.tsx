import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { FileScreen } from "./screen";

const nav = vi.hoisted(() => ({ fileId: "file-extension-notice", search: "" }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ grantId: "grant-sample", fileId: nav.fileId }),
  usePathname: () => `/grants/grant-sample/files/${nav.fileId}`,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

function renderPage(fileId: string, search = "") {
  nav.fileId = fileId;
  nav.search = search;
  const auth = { state: { status: "signed_in" as const, user: FAKE_USER }, fake: true, signIn: async () => {}, signOut: async () => {}, getAccessToken: async () => null };
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StaticAuthProvider value={auth}>
        <ApiProvider client={createFakeApiClient()}>{children}</ApiProvider>
      </StaticAuthProvider>
    );
  }
  return render(<FileScreen />, { wrapper: Wrapper });
}

describe("the viewer page", () => {
  it("has one h1, the file's name, and the viewer's head doesn't repeat it as another", async () => {
    renderPage("file-extension-notice", "record=rec-period-extension&value=end");
    expect(await screen.findByRole("heading", { level: 1, name: "extension_notice.txt" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.queryByRole("heading", { level: 2, name: "extension_notice.txt" })).toBeNull();
  });

  it("lists every fact in the file under In this file, the open one marked, each a link to its spot", async () => {
    const cards = await createFakeApiClient().listEvidence("grant-sample");
    const card = cards.find((c) => c.file.id === "file-syn-field-station-invoice")!;
    const paths = (card.facts ?? []).flatMap((f) => (f.values ?? []).map((v) => ({ record: f.record.id, path: v.path })));
    renderPage("file-syn-field-station-invoice", "record=rec-syn-bill-fs-2207&value=total");
    const list = await screen.findByRole("navigation", { name: "In this file" });
    const links = within(list).getAllByRole("link");
    // Every value, in the card's order, each opening its own spot.
    expect(links.map((a) => a.getAttribute("href"))).toEqual(
      paths.map(({ record, path }) => `/grants/grant-sample/files/file-syn-field-station-invoice?record=${record}&value=${encodeURIComponent(path)}`),
    );
    // The open one is marked, and only it.
    await waitFor(() => expect(links.filter((a) => a.getAttribute("aria-current") === "true")).toHaveLength(1));
    expect(links.find((a) => a.getAttribute("aria-current") === "true")).toHaveTextContent("Total");
    // An unconfirmed value keeps the card's words.
    expect(within(list).getByText("Unconfirmed")).toBeInTheDocument();
  });

  it("keeps focus on the value just followed, now the current one: the panel isn't rebuilt", async () => {
    const view = renderPage("file-syn-field-station-invoice", "record=rec-syn-bill-fs-2207&value=total");
    const list = await screen.findByRole("navigation", { name: "In this file" });
    const vendor = within(list).getByRole("link", { name: /^Vendor/ });
    vendor.focus();
    // Following the link changes the address; the screen renders again for the new value.
    nav.search = "record=rec-syn-bill-fs-2207&value=vendor";
    view.rerender(<FileScreen />);
    await waitFor(() => expect(vendor).toHaveAttribute("aria-current", "true"));
    // The same element, still in the page and still focused.
    expect(vendor.isConnected).toBe(true);
    expect(document.activeElement).toBe(vendor);
    expect(within(screen.getByRole("navigation", { name: "In this file" })).getByRole("link", { name: /^Total/ })).not.toHaveAttribute("aria-current");
    expect(within(screen.getByTestId("viewer-bar")).getByText("Vendor")).toBeInTheDocument();
  });

  it("lists the file's facts with nothing marked when no value is open", async () => {
    renderPage("file-syn-field-station-invoice");
    const list = await screen.findByRole("navigation", { name: "In this file" });
    expect(within(list).getAllByRole("link").filter((a) => a.getAttribute("aria-current") === "true")).toHaveLength(0);
  });
});
