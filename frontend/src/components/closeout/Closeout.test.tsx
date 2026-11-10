import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, ApiProvider, type ApiClient } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { StaticAuthProvider, type Auth } from "@/lib/auth";
import { CloseoutCharges } from "./CloseoutCharges";
import { ReportDraft } from "./ReportDraft";

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
