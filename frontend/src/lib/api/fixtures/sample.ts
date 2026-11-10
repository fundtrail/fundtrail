// The contract's sample grant (contracts.md section 15), shared by every area's
// fixtures. sample_grant.json is a copy of
// backend/app/contracts/fixtures/golden/sample_grant.json, and a test checks
// that it still matches.
//
// The fake shows the sample at FAKE_NOW, Apr 9, 2026 at 18:00 UTC: the
// extension notice has arrived from Drive and waits for the accountant, so the
// old end date stays in force and L-1002 is in Possible conflict. Only what had
// arrived or been written by then is visible.
//
// Everything here is synthetic. Status text in the area files stands in for
// text the server builds; screens show it as it comes.

import { ApiError } from "../client";
import type { Charge, Cents, EvidenceFile, FtRecord, Grant, Id, IsoDate, IsoDatetime, User, ValueState, Workspace } from "../types";
import raw from "./sample_grant.json";

export interface DefaultItemFixture {
  key: Id;
  needed: string;
  amount_cents?: Cents | null;
  expected_by?: IsoDate | null;
}

export interface SampleGrant {
  user: User;
  workspace: Workspace;
  grant: Grant;
  charges: Charge[];
  files: EvidenceFile[];
  records: FtRecord[];
  default_items: Record<string, DefaultItemFixture[]>;
}

export const sample = raw as unknown as SampleGrant;

export const FAKE_NOW: IsoDatetime = "2026-04-09T18:00:00Z";

const t = (iso: string) => new Date(iso).getTime();

/** What had arrived or been written by `now`. */
export function visibleAt(now: IsoDatetime) {
  return {
    charges: sample.charges.filter((c) => t(c.arrived_at) <= t(now)),
    files: sample.files.filter((f) => t(f.arrived_at) <= t(now)),
    records: sample.records.filter((r) => t(r.written_at) <= t(now)),
  };
}

export const atNow = visibleAt(FAKE_NOW);

export const WORKSPACE_ID = sample.workspace.id;
export const SAMPLE_GRANT_ID = sample.grant.id;

function find<T extends { id: Id }>(items: T[], id: Id, what: string): T {
  const item = items.find((i) => i.id === id);
  if (!item) throw new Error(`The sample grant has no ${what} ${id}`);
  return item;
}

/** One of the sample's records, files or charges by ID. Throws when the sample doesn't have it. */
export const sampleRecord = <R extends FtRecord = FtRecord>(id: Id) => find(sample.records, id, "record") as R;
export const sampleFile = (id: Id) => find(sample.files, id, "file");
export const sampleCharge = (id: Id) => find(sample.charges, id, "charge");

/** The workspace as the fake serves it, on the fake clock. */
export const sampleWorkspace: Workspace = { ...sample.workspace, clock_now: FAKE_NOW };

/** A deep copy, or a 404 when there's nothing, the way the server answers. */
export function served<T>(value: T | undefined): Promise<T> {
  return value === undefined ? Promise.reject(new ApiError(404, "Not Found")) : Promise.resolve(structuredClone(value));
}

/**
 * Every top-level cited value of a record, confirmed because its quote was
 * found: true of every value in the sample. Stands in for what the server
 * works out.
 */
export function foundValues(record: FtRecord): ValueState[] {
  return Object.entries(record.data)
    .filter(([, v]) => typeof v === "object" && v !== null && "value" in v && "citation" in v)
    .map(([path]) => ({ path, confirmed: true, how: "found" as const, confirmed_at: record.written_at }));
}

let counter = 0;
/** A fresh ID for something the fake creates. */
export function fakeId(prefix: string): Id {
  counter += 1;
  return `${prefix}-fake-${counter}`;
}
