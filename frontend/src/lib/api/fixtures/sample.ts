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
import type { Charge, Cents, EvidenceFile, FtRecord, Grant, HeldMail, Id, IsoDate, IsoDatetime, SignOffState, User, ValueState, Workspace } from "../types";
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

/**
 * Mail held for the sample grant (decision 0025). The contract's sample holds
 * none, so this adds one synthetic message from a sender nobody added: a vendor
 * sending a copy of invoice INV-1001 straight to the grant's address. The
 * grant's problem list and the mail screen both show it.
 */
export const SAMPLE_HELD_MAIL: HeldMail[] = [
  {
    id: "held-inv-1001-copy",
    workspace_id: WORKSPACE_ID,
    grant_id: SAMPLE_GRANT_ID,
    sender: "billing@labsupply.example",
    reason: "unknown_sender",
    source_ref: "gmail-synthetic-0002",
    subject: "Invoice INV-1001",
    held_at: "2026-04-08T14:10:00Z",
    files: [
      {
        name: "message.eml",
        media_type: "message/rfc822",
        storage_path: `${WORKSPACE_ID}/${SAMPLE_GRANT_ID}/held-inv-1001-copy/message.eml`,
        sha256: "fake-held-inv-1001-copy-message",
      },
      {
        name: "INV-1001.pdf",
        media_type: "application/pdf",
        storage_path: `${WORKSPACE_ID}/${SAMPLE_GRANT_ID}/held-inv-1001-copy/INV-1001.pdf`,
        sha256: "fake-held-inv-1001-copy-attachment",
      },
    ],
  },
];

/** The sample hasn't been signed off. Shared by the grant page and the closeout screen. */
export const SAMPLE_SIGN_OFF: SignOffState = { state: "not_signed", sign_off: null, changes: [] };

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
