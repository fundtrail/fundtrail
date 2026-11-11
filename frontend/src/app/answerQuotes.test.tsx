import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { findCitation } from "@/components/evidence/findCitation";
import { ApiProvider } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { FAKE_USER, StaticAuthProvider, type Auth } from "@/lib/auth";
import { ChargeScreen } from "./grants/[grantId]/charges/[chargeId]/screen";

vi.mock("next/navigation", () => ({
  useParams: () => ({ grantId: "grant-sample", chargeId: "chg-l-1001" }),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/grants/grant-sample/charges/chg-l-1001",
  useSearchParams: () => new URLSearchParams(),
}));

const auth: Auth = {
  state: { status: "signed_in", user: FAKE_USER },
  fake: true,
  signIn: async () => {},
  signOut: async () => {},
  getAccessToken: async () => null,
};

describe("an answer's quote (#275)", () => {
  it("links to the viewer at that quote of that answer", async () => {
    const client = createFakeApiClient();
    function Wrapper({ children }: { children: ReactNode }) {
      return (
        <StaticAuthProvider value={auth}>
          <ApiProvider client={client}>{children}</ApiProvider>
        </StaticAuthProvider>
      );
    }
    render(<ChargeScreen />, { wrapper: Wrapper });
    await waitFor(() => {
      const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
      expect(hrefs).toContain("/grants/grant-sample/files/file-invoice-1001?record=rec-allowable-l-1001&value=quotes%5B0%5D");
    });
    // From a charge, back goes to the problem list, not the grant's overview.
    expect(screen.getByRole("link", { name: "Back to the problem list" })).toHaveAttribute("href", "/grants/grant-sample/problems");
  });

  it("is found by the viewer among the grant's records, since answers aren't on the evidence cards", async () => {
    const client = createFakeApiClient();
    const [cards, records] = await Promise.all([client.listEvidence(SAMPLE_GRANT_ID), client.listRecords(SAMPLE_GRANT_ID)]);
    // Without the records the viewer can't place it, which is what #275 saw.
    expect(findCitation(cards, "rec-allowable-l-1001", "quotes[0]")).toBeNull();
    const spot = findCitation(cards, "rec-allowable-l-1001", "quotes[0]", records.map((r) => r.record));
    expect(spot?.citation.file_id).toBe("file-invoice-1001");
    expect(spot?.label).toBe("Quote 1 in the answer");
  });
});
