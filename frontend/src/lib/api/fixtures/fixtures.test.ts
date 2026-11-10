// @vitest-environment node
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { createFakeApiClient } from "../fake";
import { SAMPLE_DOCUMENTS } from "./documents";
import { SAMPLE_GRANT_ID, WORKSPACE_ID } from "./sample";
import raw from "./sample_grant.json";
import { countLedger, SAMPLE_LEDGER_CSV } from "./setup";

// Tests run from frontend/.
const golden = `${resolve(process.cwd(), "../backend/app/contracts/fixtures/golden")}/`;

describe("the copies of the contract's sample grant", () => {
  it.runIf(existsSync(golden))("match backend/app/contracts/fixtures/golden", () => {
    expect(raw).toEqual(JSON.parse(readFileSync(`${golden}sample_grant.json`, "utf8")));
    const names = readdirSync(`${golden}documents`).sort();
    expect(Object.keys(SAMPLE_DOCUMENTS).sort()).toEqual(names);
    for (const name of names) expect(SAMPLE_DOCUMENTS[name]).toBe(readFileSync(`${golden}documents/${name}`, "utf8"));
    expect(SAMPLE_LEDGER_CSV).toBe(readFileSync(`${golden}ledger.csv`, "utf8").trimEnd());
  });
});

describe("the fake client", () => {
  it("serves every area from the sample grant", async () => {
    const api = createFakeApiClient();
    expect((await api.listGrants(WORKSPACE_ID)).map((g) => g.grant.award_number)).toEqual(["SYN-2300117"]);
    expect((await api.getCharge("chg-l-1002")).status?.bucket).toBe("possible_conflict");
    expect((await api.listEvidence(SAMPLE_GRANT_ID)).map((c) => c.file.name)).toEqual([
      "extension_notice.txt",
      "sequencing_statement.eml",
      "invoice_1001.txt",
      "award_letter.txt",
    ]);
    expect((await api.getFileLink("file-invoice-1001")).url).toMatch(/^data:text\/plain/);
    expect((await api.listHeldMail(WORKSPACE_ID)).map((m) => m.sender)).toEqual(["billing@labsupply.example"]);
    expect((await api.getClock(WORKSPACE_ID)).now).toBe("2026-04-09T18:00:00Z");
    expect((await api.getReport(SAMPLE_GRANT_ID)).type).toBe("application/pdf");
  });

  it("keeps what it writes, per client", async () => {
    const api = createFakeApiClient();
    const posted = await api.postChargeMessage("chg-l-1002", "Any update?");
    expect((await api.getChargeThread("chg-l-1002")).entries.at(-1)).toEqual({ kind: "message", message: posted });
    expect((await createFakeApiClient().getChargeThread("chg-l-1002")).entries).toHaveLength(3);

    const record = await api.writeRecord(SAMPLE_GRANT_ID, { data: { kind: "confirmation", record_ids: ["rec-period-extension"] } });
    expect((await api.listRecords(SAMPLE_GRANT_ID)).map((r) => r.record.id)).toContain(record.id);
  });

  it("moves the clock only forward and answers unknown IDs with a 404", async () => {
    const api = createFakeApiClient();
    await expect(api.moveClock(WORKSPACE_ID, { to: "2026-01-01T00:00:00Z" })).rejects.toMatchObject({ status: 422 });
    expect((await api.moveClock(WORKSPACE_ID, { to: "2026-04-10T17:00:00Z" })).now).toBe("2026-04-10T17:00:00Z");
    await expect(api.getCharge("nope")).rejects.toMatchObject({ status: 404 });
  });

  it("counts a ledger upload by line ID", () => {
    expect(countLedger(SAMPLE_LEDGER_CSV)).toEqual({ added: 0, already_present: 2, rejected: [] });
    expect(countLedger(`${SAMPLE_LEDGER_CSV}\nL-1003,2026-03-01,2026-03-02,10.00,Tips,55016 Lab,,,\n,2026-03-01,2026-03-02,1.00,x,y,,,`)).toEqual({
      added: 1,
      already_present: 2,
      rejected: [{ row: 4, message: "The row has no line_id." }],
    });
  });
});
