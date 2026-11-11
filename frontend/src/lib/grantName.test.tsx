import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GrantList } from "@/components/GrantList";
import { ApiProvider, type GrantSummary, type SampleOption } from "./api";
import { createFakeApiClient } from "./api/fake";
import { FAKE_USER, StaticAuthProvider } from "./auth";
import { grantDisplayName, UNTITLED_GRANT } from "./grantName";

const samples: SampleOption[] = [
  { choice: "small_live", name: "Nitrate sensors", description: "d", needs_confirm: false, available: true },
  { choice: "larger_live", name: "Coastal survey", description: "d", needs_confirm: true, available: true },
];

function summary(grant: Partial<GrantSummary["grant"]>): GrantSummary {
  return {
    grant: { id: "g", workspace_id: "ws", ...grant },
    charges_ready: 0,
    charges_total: 0,
    on_problem_list: 0,
    waiting: 0,
    bucket_counts: { evidence_complete: 0, possible_conflict: 0, missing_evidence: 0, needs_human: 0 },
    now: "2026-04-09T18:00:00Z",
  };
}

describe("grantDisplayName", () => {
  it("names a sample grant by its sample until it has a title or award number", () => {
    const sample = { sample: "nitrate-sensors", choice: "small_live" as const };
    expect(grantDisplayName(summary({ sample }), samples)).toBe("Nitrate sensors");
    expect(grantDisplayName(summary({ sample, title: "Nitrate Sensor Network" }), samples)).toBe("Nitrate Sensor Network");
    expect(grantDisplayName(summary({ sample, award_number: "SYN-2500001" }), samples)).toBe("SYN-2500001");
  });

  it("keeps Untitled grant for a real grant, and for a sample before the choices load", () => {
    expect(grantDisplayName(summary({}), samples)).toBe(UNTITLED_GRANT);
    expect(grantDisplayName(summary({ sample: { sample: "x", choice: "small_live" } }))).toBe(UNTITLED_GRANT);
    expect(grantDisplayName(summary({ sample: { sample: "x", choice: "larger_prerun" } }), samples)).toBe(UNTITLED_GRANT);
  });

  it("names a just-opened sample grant on the workspace home", async () => {
    const client = createFakeApiClient();
    const opened = await client.createSample("ws-sample", { choice: "small_live" });
    const [option] = await client.listSamples();
    render(
      <StaticAuthProvider value={{ state: { status: "signed_in", user: FAKE_USER }, fake: true, signIn: async () => {}, signOut: async () => {}, getAccessToken: async () => null }}>
        <ApiProvider client={client}>
          <GrantList grants={[opened]} />
        </ApiProvider>
      </StaticAuthProvider>,
    );
    await waitFor(() => expect(screen.getByRole("link", { name: option.name })).toBeInTheDocument());
  });
});
