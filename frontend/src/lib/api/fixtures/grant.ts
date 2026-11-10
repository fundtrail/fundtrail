// The workspace, the grant list, the grant page, the problem list, the charges
// list and the records, for the sample grant at FAKE_NOW. Shared base (the
// screens foundation, #92): the grant list and grant page read it.
//
// Writing a record stores it in memory and returns it with an ID, the
// accountant as author and FAKE_NOW as its time. A sign-off is filled in the
// way the server fills it in, and the grant then shows as signed. The fake has
// no checks, so nothing else changes.

import type { ApiClient } from "../client";
import type { AgentRun, BudgetLine, ChargeRow, FtRecord, Grant, GrantDetail, GrantSummary, Id, ProblemList, RecordData, RecordState, RecordView, SignOff, TermView, Workspace } from "../types";
import { chargeStatusAt } from "./statuses";
import {
  atNow,
  FAKE_NOW,
  fakeId,
  foundValues,
  sample,
  sampleCharge,
  sampleFile,
  sampleRecord,
  sampleWorkspace,
  SAMPLE_HELD_MAIL,
  SAMPLE_REUSABLE_NOTE,
  SAMPLE_SIGN_OFF,
  served,
  SAMPLE_GRANT_ID,
  WORKSPACE_ID,
} from "./sample";

const AWARD_TERMS = [
  "rec-period",
  "rec-budget-participant-support",
  "rec-budget-other-direct-costs",
  "rec-budget-materials-and-supplies",
  "rec-budget-other",
  "rec-person-pi",
  "rec-person-program-officer",
  "rec-person-grants-officer",
  "rec-approval-rule",
  "rec-notice-000",
];

/** What counts at FAKE_NOW: everything but the extension, which waits for the accountant. */
function stateAt(record: FtRecord): RecordState {
  return record.id === "rec-period-extension" ? "waiting" : "counts";
}

export const sampleSummary: GrantSummary = {
  grant: sample.grant,
  end_date: "2026-01-31",
  charges_ready: 1,
  charges_total: 2,
  // The waiting terms row, the held mail row and L-1002.
  on_problem_list: 3,
  waiting: 1,
  bucket_counts: { evidence_complete: 1, possible_conflict: 1, missing_evidence: 0, needs_human: 0 },
  next_closeout: { date: "2026-05-01", label: "Final financial report due" },
};

function terms(): TermView[] {
  const decision = sampleRecord("rec-confirm-award-terms");
  const extension = sampleRecord("rec-period-extension");
  return [
    // Waiting first, then in force (answer 5).
    { record: extension, state: "waiting", decision: null, replaces: null, values: foundValues(extension), status: null },
    ...AWARD_TERMS.map((id) => {
      const record = sampleRecord(id);
      return { record, state: stateAt(record), decision, replaces: null, values: foundValues(record), status: null };
    }),
  ];
}

const line = (id: Id) => sampleRecord<FtRecord<BudgetLine>>(id);

function grantDetail(): GrantDetail {
  return {
    summary: sampleSummary,
    terms: terms(),
    budget: {
      lines: [
        { line: line("rec-budget-participant-support"), amount_cents: 2_000_000, spent_cents: 0 },
        { line: line("rec-budget-other-direct-costs"), amount_cents: 10_000_000, spent_cents: 342_000 },
        { line: line("rec-budget-materials-and-supplies"), amount_cents: 4_000_000, spent_cents: 124_000 },
        { line: line("rec-budget-other"), amount_cents: 6_000_000, spent_cents: 218_000 },
      ],
      limit_cents: 12_000_000,
      spent_cents: 342_000,
    },
    grant_notes: [],
    reusable_notes: [SAMPLE_REUSABLE_NOTE],
    sign_off: SAMPLE_SIGN_OFF,
  };
}

/**
 * What a sign-off stores (decision 0022), filled in by the fake the way the
 * server fills in a sign-off that sends only its note: a report path and
 * checksum that say they're fake, and a snapshot of the grant as served.
 */
function storedSignOff(grantId: Id, detail: GrantDetail, problems: ProblemList, charges: ChargeRow[], note: string | null | undefined): SignOff {
  const rowKey = (row: ProblemList["rows"][number]): string => {
    switch (row.kind) {
      case "grant":
        return `grant:${row.problem.check}:${row.problem.problem}`;
      case "terms_waiting":
        return `terms_waiting:${row.file.id}`;
      case "record":
        return `record:${row.status.record_id ?? ""}:${row.status.file_id ?? ""}`;
      case "charge":
        return `charge:${row.charge.id}`;
      case "held_mail":
        return `held_mail:${row.held.id}`;
    }
  };
  const id = fakeId("report");
  return {
    kind: "sign_off",
    note: note ?? null,
    report_path: `${WORKSPACE_ID}/${grantId}/reports/${id}.pdf`,
    report_sha256: `fake-${id}`,
    snapshot: {
      charges: charges.map(({ charge, status }) => ({
        charge_id: charge.id,
        bucket: status?.bucket ?? "needs_human",
        accepted: status?.accepted ?? false,
        reversed: status?.reversed ?? false,
      })),
      problem_rows: problems.rows.map(rowKey),
      totals: {
        ledger_total_cents: detail.budget.spent_cents,
        charges_total: detail.summary.charges_total,
        charges_ready: detail.summary.charges_ready,
        accepted: charges.filter((c) => c.status?.accepted).length,
        reversed: charges.filter((c) => c.status?.reversed).length,
        bucket_counts: detail.summary.bucket_counts,
      },
    },
  };
}

/** The server's order (answer 1): grant problems, then records, files and held mail, then charges. */
function problemList(): ProblemList {
  return {
    rows: [
      {
        kind: "terms_waiting",
        file: sampleFile("file-extension-notice"),
        record_ids: ["rec-period-extension"],
        text: "1 term waiting to be confirmed",
      },
      ...SAMPLE_HELD_MAIL.map((held) => ({ kind: "held_mail" as const, held })),
      { kind: "charge", charge: sampleCharge("chg-l-1002"), status: chargeStatusAt("chg-l-1002") },
    ],
  };
}

function chargeRows(): ChargeRow[] {
  return [
    { charge: sampleCharge("chg-l-1001"), status: chargeStatusAt("chg-l-1001"), budget_line: line("rec-budget-materials-and-supplies"), account_categories: ["materials_and_supplies"] },
    { charge: sampleCharge("chg-l-1002"), status: chargeStatusAt("chg-l-1002"), budget_line: line("rec-budget-other"), account_categories: ["other_direct_costs_other"] },
  ];
}

const sampleRuns: AgentRun[] = [
  {
    id: "run-extension-notice",
    workspace_id: WORKSPACE_ID,
    grant_id: SAMPLE_GRANT_ID,
    trigger: { kind: "file", id: "file-extension-notice" },
    status: "done",
    clock_now: "2026-04-09T16:00:00Z",
    queued_at: "2026-04-09T16:00:01Z",
    started_at: "2026-04-09T16:00:02Z",
    finished_at: "2026-04-09T16:00:30Z",
    summary: "Read extension_notice.txt: a new end date, Jan 31, 2027, waiting for the accountant.",
  },
];

/** A grant just added, before the agent has read its award letter: no terms, charges or problems. */
function newGrantDetail(grant: Grant): GrantDetail {
  return {
    summary: {
      grant,
      end_date: null,
      charges_ready: 0,
      charges_total: 0,
      on_problem_list: 0,
      waiting: 0,
      bucket_counts: { evidence_complete: 0, possible_conflict: 0, missing_evidence: 0, needs_human: 0 },
      next_closeout: null,
    },
    terms: [],
    budget: { lines: [], limit_cents: null, spent_cents: 0 },
    grant_notes: [],
    reusable_notes: [],
    sign_off: SAMPLE_SIGN_OFF,
  };
}

export function grantFake(): Pick<
  ApiClient,
  "listWorkspaces" | "createWorkspace" | "listGrants" | "getGrant" | "getProblemList" | "listCharges" | "listRecords" | "writeRecord" | "listRuns"
> & {
  /** Serve a grant added in fake mode (setup.ts creates it). */
  addGrant(grant: Grant): void;
} {
  const workspaces: Workspace[] = [sampleWorkspace];
  const records: RecordView[] = atNow.records.map((record) => ({ record, state: stateAt(record) }));
  const added = new Map<Id, Grant>();
  const isSample = (grantId: Id) => grantId === SAMPLE_GRANT_ID;
  const known = (grantId: Id) => isSample(grantId) || added.has(grantId);
  const addedIn = (workspaceId: Id) => [...added.values()].filter((g) => g.workspace_id === workspaceId).map((g) => newGrantDetail(g).summary);
  return {
    addGrant: (grant) => {
      added.set(grant.id, grant);
    },
    listWorkspaces: () => served(workspaces),
    createWorkspace: (name) => {
      // A workspace the user creates runs on the real date (architecture.md, The clock).
      const workspace: Workspace = { id: fakeId("ws"), name, owner_id: sample.user.id, clock_now: null };
      workspaces.push(workspace);
      return served(workspace);
    },
    listGrants: (workspaceId) =>
      served(
        workspaceId === WORKSPACE_ID
          ? [sampleSummary, ...addedIn(workspaceId)]
          : workspaces.some((w) => w.id === workspaceId)
            ? addedIn(workspaceId)
            : undefined,
      ),
    getGrant: (grantId) => {
      const grant = added.get(grantId);
      const detail = isSample(grantId) ? grantDetail() : grant ? newGrantDetail(grant) : undefined;
      // The latest sign-off stored in fake mode shows as signed. The fake has no
      // checks, so nothing changes after it.
      const signed = records.filter((r) => r.record.grant_id === grantId && r.record.data.kind === "sign_off").at(-1);
      if (detail && signed) detail.sign_off = { state: "signed", sign_off: signed.record as FtRecord<SignOff>, changes: [] };
      return served(detail);
    },
    getProblemList: (grantId) => served(isSample(grantId) ? problemList() : known(grantId) ? { rows: [] } : undefined),
    listCharges: (grantId) => served(isSample(grantId) ? chargeRows() : known(grantId) ? [] : undefined),
    listRecords: (grantId) => served(known(grantId) ? records.filter((r) => r.record.grant_id === grantId) : undefined),
    listRuns: (grantId) => served(isSample(grantId) ? sampleRuns : known(grantId) ? [] : undefined),
    writeRecord: (grantId, body) => {
      if (!known(grantId)) return served<FtRecord>(undefined);
      const record: FtRecord = {
        id: fakeId("rec"),
        workspace_id: WORKSPACE_ID,
        grant_id: grantId,
        author: "user",
        author_user_id: sample.user.id,
        written_at: FAKE_NOW,
        replaces_id: body.replaces_id ?? null,
        data:
          body.data.kind === "sign_off"
            ? storedSignOff(
                grantId,
                isSample(grantId) ? grantDetail() : newGrantDetail(added.get(grantId)!),
                isSample(grantId) ? problemList() : { rows: [] },
                isSample(grantId) ? chargeRows() : [],
                body.data.note,
              )
            : (body.data as RecordData),
      };
      records.push({ record, state: "counts" });
      return served(record);
    },
  };
}
