import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { FAKE_USER, StaticAuthProvider, type Auth } from "@/lib/auth";
import { WorkspaceScreen } from "./screen";

const params = { workspaceId: "ws-sample" };
vi.mock("next/navigation", () => ({
  useParams: () => params,
  usePathname: () => `/w/${params.workspaceId}`,
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

const auth: Auth = {
  state: { status: "signed_in", user: FAKE_USER },
  fake: true,
  signIn: async () => {},
  signOut: async () => {},
  getAccessToken: async () => null,
};

function renderScreen(client: ApiClient, workspaceId: string) {
  params.workspaceId = workspaceId;
  return render(
    <StaticAuthProvider value={auth}>
      <ApiProvider client={client}>
        <WorkspaceScreen />
      </ApiProvider>
    </StaticAuthProvider>,
  );
}

/** The page's own Add a grant links, leaving out the sidebar's. */
function addGrantLinks() {
  return within(screen.getByRole("main")).queryAllByRole("link", { name: "Add a grant" });
}

describe("the workspace home", () => {
  beforeEach(() => {
    params.workspaceId = "ws-sample";
  });

  it("names the workspace and offers Add a grant in its header once its grants have loaded", async () => {
    renderScreen(createFakeApiClient(), "ws-sample");
    const title = await screen.findByRole("heading", { level: 1, name: "Grants in Sample grant" });
    await screen.findByRole("table", { name: "Grants" });
    const links = addGrantLinks();
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/w/ws-sample/grants/new");
    expect(title.closest("header")).toContainElement(links[0]!);
  });

  it("calls the page what the sidebar calls it, in the breadcrumb", async () => {
    renderScreen(createFakeApiClient(), "ws-sample");
    await screen.findByRole("heading", { level: 1, name: "Grants in Sample grant" });
    const crumbs = screen.getByRole("list", { name: "Breadcrumbs" });
    expect(within(crumbs).getAllByRole("listitem").at(-1)).toHaveTextContent("All grants");
    expect(screen.getByRole("link", { name: "All grants" })).toBeInTheDocument();
  });

  it("fills one button, Add a grant, with grants and without", async () => {
    const client = createFakeApiClient();
    const { container, unmount } = renderScreen(client, "ws-sample");
    await screen.findByRole("table", { name: "Grants" });
    expect([...container.querySelectorAll("main .ft-btn--main")].map((b) => b.textContent)).toEqual(["Add a grant"]);
    unmount();
    const workspace = await client.createWorkspace("Biology department");
    const empty = renderScreen(client, workspace.id);
    await screen.findByRole("region", { name: "No grants in this workspace yet." });
    expect([...empty.container.querySelectorAll("main .ft-btn--main")].map((b) => b.textContent)).toEqual(["Add a grant"]);
  });

  it("says it is loading in the title's place, with no action yet", () => {
    renderScreen(createFakeApiClient(), "ws-sample");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Loading…");
    expect(addGrantLinks()).toHaveLength(0);
  });

  it("says a workspace that isn't the user's can't be shown, and offers nothing", async () => {
    renderScreen(createFakeApiClient(), "ws-someone-else");
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found, or not yours to see.");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Not found, or not yours to see.");
    expect(addGrantLinks()).toHaveLength(0);
  });

  it("shows an empty workspace what to do first, with Add a grant on the page and not in the header", async () => {
    const client = createFakeApiClient();
    const workspace = await client.createWorkspace("Biology department");
    renderScreen(client, workspace.id);
    const empty = await screen.findByRole("region", { name: "No grants in this workspace yet." });
    expect(
      within(empty).getByText(
        "Add your own grant from its award letter: the agent reads its terms, and you confirm them before any check uses them. Or add a sample grant to try FundTrail on.",
      ),
    ).toBeInTheDocument();
    const links = addGrantLinks();
    expect(links).toHaveLength(1);
    expect(empty).toContainElement(links[0]!);
    expect(links[0]).toHaveAttribute("href", `/w/${workspace.id}/grants/new`);
    expect(screen.getByRole("heading", { level: 1, name: "Grants in Biology department" })).toBeInTheDocument();
  });
});
