// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, HttpApiClient, SampleRefusalError } from "../client";
import { createFakeApiClient } from "../fake";
import { FAKE_NOW, SAMPLE_GRANT_ID, WORKSPACE_ID } from "./sample";
import { sampleStartsAt } from "./samples";

afterEach(() => vi.unstubAllGlobals());

describe("sample grants in fake mode", () => {
  it("lists the Sample dropdown's choices in order", async () => {
    const options = await createFakeApiClient().listSamples();
    expect(options.map((o) => [o.choice, o.needs_confirm, o.available])).toEqual([
      ["small_live", false, true],
      ["larger_live", true, true],
      ["larger_prerun", false, false],
    ]);
  });

  it("refuses the larger live sample until it's confirmed, with a SampleRefusal", async () => {
    const api = createFakeApiClient();
    const refused = await api.createSample(WORKSPACE_ID, { choice: "larger_live" }).catch((e: unknown) => e);
    expect(refused).toBeInstanceOf(SampleRefusalError);
    expect((refused as SampleRefusalError).refusal.reason).toBe("needs_confirm");

    const opened = await api.createSample(WORKSPACE_ID, { choice: "larger_live", confirmed: true });
    expect(opened.grant.sample?.choice).toBe("larger_live");
    expect(opened.now).toBe(sampleStartsAt());
    expect((await api.getGrant(opened.grant.id)).summary.grant.id).toBe(opened.grant.id);
    // It opens at the start of its timeline: the first event played.
    const opening = await api.getTimeline(opened.grant.id);
    expect(opening.now.now).toBe("2023-01-12T15:00:00Z");
    expect(opening.now.stopped_on?.name).toBe("award_letter.txt");
    expect(opening.coming_up).toHaveLength(5);
  });

  it("marks the fake's grant as a sample, with its now", async () => {
    const [row] = await createFakeApiClient().listGrants(WORKSPACE_ID);
    expect(row.grant.sample?.choice).toBe("small_live");
    expect(row.now).toBe(FAKE_NOW);
  });

  it("shows the sample grant where the fake stands, and plays it again from the start", async () => {
    const api = createFakeApiClient();
    const atNow = await api.getTimeline(SAMPLE_GRANT_ID);
    expect(atNow.now.now).toBe(FAKE_NOW);
    expect(atNow.now.stopped_on?.name).toBe("extension_notice.txt");
    expect(atNow.just_happened?.[0].agent_records?.map((r) => r.id)).toEqual(["rec-period-extension"]);
    expect(atNow.coming_up).toEqual([]);
    expect(atNow.now.waiting_on_problem_list).toBe(3);

    // Starting over goes back to the start of the timeline: its first event, played.
    const fresh = await api.startOver(SAMPLE_GRANT_ID, true);
    expect(fresh.now.now).toBe(sampleStartsAt());
    expect(fresh.now.stopped_on?.name).toBe("award_letter.txt");
    expect(fresh.coming_up?.map((e) => e.name)).toEqual(["invoice_1001.txt", "L-1001", "sequencing_statement.eml", "L-1002", "extension_notice.txt"]);

    // The award letter is the user's to deliver: once its date comes, it waits in Now.
    expect(fresh.now.deliveries?.map((d) => d.event.name)).toEqual(["award_letter.txt"]);
    expect((await api.deliveryFileUrl(SAMPLE_GRANT_ID, "event-file-award-letter")).url).toMatch(/^data:text\/plain/);
    const delivered = await api.deliverForMe(SAMPLE_GRANT_ID, "event-file-award-letter");
    expect(delivered.now.deliveries).toEqual([]);

    // Going to a date plays every event up to it; the ledger line says what the agent did.
    const later = await api.moveTimeline(SAMPLE_GRANT_ID, { to: "2025-11-14T12:00:00Z" });
    expect(later.just_happened?.map((p) => p.event.name)).toEqual(["L-1001"]);
    expect(later.just_happened?.[0].charge_ids).toEqual(["chg-l-1001"]);
    expect(later.now.deliveries?.map((d) => d.event.name)).toEqual(["invoice_1001.txt"]);

    await expect(api.moveTimeline(SAMPLE_GRANT_ID, { to: "2024-01-01T00:00:00Z" })).rejects.toMatchObject({ status: 409 });
  });

  it("answers a 404 for the timeline of a grant that isn't a sample", async () => {
    const api = createFakeApiClient();
    const grant = await api.createGrant(WORKSPACE_ID, new Blob(["letter"]), "award_letter.pdf");
    await expect(api.getTimeline(grant.id)).rejects.toMatchObject({ status: 404 });
  });
});

describe("HttpApiClient for sample grants", () => {
  it("turns a 409 SampleRefusal into a SampleRefusalError", async () => {
    const refusal = { reason: "needs_confirm", message: "Confirm to open this sample.", grant: null };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: refusal }), { status: 409 })));
    const api = new HttpApiClient("https://api.example", async () => "t");
    const error = await api.createSample("ws", { choice: "larger_live", confirmed: true }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(SampleRefusalError);
    expect((error as SampleRefusalError).refusal).toEqual(refusal);
  });

  it("turns a refused clock move into a SampleRefusalError", async () => {
    const refusal = { reason: "another_sample_working", message: "Another sample is still working.", grant: null };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: refusal }), { status: 409 })));
    const api = new HttpApiClient("https://api.example", async () => "t");
    const error = await api.moveTimeline("g", {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(SampleRefusalError);
    expect((error as SampleRefusalError).refusal.reason).toBe("another_sample_working");
  });

  it("leaves a 409 that isn't a refusal a plain ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "The timeline only moves forward." }), { status: 409 })));
    const api = new HttpApiClient("https://api.example", async () => "t");
    const error = await api.moveTimeline("g", { to: "2020-01-01T00:00:00Z" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).not.toBeInstanceOf(SampleRefusalError);
    expect((error as ApiError).status).toBe(409);
    const refusing = await api.createSample("ws", { choice: "small_live" }).catch((e: unknown) => e);
    expect(refusing).not.toBeInstanceOf(SampleRefusalError);
  });

  it("sends the sample routes", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const api = new HttpApiClient("https://api.example", async () => "t");
    await api.listSamples();
    await api.createSample("ws 1", { choice: "larger_live", confirmed: true });
    await api.getTimeline("g");
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(([url, init]) => [init.method ?? "GET", url, init.body ?? null])).toEqual([
      ["GET", "https://api.example/samples", null],
      ["POST", "https://api.example/workspaces/ws%201/samples", '{"choice":"larger_live","confirmed":true}'],
      ["GET", "https://api.example/grants/g/timeline", null],
    ]);
  });

  it("sends the timeline routes", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const api = new HttpApiClient("https://api.example", async () => "t");
    await api.moveTimeline("g", { to: null });
    await api.startOver("g", true);
    await api.deliverForMe("g", "ev 1");
    await api.deliveryFileUrl("g", "ev 1");
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls.map(([url, init]) => [init.method ?? "GET", url, init.body ?? null])).toEqual([
      ["POST", "https://api.example/grants/g/timeline", '{"to":null}'],
      ["POST", "https://api.example/grants/g/timeline/start-over", '{"confirmed":true}'],
      ["POST", "https://api.example/grants/g/timeline/deliveries/ev%201", null],
      ["GET", "https://api.example/grants/g/timeline/deliveries/ev%201/file", null],
    ]);
  });
});
