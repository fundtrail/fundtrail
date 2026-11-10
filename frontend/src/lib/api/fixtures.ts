// Synthetic data for the fake API, shaped like the sample grant in contracts.md
// section 15. No person, award number or address in it is real: award numbers
// start with SYN- and email addresses use the .example domain.
//
// The sample grant is shown on Apr 9, 2026: the extension notice has arrived
// from Drive and waits for the accountant, so the old end date stays in force
// and L-1002 is in Possible conflict. The second grant is a made-up companion
// so the fake shows a grant problem (spending over the award's limit, one of
// the four code raises), a file problem and a grant note.
//
// Every status text here stands in for text the server builds. The screens show
// it as it comes.

import type {
  BudgetCategory,
  BudgetLineData,
  Bucket,
  Charge,
  ChargeRow,
  ChargeStatus,
  Cited,
  Clock,
  EvidenceFile,
  FtRecord,
  GrantDetail,
  GrantSummary,
  IsoDate,
  ProblemList,
  Reason,
  RecordState,
  TermView,
  Workspace,
} from "./types";

export const DEMO_WORKSPACE_ID = "ws-demo";
export const SAMPLE_GRANT_ID = "grant-sample";
export const KELP_GRANT_ID = "grant-kelp";
const CLOCK_NOW = "2026-04-09T12:00:00Z";

export const workspaces: Workspace[] = [
  { id: DEMO_WORKSPACE_ID, name: "Demo workspace", owner_id: "user-fake", clock_now: CLOCK_NOW },
];

export const clocks: Record<string, Clock> = {
  [DEMO_WORKSPACE_ID]: { now: CLOCK_NOW, simulated: true, next_arrival_at: "2026-04-10T15:00:00Z" },
};

// --- Helpers ---

function file(id: string, grantId: string, name: string, source: EvidenceFile["source"], arrivedAt: string, mediaType = "text/plain"): EvidenceFile {
  return {
    id,
    workspace_id: DEMO_WORKSPACE_ID,
    grant_id: grantId,
    source,
    name,
    media_type: mediaType,
    storage_path: `${DEMO_WORKSPACE_ID}/${grantId}/${id}/${name}`,
    sha256: `fake-${id}`,
    document_date: null,
    arrived_at: arrivedAt,
    sender: source === "gmail" ? "robin.example@university.example" : null,
    source_ref: null,
    parent_id: null,
  };
}

function cited<T>(value: T, fileId: string, passage: string, start: number): Cited<T> {
  return {
    value,
    text: null,
    citation: {
      file_id: fileId,
      passage,
      location: { type: "char_location", start_char_index: start, end_char_index: start + passage.length },
      match: "exact",
    },
  };
}

function budgetLine(id: string, grantId: string, fileId: string, name: string, cents: number, category: BudgetCategory, writtenAt: string): FtRecord<BudgetLineData> {
  return {
    id,
    workspace_id: DEMO_WORKSPACE_ID,
    grant_id: grantId,
    author: "agent",
    author_user_id: null,
    written_at: writtenAt,
    replaces_id: null,
    data: {
      kind: "budget_line",
      dated: cited("2023-01-10", fileId, "January 10, 2023", 40),
      name: cited(name, fileId, name, 900),
      amount: cited(cents, fileId, (cents / 100).toLocaleString("en-US"), 960),
      category,
    },
  };
}

function charge(id: string, grantId: string, line: string, tx: IsoDate, posted: IsoDate, cents: number, description: string, account: string, vendor: string | null, reference: string | null): Charge {
  return {
    id,
    workspace_id: DEMO_WORKSPACE_ID,
    grant_id: grantId,
    ledger_line_id: line,
    transaction_date: tx,
    posting_date: posted,
    arrived_at: `${posted}T00:00:00Z`,
    amount_cents: cents,
    description,
    account,
    vendor,
    reference,
    original_line_id: null,
  };
}

function pass(check: string, text: string): Reason {
  return { check, problem: "pass", text, record_ids: [], bucket: "evidence_complete", expected_by: null, accepted_by: null, offered_note_id: null };
}

function reason(check: string, problem: string, bucket: Bucket, text: string, extra: Partial<Reason> = {}): Reason {
  return { check, problem, text, record_ids: [], bucket, expected_by: null, accepted_by: null, offered_note_id: null, ...extra };
}

function status(c: Charge, bucket: Bucket, reasons: Reason[], flags: Partial<ChargeStatus> = {}): ChargeStatus {
  return {
    grant_id: c.grant_id,
    charge_id: c.id,
    bucket,
    reasons,
    checklist: [],
    flagged: false,
    rechecking: false,
    accepted: false,
    snoozed: false,
    ...flags,
  };
}

// --- The sample grant (contracts.md section 15) ---

const awardLetter = file("file-award", SAMPLE_GRANT_ID, "award_letter.txt", "upload", "2023-01-12T15:00:00Z");
const extensionNotice = file("file-extension", SAMPLE_GRANT_ID, "extension_notice.txt", "drive", "2026-04-09T09:00:00Z");

const sampleLines = {
  psc: budgetLine("term-psc", SAMPLE_GRANT_ID, awardLetter.id, "Participant Support Costs", 2_000_000, "participant_support", "2023-01-12T15:05:00Z"),
  odc: budgetLine("term-odc", SAMPLE_GRANT_ID, awardLetter.id, "Other Direct Costs", 10_000_000, "other_direct_costs", "2023-01-12T15:05:00Z"),
  ms: budgetLine("term-ms", SAMPLE_GRANT_ID, awardLetter.id, "Materials and Supplies", 4_000_000, "materials_and_supplies", "2023-01-12T15:05:00Z"),
  other: budgetLine("term-other", SAMPLE_GRANT_ID, awardLetter.id, "Other", 6_000_000, "other", "2023-01-12T15:05:00Z"),
};

const periodTerm: FtRecord = {
  id: "term-period",
  workspace_id: DEMO_WORKSPACE_ID,
  grant_id: SAMPLE_GRANT_ID,
  author: "agent",
  author_user_id: null,
  written_at: "2023-01-12T15:05:00Z",
  replaces_id: null,
  data: {
    kind: "period_of_performance",
    dated: cited("2023-01-10", awardLetter.id, "January 10, 2023", 40),
    start: cited("2023-02-01", awardLetter.id, "February 1, 2023", 420),
    end: cited("2026-01-31", awardLetter.id, "January 31, 2026", 445),
  },
};

const extensionTerm: FtRecord = {
  id: "term-extension",
  workspace_id: DEMO_WORKSPACE_ID,
  grant_id: SAMPLE_GRANT_ID,
  author: "agent",
  author_user_id: null,
  written_at: "2026-04-09T09:02:00Z",
  replaces_id: null,
  data: {
    kind: "period_of_performance",
    dated: cited("2026-01-15", extensionNotice.id, "January 15, 2026", 30),
    start: null,
    end: cited("2027-01-31", extensionNotice.id, "January 31, 2027", 310),
  },
};

const l1001 = charge("charge-l1001", SAMPLE_GRANT_ID, "L-1001", "2025-11-12", "2025-11-14", 124_000, "Sediment core liners", "55016 Lab Instruments and Supplies", "Example Lab Supply Co.", "INV-1001");
const l1002 = charge("charge-l1002", SAMPLE_GRANT_ID, "L-1002", "2026-02-20", "2026-02-24", 218_000, "Sediment DNA sequencing run 7", "59009 Recharge-Other Expenses", "Example Sequencing Core", "SEQ-0207");

const l1001Status = status(l1001, "evidence_complete", [
  pass("period_of_performance", "Cost date Nov 12, 2025 is inside the grant's period, Feb 1, 2023 to Jan 31, 2026."),
  pass("checklist", "Bills on file cover $1,240.00 of $1,240.00."),
]);
const l1002Status = status(
  l1002,
  "possible_conflict",
  [
    reason("period_of_performance", "after_end_date", "possible_conflict", "Cost date Feb 20, 2026 is after the grant's end date, Jan 31, 2026."),
    pass("checklist", "Bills on file cover $2,180.00 of $2,180.00."),
  ],
  { flagged: true },
);

function terms(views: [FtRecord, RecordState][]): TermView[] {
  return views.map(([record, state]) => ({ record, state, decision: null, status: null }));
}

const sampleSummary: GrantSummary = {
  grant: { id: SAMPLE_GRANT_ID, workspace_id: DEMO_WORKSPACE_ID, funder: "NSF", award_number: "SYN-2300117", title: "Sediment Microbiome Survey of Example Bay" },
  end_date: "2026-01-31",
  charges_ready: 1,
  charges_total: 2,
  on_problem_list: 2,
  waiting: 1,
  bucket_counts: { evidence_complete: 1, possible_conflict: 1, missing_evidence: 0, needs_human: 0 },
  next_closeout: { date: "2026-05-01", label: "Final financial report due" },
};

// --- A companion grant, made up for the fake ---

const kelpLetter = file("file-kelp-award", KELP_GRANT_ID, "award_letter.pdf", "upload", "2024-08-20T16:00:00Z", "application/pdf");
const kelpInvoice = file("file-kelp-inv", KELP_GRANT_ID, "invoice_KF-2210.pdf", "gmail", "2026-01-12T14:20:00Z", "application/pdf");

const kelpLines = {
  travel: budgetLine("kelp-travel", KELP_GRANT_ID, kelpLetter.id, "Travel", 150_000, "travel", "2024-08-20T16:10:00Z"),
  odc: budgetLine("kelp-odc", KELP_GRANT_ID, kelpLetter.id, "Other Direct Costs", 4_000_000, "other_direct_costs", "2024-08-20T16:10:00Z"),
  ms: budgetLine("kelp-ms", KELP_GRANT_ID, kelpLetter.id, "Materials and Supplies", 2_500_000, "materials_and_supplies", "2024-08-20T16:10:00Z"),
};

// The award letter: its period, and the funding notice that sets the award's
// limit, "Total Amount Obligated to Date".
const kelpPeriod: FtRecord = {
  id: "kelp-period",
  workspace_id: DEMO_WORKSPACE_ID,
  grant_id: KELP_GRANT_ID,
  author: "agent",
  author_user_id: null,
  written_at: "2024-08-20T16:10:00Z",
  replaces_id: null,
  data: {
    kind: "period_of_performance",
    dated: cited("2024-08-15", kelpLetter.id, "August 15, 2024", 40),
    start: cited("2024-09-01", kelpLetter.id, "September 1, 2024", 410),
    end: cited("2026-06-30", kelpLetter.id, "June 30, 2026", 438),
  },
};
const kelpNotice: FtRecord = {
  id: "kelp-notice",
  workspace_id: DEMO_WORKSPACE_ID,
  grant_id: KELP_GRANT_ID,
  author: "agent",
  author_user_id: null,
  written_at: "2024-08-20T16:10:00Z",
  replaces_id: null,
  data: {
    kind: "notice",
    dated: cited("2024-08-15", kelpLetter.id, "August 15, 2024", 40),
    amendment_number: cited("000", kelpLetter.id, "000", 120),
    amendment_type: cited("New Project", kelpLetter.id, "New Project", 140),
    obligated_by_amendment: cited(600_000, kelpLetter.id, "6,000", 180),
    obligated_to_date: cited(600_000, kelpLetter.id, "6,000", 220),
  },
};

const k201 = charge("charge-k201", KELP_GRANT_ID, "K-0201", "2025-10-03", "2025-10-07", 182_450, "Field season flights, Example Harbor", "52010 Domestic Travel", "Example Air", "TRV-0931");
const k202 = charge("charge-k202", KELP_GRANT_ID, "K-0202", "2025-12-15", "2025-12-18", 98_000, "Dive tank refills, December", "55016 Lab Instruments and Supplies", "Example Dive Supply", null);
const k203 = charge("charge-k203", KELP_GRANT_ID, "K-0203", "2026-01-09", "2026-01-12", 420_000, "Underwater camera housing", "55016 Lab Instruments and Supplies", "Example Optics Ltd.", "KF-2210");
const k204 = charge("charge-k204", KELP_GRANT_ID, "K-0204", "2026-02-02", "2026-02-04", -15_000, "Credit, returned mooring line", "55016 Lab Instruments and Supplies", "Example Marine Hardware", "CR-118");

const k201Status = status(k201, "needs_human", [
  reason("allowable", "unsure", "needs_human", "The agent is unsure whether the fare class is allowed. The accountant answers."),
  pass("checklist", "Bills on file cover $1,824.50 of $1,824.50."),
], { flagged: true });
const k202Status = status(k202, "missing_evidence", [
  reason("checklist", "missing_item", "missing_evidence", "A bill that adds up to the charge isn't on file.", { expected_by: "2025-12-18" }),
], { flagged: true });
const k203Status = status(k203, "evidence_complete", [pass("checklist", "Bills on file cover $4,200.00 of $4,200.00.")], { rechecking: true });
const k204Status = status(k204, "missing_evidence", [
  reason("checklist", "missing_item", "missing_evidence", "A written justification isn't on file.", { expected_by: "2026-02-04", accepted_by: "rec-accept-k204" }),
], { accepted: true });

const kelpSummary: GrantSummary = {
  grant: { id: KELP_GRANT_ID, workspace_id: DEMO_WORKSPACE_ID, funder: "NSF", award_number: "SYN-2400342", title: "Kelp Forest Canopy Recovery Survey" },
  end_date: "2026-06-30",
  charges_ready: 1,
  charges_total: 4,
  on_problem_list: 4,
  waiting: 0,
  bucket_counts: { evidence_complete: 1, possible_conflict: 0, missing_evidence: 2, needs_human: 1 },
  next_closeout: { date: "2026-08-31", label: "Award Closeout Certification due" },
};

// --- What the fake serves ---

export const grantSummaries: Record<string, GrantSummary[]> = {
  [DEMO_WORKSPACE_ID]: [sampleSummary, kelpSummary],
};

export const grantDetails: Record<string, GrantDetail> = {
  [SAMPLE_GRANT_ID]: {
    summary: sampleSummary,
    terms: terms([
      [extensionTerm, "waiting"],
      [periodTerm, "counts"],
      [sampleLines.psc, "counts"],
      [sampleLines.odc, "counts"],
      [sampleLines.ms, "counts"],
      [sampleLines.other, "counts"],
    ]),
    budget: {
      lines: [
        { line: sampleLines.psc, amount_cents: 2_000_000, spent_cents: 0 },
        { line: sampleLines.odc, amount_cents: 10_000_000, spent_cents: 342_000 },
        { line: sampleLines.ms, amount_cents: 4_000_000, spent_cents: 124_000 },
        { line: sampleLines.other, amount_cents: 6_000_000, spent_cents: 218_000 },
      ],
      limit_cents: 12_000_000,
      spent_cents: 342_000,
    },
    grant_notes: [],
  },
  [KELP_GRANT_ID]: {
    summary: kelpSummary,
    terms: terms([
      [kelpPeriod, "counts"],
      [kelpNotice, "counts"],
      [kelpLines.travel, "counts"],
      [kelpLines.odc, "counts"],
      [kelpLines.ms, "counts"],
    ]),
    budget: {
      lines: [
        { line: kelpLines.travel, amount_cents: 150_000, spent_cents: 182_450 },
        { line: kelpLines.odc, amount_cents: 4_000_000, spent_cents: 503_000 },
        { line: kelpLines.ms, amount_cents: 2_500_000, spent_cents: 503_000 },
      ],
      limit_cents: 600_000,
      spent_cents: 685_450,
    },
    grant_notes: [{ grant_id: KELP_GRANT_ID, check: "budget", text: "Travel: $1,824.50 of $1,500.00", record_ids: [kelpLines.travel.id] }],
  },
};

export const problemLists: Record<string, ProblemList> = {
  [SAMPLE_GRANT_ID]: {
    rows: [
      {
        kind: "terms_waiting",
        file: extensionNotice,
        record_ids: [extensionTerm.id],
        text: "1 term waiting to be confirmed",
      },
      { kind: "charge", charge: l1002, status: l1002Status },
    ],
  },
  [KELP_GRANT_ID]: {
    rows: [
      {
        kind: "grant",
        problem: {
          check: "budget",
          problem: "over_award_limit",
          text: "Spending of $6,854.50 is over the award's limit of $6,000.00.",
          record_ids: [kelpNotice.id],
          flagged: true,
          accepted: false,
          snoozed: false,
        },
      },
      {
        kind: "record",
        status: {
          grant_id: KELP_GRANT_ID,
          record_id: null,
          file_id: kelpInvoice.id,
          problems: [
            {
              check: "unlinked_bill",
              problem: "money_not_charged",
              text: "invoice_KF-2210.pdf: $380.00 nobody charged, 60 days after it arrived.",
              record_ids: [],
            },
          ],
          flagged: true,
          accepted: false,
          snoozed: false,
        },
        record: null,
        file: kelpInvoice,
      },
      { kind: "charge", charge: k201, status: k201Status },
      { kind: "charge", charge: k202, status: k202Status },
    ],
  },
};

export const chargeLists: Record<string, ChargeRow[]> = {
  [SAMPLE_GRANT_ID]: [
    { charge: l1001, status: l1001Status, budget_line: sampleLines.ms, account_categories: ["materials_and_supplies"] },
    { charge: l1002, status: l1002Status, budget_line: sampleLines.other, account_categories: ["other"] },
  ],
  [KELP_GRANT_ID]: [
    { charge: k201, status: k201Status, budget_line: kelpLines.travel, account_categories: ["travel"] },
    { charge: k202, status: k202Status, budget_line: kelpLines.ms, account_categories: ["materials_and_supplies"] },
    { charge: k203, status: k203Status, budget_line: kelpLines.ms, account_categories: ["materials_and_supplies"] },
    { charge: k204, status: k204Status, budget_line: kelpLines.ms, account_categories: ["materials_and_supplies"] },
  ],
};
