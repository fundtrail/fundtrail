// @vitest-environment node
import { describe, expect, it } from "vitest";
import type { Grant, TimelineView } from "../types";
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
const decided = (view: TimelineView) => (view.just_happened ?? []).flatMap((p) => (p.scripted_decisions ?? []).map((d) => d.id));
const deliveredForUser = (view: TimelineView) => names((view.just_happened ?? []).filter((p) => p.delivered_by_sample_accountant));

describe("Next highlight in the fake (ruling 77)", () => {
  it("moves to the next event carrying a highlight, with the sample accountant doing the steps before it", async () => {
    const api = createFakeApiClient();
    await api.startOver(SAMPLE_GRANT_ID, true);
    const view = await api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true });
    expect(view.now.now).toBe("2026-02-21T17:30:00Z");
    expect(view.now.stopped_on?.highlight).toBe("A bill by email");
    // Both uploads delivered for the user, and the award terms confirmed, on the way.
    expect(view.now.deliveries).toEqual([]);
    expect(deliveredForUser(view)).toEqual(["award_letter.txt", "invoice_1001.txt"]);
    expect(decided(view)).toEqual(["rec-confirm-award-terms"]);
  });

  it("holds the highlight's own steps for the user: the next Next highlight press doesn't make them, a later skip does", async () => {
    // Delivering the invoice marked as the emailed bill highlight's own step.
    const api = timeline({ "event-file-invoice-1001": "A bill by email" });
    await api.startOver(SAMPLE_GRANT_ID, true);
    const atHighlight = await api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true });
    expect(names(atHighlight.now.deliveries)).toEqual(["invoice_1001.txt"]);
    expect(deliveredForUser(atHighlight)).toEqual(["award_letter.txt"]);

    // Next highlight waits for it, saying why (ruling 86); a plain Next event leaves it.
    const reason = "Bring in invoice_1001.txt first: that's this highlight's step.";
    expect(atHighlight.next_highlight_unavailable_reason).toBe(reason);
    await expect(api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true })).rejects.toMatchObject({ status: 409, detail: reason });
    const plain = await api.moveTimeline(SAMPLE_GRANT_ID, {});
    expect(names(plain.now.deliveries)).toEqual(["invoice_1001.txt"]);

    // A later skipping move that isn't Next highlight makes it.
    const skipping = await api.moveTimeline(SAMPLE_GRANT_ID, { to: "2026-04-11T00:00:00Z", skip_human_steps: true });
    expect(skipping.now.deliveries).toEqual([]);
    expect(deliveredForUser(skipping)).toEqual(["invoice_1001.txt"]);
  });

  it("stops at the later of the highlight's event and its own steps' due times, and holds them (the amendment)", async () => {
    // The extension notice arrives Apr 9; confirming it, its own step, is due Apr 10.
    const api = createFakeApiClient();
    await api.startOver(SAMPLE_GRANT_ID, true);
    await api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true }); // A bill by email
    await api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true }); // Work after the end date
    const atExtension = await api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true });
    expect(atExtension.now.now).toBe("2026-04-10T16:00:00Z");
    expect(decided(atExtension)).not.toContain("rec-confirm-extension");
    // Ruling 85: Now names the highlight reached, though the clock stopped later.
    const reached = atExtension.now.stopped_on;
    expect(reached?.highlight).toBeTruthy();
    expect(reached ? Date.parse(reached.at) : NaN).toBeLessThan(Date.parse(atExtension.now.now));

    await expect(api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true })).rejects.toMatchObject({
      status: 409,
      detail: "No highlight is left to play.",
    });
    const skipping = await api.moveTimeline(SAMPLE_GRANT_ID, { to: "2026-04-11T00:00:00Z", skip_human_steps: true });
    expect(decided(skipping)).toEqual(["rec-confirm-extension"]);
  });

  it("stops at an earlier highlight's own step that comes due first, and waits for the user there (ruling 86)", async () => {
    // Confirming the award terms marked as the award letter's own step.
    const api = timeline({ "rec-confirm-award-terms": "Terms tied to their passages" });
    await api.startOver(SAMPLE_GRANT_ID, true);
    const first = await api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true });
    expect(first.now.now).not.toBe("2026-02-21T17:30:00Z");
    expect(decided(first)).not.toContain("rec-confirm-award-terms");
    const reason = "Confirm the terms read from award_letter.txt first: that's this highlight's step.";
    expect(first.next_highlight_unavailable_reason).toBe(reason);
    await expect(api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true })).rejects.toMatchObject({ status: 409, detail: reason });
  });

  it("queues nothing on a plain move: a later skipping move doesn't make what it passed", async () => {
    const api = createFakeApiClient();
    await api.startOver(SAMPLE_GRANT_ID, true);
    // A plain move past both confirmations and both uploads.
    await api.moveTimeline(SAMPLE_GRANT_ID, { to: "2026-04-11T00:00:00Z" });
    const skipping = await api.moveTimeline(SAMPLE_GRANT_ID, { to: "2026-04-12T00:00:00Z", skip_human_steps: true });
    expect(decided(skipping)).toEqual([]);
    expect(deliveredForUser(skipping)).toEqual([]);
    // The uploads stay the user's to deliver.
    expect(names(skipping.now.deliveries)).toEqual(["award_letter.txt", "invoice_1001.txt"]);
  });

  it("gives the timeline guide's fields as the backend does", async () => {
    const api = timeline({ "event-file-invoice-1001": "A bill by email" });
    await api.startOver(SAMPLE_GRANT_ID, true);
    const view = await api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true });
    expect(view.highlight_total).toBeGreaterThan(0);
    expect(view.highlight_index).toBe(1);
    expect(view.highlight_event?.highlight).toBe("A bill by email");
    expect(view.your_step).toEqual({ action: "deliver_file", open: "delivery", id: "event-file-invoice-1001" });
  });

  it("words its 409s as the backend does", async () => {
    const api = createFakeApiClient();
    await expect(api.moveTimeline(SAMPLE_GRANT_ID, { next_highlight: true })).rejects.toMatchObject({
      status: 409,
      detail: "No highlight is left to play.",
    });
    await expect(api.moveTimeline(SAMPLE_GRANT_ID, {})).rejects.toMatchObject({ status: 409, detail: "Nothing is left to play." });
  });
});
