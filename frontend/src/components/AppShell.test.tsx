import { render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient } from "@/lib/api";
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

/** Renders the shell at a path, with the fake client or one the test adjusted. */
function renderShell(path: string, client: ApiClient = createFakeApiClient(), as: Auth = auth, crumbs = ["Page"]) {
  pathname = path;
  render(
    <StaticAuthProvider value={as}>
      <ApiProvider client={client}>
        <AppShell workspaceId="ws-sample" crumbs={crumbs}>
          <p>Content</p>
        </AppShell>
      </ApiProvider>
    </StaticAuthProvider>,
  );
}

/** Renders the shell at a path and waits for the sample grant to reach the sidebar. */
async function renderAt(path: string) {
  renderShell(path);
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
  it("names the grant above its pages and marks Overview on the grant page", async () => {
    await renderAt("/grants/grant-sample");
    expect(links()).toEqual(["All grants", "Held mail", "Overview", "Problem list", "Charges", "Evidence", "Grant terms", "Ledger", "Closeout", "Add a grant"]);
    // The grant's name is a label for its pages, not a link.
    expect(within(nav()).getByText("SYN-2300117").closest("a")).toBeNull();
    expect(marked()).toEqual([["Overview", "page"]]);
    expect(within(nav()).getByRole("link", { name: "Overview" })).toHaveAttribute("href", "/grants/grant-sample");
    expect(within(nav()).getByRole("link", { name: "Charges" })).toHaveAttribute("href", "/grants/grant-sample/charges");
  });

  it("keeps the problem list count on Problem list", async () => {
    await renderAt("/grants/grant-sample");
    const problems = within(nav()).getByRole("link", { name: /Problem list/ });
    expect(problems).toHaveAttribute("href", "/grants/grant-sample/problems");
    expect(problems.querySelector(".ft-count")).toHaveTextContent("on the problem list");
  });

  it.each([
    ["/grants/grant-sample/charges/chg-l-1002", "Charges"],
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
    ["/grants/grant-sample", "Overview"],
    ["/grants/grant-sample/problems", "Problem list"],
    ["/grants/grant-sample/charges", "Charges"],
  ])("marks the page itself on %s", async (path, page) => {
    await renderAt(path);
    expect(marked()).toEqual([[page, "page"]]);
  });
});

describe("the sidebar on a grant page it can't name yet", () => {
  it("shows neither the grants list nor any grant's pages while the grant list loads", async () => {
    const client = createFakeApiClient();
    vi.spyOn(client, "listGrants").mockReturnValue(new Promise(() => {}));
    renderShell("/grants/grant-sample", client);
    await within(nav()).findByText("All grants");
    expect(links()).toEqual(["All grants", "Held mail", "Add a grant"]);
    expect(within(nav()).queryByText("Grants")).toBeNull();
    expect(marked()).toEqual([]);
  });

  it("shows neither when the grant isn't in the workspace's list", async () => {
    const client = createFakeApiClient();
    const list = vi.spyOn(client, "listGrants").mockResolvedValue([]);
    renderShell("/grants/grant-sample", client);
    await waitFor(() => expect(list).toHaveBeenCalled());
    await within(nav()).findByText("All grants");
    expect(links()).toEqual(["All grants", "Held mail", "Add a grant"]);
    expect(within(nav()).queryByText("Grants")).toBeNull();
  });

  it("names a grant with no award number by its display name", async () => {
    const client = createFakeApiClient();
    const real = client.listGrants.bind(client);
    vi.spyOn(client, "listGrants").mockImplementation(async (id) =>
      (await real(id)).map((g) => ({ ...g, grant: { ...g.grant, award_number: null } })),
    );
    renderShell("/grants/grant-sample", client);
    const label = await within(nav()).findByText("Sediment Microbiome Survey of Example Bay");
    expect(label.closest("a")).toBeNull();
    expect(label).toHaveAttribute("title", "Sediment Microbiome Survey of Example Bay");
    expect(within(nav()).queryByText("SYN-2300117")).toBeNull();
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

describe("the account block and the breadcrumbs", () => {
  it("shows the email once, under the name, with its full text as a title", async () => {
    await renderAt("/w/ws-sample");
    const email = within(nav()).getByText(FAKE_USER.email);
    expect(email).toHaveAttribute("title", FAKE_USER.email);
    expect(within(nav()).getByText("Demo accountant")).toBeInTheDocument();
  });

  it("shows the email once when the name is the email", async () => {
    const user = { ...FAKE_USER, name: FAKE_USER.email };
    renderShell("/w/ws-sample", createFakeApiClient(), { ...auth, state: { status: "signed_in", user } });
    await within(nav()).findByText("SYN-2300117");
    expect(within(nav()).getAllByText(FAKE_USER.email)).toHaveLength(1);
  });

  it("gives every crumb its full text as a title, so a cut-off crumb can be read", async () => {
    renderShell("/grants/grant-sample/charges/chg", createFakeApiClient(), auth, ["Low-Cost Nitrate Sensors", "L-1958-0004"]);
    const crumbs = screen.getByRole("list", { name: "Breadcrumbs" });
    expect(within(crumbs).getByText("Low-Cost Nitrate Sensors")).toHaveAttribute("title", "Low-Cost Nitrate Sensors");
    expect(within(crumbs).getByText("L-1958-0004")).toHaveAttribute("aria-current", "page");
  });
});
