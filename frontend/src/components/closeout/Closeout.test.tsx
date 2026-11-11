import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi, type Mock } from "vitest";
import { ApiError, ApiProvider, type ApiClient, type FtRecord, type SignOff, type SignOffState } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { StaticAuthProvider, type Auth } from "@/lib/auth";
import { CloseoutCharges } from "./CloseoutCharges";
import { ReportDraft } from "./ReportDraft";
import { SnoozedCharges } from "./SnoozedCharges";

const auth: Auth = {
  state: { status: "signed_in", user: { id: "user-1", email: "accountant@university.example", name: null } },
  fake: true,
  signIn: async () => {},
  signOut: async () => {},
  getAccessToken: async () => null,
};

function wrap(client: ApiClient, children: ReactNode) {
  return (
    <StaticAuthProvider value={auth}>
      <ApiProvider client={client}>{children}</ApiProvider>
    </StaticAuthProvider>
  );
}

describe("CloseoutCharges", () => {
  it("lists every expense with its bucket, and opens its evidence and history", async () => {
    const client = createFakeApiClient();
    const rows = await client.listCharges(SAMPLE_GRANT_ID);
    render(wrap(client, <CloseoutCharges grantId={SAMPLE_GRANT_ID} rows={rows} />));

    expect(screen.getAllByRole("row")).toHaveLength(rows.length + 1);
    expect(screen.queryByRole("row", { name: "Evidence and history for L-1002" })).not.toBeInTheDocument();
    expect(screen.getByText("L-1002")).toBeInTheDocument();
    expect(screen.getAllByText("Possible conflict").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Show evidence and history for L-1002" }));
    expect(await screen.findByText(/ledger line L-1002 arrived/)).toBeInTheDocument();
    expect(screen.getByText("Evidence")).toBeInTheDocument();
  });
});

describe("ReportDraft", () => {
  it("says plainly when the server hasn't built the report yet", async () => {
    const client = { getReport: vi.fn(async () => Promise.reject(new ApiError(501, "Not Implemented"))) } as unknown as ApiClient;
    render(wrap(client, <ReportDraft grantId="g-1" signOff={{ state: "not_signed", sign_off: null, changes: [] }} />));
    fireEvent.click(screen.getByRole("button", { name: "Make the draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The evidence report isn't built yet");
  });

  it("offers the draft PDF to open once it's made", async () => {
    const createObjectURL = vi.fn(() => "blob:draft");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    render(wrap(createFakeApiClient(), <ReportDraft grantId={SAMPLE_GRANT_ID} signOff={{ state: "not_signed" }} />));
    fireEvent.click(screen.getByRole("button", { name: "Make the draft" }));
    expect(await screen.findByRole("link", { name: "Open the draft (PDF)" })).toHaveAttribute("href", "blob:draft");
    vi.unstubAllGlobals();
  });
});

describe("ReportDraft, the signed report", () => {
  const signOffRecord = {
    id: "rec-sign-off-1",
    workspace_id: "ws",
    grant_id: "g-1",
    author: "user",
    author_user_id: "user-1",
    written_at: "2026-04-12T10:00:00Z",
    data: { kind: "sign_off", note: null, report_path: "ws/g-1/reports/r.pdf", report_sha256: "abc123" },
  } as unknown as FtRecord<SignOff>;
  const signed: SignOffState = { state: "signed", sign_off: signOffRecord, changes: [] };

  function client(overrides: Partial<ApiClient> = {}) {
    return {
      getReport: vi.fn(async () => new Blob(["draft"], { type: "application/pdf" })),
      getSignedReport: vi.fn(async () => new Blob(["signed"], { type: "application/pdf" })),
      ...overrides,
    } as unknown as ApiClient & { getReport: Mock; getSignedReport: Mock };
  }

  function stubUrls() {
    let n = 0;
    const createObjectURL = vi.fn(() => `blob:${++n}`);
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL }));
    return { createObjectURL, revokeObjectURL };
  }

  it("offers nothing new before a sign-off", () => {
    const api = client();
    render(wrap(api, <ReportDraft grantId="g-1" signOff={{ state: "not_signed", sign_off: null, changes: [] }} />));
    expect(screen.queryByRole("group", { name: "Signed report" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Get the signed report" })).not.toBeInTheDocument();
    expect(screen.queryByText(/signed report \(PDF\)/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Make the draft" })).toBeInTheDocument();
  });

  it("fetches the signed report through the sign-off record, then offers it to open and save, above the draft", async () => {
    stubUrls();
    const api = client();
    render(wrap(api, <ReportDraft grantId="g-1" signOff={signed} />));
    const get = screen.getByRole("button", { name: "Get the signed report" });
    // The signed report's action comes before the draft's.
    expect(get.compareDocumentPosition(screen.getByRole("button", { name: "Make the draft" }))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    fireEvent.click(get);

    const open = await screen.findByRole("link", { name: "Open the signed report (PDF)" });
    expect(api.getSignedReport).toHaveBeenCalledWith("rec-sign-off-1");
    expect(api.getSignedReport).not.toHaveBeenCalledWith("g-1");
    expect(api.getReport).not.toHaveBeenCalled();
    expect(open).toHaveAttribute("href", "blob:1");
    const group = screen.getByRole("group", { name: "Signed report" });
    const save = within(group).getByRole("link", { name: "Save it" });
    expect(save).toHaveAttribute("href", "blob:1");
    expect(save).toHaveAttribute("download", "evidence-report-signed-g-1.pdf");
    vi.unstubAllGlobals();
  });

  it("keeps the draft's buttons working as before, with a sign-off", async () => {
    stubUrls();
    const api = client();
    render(wrap(api, <ReportDraft grantId="g-1" signOff={signed} />));
    fireEvent.click(screen.getByRole("button", { name: "Make the draft" }));
    expect(await screen.findByRole("link", { name: "Open the draft (PDF)" })).toHaveAttribute("href", "blob:1");
    expect(api.getReport).toHaveBeenCalledWith("g-1");
    expect(api.getSignedReport).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Make the draft again" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Get the signed report" })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("shows the server's words when the signed report can't be served, apart from the draft", async () => {
    const detail = "The stored report doesn't match the checksum on its sign-off, so it isn't served.";
    const api = client({ getSignedReport: vi.fn(async () => Promise.reject(new ApiError(409, detail))) });
    render(wrap(api, <ReportDraft grantId="g-1" signOff={signed} />));
    fireEvent.click(screen.getByRole("button", { name: "Get the signed report" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    // The draft is untouched by the signed report's error.
    expect(screen.getByRole("button", { name: "Make the draft" })).toBeEnabled();
  });

  it("revokes the signed file's URL when it goes away", async () => {
    const { revokeObjectURL } = stubUrls();
    const api = client();
    const { unmount } = render(wrap(api, <ReportDraft grantId="g-1" signOff={signed} />));
    fireEvent.click(screen.getByRole("button", { name: "Get the signed report" }));
    await screen.findByRole("link", { name: "Open the signed report (PDF)" });
    unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:1");
    vi.unstubAllGlobals();
  });

  it("doesn't offer a file fetched for an earlier sign-off once a newer one arrives", async () => {
    stubUrls();
    const api = client();
    const { rerender } = render(wrap(api, <ReportDraft grantId="g-1" signOff={signed} />));
    fireEvent.click(screen.getByRole("button", { name: "Get the signed report" }));
    await screen.findByRole("link", { name: "Open the signed report (PDF)" });
    const newer = { ...signOffRecord, id: "rec-sign-off-2" } as FtRecord<SignOff>;
    rerender(wrap(api, <ReportDraft grantId="g-1" signOff={{ state: "signed", sign_off: newer, changes: [] }} />));
    expect(screen.queryByRole("link", { name: "Open the signed report (PDF)" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Get the signed report" }));
    await screen.findByRole("link", { name: "Open the signed report (PDF)" });
    expect(api.getSignedReport).toHaveBeenLastCalledWith("rec-sign-off-2");
    vi.unstubAllGlobals();
  });
});

describe("SnoozedCharges", () => {
  it("lists the charges whose status says they're snoozed, and nothing when none are", async () => {
    const rows = await createFakeApiClient().listCharges(SAMPLE_GRANT_ID);
    const { rerender } = render(<SnoozedCharges grantId={SAMPLE_GRANT_ID} rows={rows} />);
    expect(screen.queryByRole("group")).not.toBeInTheDocument();

    const snoozed = rows.map((r) =>
      r.charge.ledger_line_id === "L-1002" && r.status ? { ...r, status: { ...r.status, snoozed: true } } : r,
    );
    rerender(<SnoozedCharges grantId={SAMPLE_GRANT_ID} rows={snoozed} />);
    const group = screen.getByRole("group", { name: /Snoozed: off the problem list, not ready for closeout \(1\)/ });
    expect(group).toHaveTextContent("L-1002");
    expect(group).not.toHaveTextContent("L-1001");
  });
});
