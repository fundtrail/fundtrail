// @vitest-environment node
import { describe, expect, it } from "vitest";
import type { Grant } from "../types";
import { createFakeApiClient } from "../fake";
import { newGrantDetail } from "./grant";
import { SAMPLE_GRANT_ID } from "./sample";
import { samplesFake } from "./samples";

/** The fake's sample timeline, with the given steps marked as highlights' own (ruling 77). */
function timeline(stepHighlights?: Record<string, string>) {
  return samplesFake({
    addGrant: () => {},
    summaryOf: (g: Grant) => newGrantDetail(g).summary,
    problemRows: 3,
    stepHighlights,
  });
}

const names = (items: { event: { name: string } }[] | undefined) => (items ?? []).map((i) => i.event.name);

describe("Next highlight in the fake (ruling 77)", () => {
  it("moves to the next event carrying a highlight, with the sample accountant doing the steps before it", async () => {
    const api = createFakeApiClient();
    await api.startOver(SAMPLE_GRANT_ID, true);
    const view = await api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true });
    expect(view.now.now).toBe("2026-02-21T17:30:00Z");
    expect(view.now.stopped_on?.highlight).toBe("A bill by email");
    // Both uploads delivered for the user, and the award terms confirmed, on the way.
    expect(view.now.deliveries).toEqual([]);
    expect((view.just_happened ?? []).filter((p) => p.delivered_by_sample_accountant).map((p) => p.event.name)).toEqual([
      "award_letter.txt",
      "invoice_1001.txt",
    ]);
    expect((view.just_happened ?? []).flatMap((p) => (p.scripted_decisions ?? []).map((d) => d.id))).toEqual(["rec-confirm-award-terms"]);
  });

  it("leaves the highlight's own steps for the user, and a later skipping move makes them", async () => {
    // Delivering the invoice marked as the emailed bill highlight's own step.
    const api = timeline({ "event-file-invoice-1001": "A bill by email" });
    await api.startOver(SAMPLE_GRANT_ID, true);
    const atHighlight = await api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true });
    expect(names(atHighlight.now.deliveries)).toEqual(["invoice_1001.txt"]);
    expect(names((atHighlight.just_happened ?? []).filter((p) => p.delivered_by_sample_accountant))).toEqual(["award_letter.txt"]);

    // A plain Next event leaves it waiting; a skipping one delivers it.
    const plain = await api.moveTimeline(SAMPLE_GRANT_ID, {});
    expect(names(plain.now.deliveries)).toEqual(["invoice_1001.txt"]);
    const skipping = await api.moveTimeline(SAMPLE_GRANT_ID, { skip_human_steps: true });
    expect(skipping.now.deliveries).toEqual([]);
    expect(names((skipping.just_happened ?? []).filter((p) => p.delivered_by_sample_accountant))).toEqual(["invoice_1001.txt"]);
  });

  it("leaves a highlight's own decision for the user until a later skipping move passes it", async () => {
    const api = createFakeApiClient();
    await api.startOver(SAMPLE_GRANT_ID, true);
    // Go past the extension's confirmation (Apr 10, 2026) without skipping, then to the end with skipping.
    await api.moveTimeline(SAMPLE_GRANT_ID, { to: "2026-04-11T00:00:00Z" });
    const skipping = await api.moveTimeline(SAMPLE_GRANT_ID, { to: "2026-04-12T00:00:00Z", skip_human_steps: true });
    const decided = (skipping.just_happened ?? []).flatMap((p) => (p.scripted_decisions ?? []).map((d) => d.id));
    expect(decided).toEqual(["rec-confirm-award-terms", "rec-confirm-extension"]);
  });

  it("answers a 409 when no highlight is coming up", async () => {
    const api = createFakeApiClient();
    await expect(api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true })).rejects.toMatchObject({ status: 409 });
  });
});
