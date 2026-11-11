import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { FAKE_USER, StaticAuthProvider, type Auth } from "@/lib/auth";
import { AppShell } from "./AppShell";

let pathname = "/";
vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ replace: vi.fn() }),
}));

const auth: Auth = {
  state: { status: "signed_in", user: FAKE_USER },
  fake: true,
  signIn: async () => {},
  signOut: async () => {},
  getAccessToken: async () => null,
};

/** Renders the shell at a path and waits for the sample grant to reach the sidebar. */
async function renderAt(path: string) {
  pathname = path;
  render(
    <StaticAuthProvider value={auth}>
      <ApiProvider client={createFakeApiClient()}>
        <AppShell workspaceId="ws-sample" crumbs={["Page"]}>
          <p>Content</p>
        </AppShell>
      </ApiProvider>
    </StaticAuthProvider>,
  );
  await within(nav()).findByText("SYN-2300117");
}

const nav = () => screen.getByRole("navigation", { name: "Main" });

/** Every sidebar link marked as where the accountant is: its words and its aria-current. */
function marked(): [string, string | null][] {
  return [...nav().querySelectorAll("a.is-active")].map((a) => [
    a.querySelector(".ft-nav__text")?.textContent ?? "",
    a.getAttribute("aria-current"),
  ]);
}

/** The words of every sidebar link, in order. */
function links(): string[] {
  return [...nav().querySelectorAll("a .ft-nav__text")].map((t) => t.textContent ?? "");
}

describe("the sidebar inside a grant", () => {
  it("names the grant above its pages and marks Problem list on the grant page", async () => {
    await renderAt("/grants/grant-sample");
    expect(links()).toEqual(["All grants", "Held mail", "Problem list", "Evidence", "Grant terms", "Ledger", "Closeout", "Add a grant"]);
    // The grant's name is a label for its pages, not a link.
    expect(within(nav()).getByText("SYN-2300117").closest("a")).toBeNull();
    expect(marked()).toEqual([["Problem list", "page"]]);
  });

  it("keeps the problem list count on Problem list", async () => {
    await renderAt("/grants/grant-sample");
    const problems = within(nav()).getByRole("link", { name: /Problem list/ });
    expect(problems).toHaveAttribute("href", "/grants/grant-sample#problem-list");
    expect(problems.querySelector(".ft-count")).toHaveTextContent("on the problem list");
  });

  it.each([
    ["/grants/grant-sample/charges/chg-l-1002", "Problem list"],
    ["/grants/grant-sample/records/rec-1", "Problem list"],
    ["/grants/grant-sample/files/file-award-letter", "Evidence"],
    ["/grants/grant-sample/files/file-award-letter/confirm", "Evidence"],
  ])("marks the page above %s as its parent", async (path, parent) => {
    await renderAt(path);
    expect(marked()).toEqual([[parent, "true"]]);
  });

  it.each([
    ["/grants/grant-sample/files", "Evidence"],
    ["/grants/grant-sample/terms", "Grant terms"],
    ["/grants/grant-sample/ledger", "Ledger"],
    ["/grants/grant-sample/closeout", "Closeout"],
  ])("marks the page itself on %s", async (path, page) => {
    await renderAt(path);
    expect(marked()).toEqual([[page, "page"]]);
  });
});

describe("the sidebar outside a grant", () => {
  it("lists the grants under a label, each linking to its grant with its count and full name", async () => {
    await renderAt("/w/ws-sample");
    expect(links()).toEqual(["All grants", "Held mail", "SYN-2300117", "Add a grant"]);
    const grant = within(nav()).getByRole("link", { name: /SYN-2300117/ });
    expect(grant).toHaveAttribute("href", "/grants/grant-sample");
    expect(grant).toHaveAttribute("title", "SYN-2300117");
    expect(grant.querySelector(".ft-count")).not.toBeNull();
  });

  it.each([
    ["/w/ws-sample", "All grants"],
    ["/w/ws-sample/grants/new", "Add a grant"],
    ["/w/ws-sample/mail", "Held mail"],
  ])("marks the page itself on %s", async (path, page) => {
    await renderAt(path);
    expect(marked()).toEqual([[page, "page"]]);
  });
});
