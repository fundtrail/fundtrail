// The bodies the screens read, hand-written to follow the agreed screen bodies
// (#22) and the contract models in backend/app/contracts/.
//
// Temporary. Once the backend routes land, these are generated from FastAPI's
// OpenAPI schema with openapi-typescript into one file, and this module
// re-exports the generated names instead. Screens import only from
// "@/lib/api", never from this file's path, so the swap touches nothing else.
//
// Conventions (contracts.md, Conventions): IDs and dates are strings, money is
// integer cents, a calendar date is "YYYY-MM-DD", a timestamp is ISO 8601 UTC.

export type Id = string;
/** A calendar date, "YYYY-MM-DD". */
export type IsoDate = string;
/** A timezone-aware timestamp in UTC. */
export type IsoDatetime = string;
export type Cents = number;

// --- Workspaces and grants (contracts: workspaces.py) ---

export interface Workspace {
  id: Id;
  name: string;
  owner_id: Id;
  /** The workspace clock's "now"; null means the real date. */
  clock_now: IsoDatetime | null;
}

export interface Grant {
  id: Id;
  workspace_id: Id;
  funder: "NSF";
  /** Empty until the award letter is read. */
  award_number: string | null;
  title: string | null;
}

export interface Clock {
  now: IsoDatetime;
  /** False when the workspace runs on the real date. */
  simulated: boolean;
  next_arrival_at: IsoDatetime | null;
}

// --- Charges and files (contracts: charges.py, evidence.py) ---

export interface Charge {
  id: Id;
  workspace_id: Id;
  grant_id: Id;
  ledger_line_id: Id;
  transaction_date: IsoDate;
  posting_date: IsoDate;
  arrived_at: IsoDatetime;
  amount_cents: Cents;
  description: string;
  account: string;
  vendor: string | null;
  reference: string | null;
  original_line_id: string | null;
}

export type Source = "gmail" | "drive" | "upload";

export interface EvidenceFile {
  id: Id;
  workspace_id: Id;
  grant_id: Id;
  source: Source;
  name: string;
  media_type: string;
  storage_path: string;
  sha256: string;
  document_date: IsoDate | null;
  arrived_at: IsoDatetime;
  sender: string | null;
  source_ref: string | null;
  parent_id: string | null;
}

// --- Records (contracts: records.py). Only the parts the screens read are typed
// closely; the rest of a record's data is carried as it comes. ---

export interface Citation {
  file_id: Id;
  passage: string | null;
  location: { type: string; [key: string]: unknown };
  match: "exact" | "close" | "not_found" | null;
  highlight?: unknown[] | null;
}

export interface Cited<T> {
  value: T;
  text: string | null;
  citation: Citation | null;
}

export type BudgetCategory =
  | "senior_personnel"
  | "other_personnel"
  | "fringe_benefits"
  | "equipment"
  | "travel"
  | "participant_support"
  | "other_direct_costs"
  | "materials_and_supplies"
  | "publication"
  | "consultant_services"
  | "computer_services"
  | "subawards"
  | "other";

export interface PeriodOfPerformanceData {
  kind: "period_of_performance";
  dated: Cited<IsoDate>;
  start: Cited<IsoDate> | null;
  end: Cited<IsoDate>;
}

export interface BudgetLineData {
  kind: "budget_line";
  dated: Cited<IsoDate>;
  name: Cited<string>;
  amount: Cited<Cents>;
  category: BudgetCategory;
}

/** Any other record kind, carried as the server sends it. */
export interface OtherRecordData {
  kind: Exclude<string, "period_of_performance" | "budget_line">;
  [key: string]: unknown;
}

export type RecordData = PeriodOfPerformanceData | BudgetLineData | OtherRecordData;

export type Author = "agent" | "user";

export interface FtRecord<D extends RecordData = RecordData> {
  id: Id;
  workspace_id: Id;
  grant_id: Id;
  author: Author;
  author_user_id: Id | null;
  written_at: IsoDatetime;
  replaces_id: Id | null;
  data: D;
}

// --- The checks' output (contracts: checks.py) ---

export type Bucket = "evidence_complete" | "possible_conflict" | "missing_evidence" | "needs_human";

export interface Problem {
  check: Id;
  problem: Id;
  /** Built by code. The screen shows it as sent. */
  text: string;
  record_ids: Id[];
}

export interface Reason extends Problem {
  bucket: Bucket;
  expected_by: IsoDate | null;
  accepted_by: Id | null;
  offered_note_id: Id | null;
  /** #22: the dispute waiting against this reason, if any. */
  dispute_id?: Id | null;
}

export interface ChecklistEntry {
  item_record_id: Id | null;
  default_item: Id | null;
  added_by: "default" | "agent" | "user";
  needed: string;
  amount_cents: Cents | null;
  expected_by: IsoDate | null;
  filled: boolean;
  link_ids: Id[];
  removal_waiting_id: Id | null;
}

export interface ChargeStatus {
  grant_id: Id;
  charge_id: Id;
  bucket: Bucket;
  /** Every reason, passes included, in the server's order. */
  reasons: Reason[];
  checklist: ChecklistEntry[];
  flagged: boolean;
  rechecking: boolean;
  accepted: boolean;
  snoozed: boolean;
}

export interface RecordStatus {
  grant_id: Id;
  record_id: Id | null;
  file_id: Id | null;
  problems: Problem[];
  flagged: boolean;
  accepted: boolean;
  snoozed: boolean;
}

/** #22: a problem on the grant itself, with whether it's flagged, accepted or snoozed. */
export interface GrantProblem extends Problem {
  flagged: boolean;
  accepted: boolean;
  snoozed: boolean;
}

/** Anything about the grant as a whole that isn't a problem, such as an overspent line. */
export interface GrantNote {
  grant_id: Id;
  check: Id;
  /** Built by code. */
  text: string;
  record_ids: Id[];
}

// --- Screen bodies (#22 and its answers) ---

/** The next closeout date that follows from the end date in force, with its name as the server words it. */
export interface CloseoutDate {
  date: IsoDate;
  /** For example "Notice of Expiration". Worded by the server. */
  label: string;
}

/** GET /workspaces/{workspace_id}/grants, one row. Answer 7. */
export interface GrantSummary {
  grant: Grant;
  /** The end date in force; null while no period is confirmed. */
  end_date: IsoDate | null;
  charges_ready: number;
  charges_total: number;
  /** Rows on the grant's problem list. */
  on_problem_list: number;
  /** The agent's records waiting for the accountant. */
  waiting: number;
  bucket_counts: Record<Bucket, number>;
  next_closeout: CloseoutDate | null;
}

/** One budget line with what it holds and what's spent against it. Answer 8. */
export interface BudgetLineView {
  /** The budget_line term in force. */
  line: FtRecord<BudgetLineData>;
  amount_cents: Cents;
  spent_cents: Cents;
}

/** The grant's budget figures. Answer 8, with the grant notes beside them (answer 3). */
export interface BudgetView {
  lines: BudgetLineView[];
  /** The award's limit, "Total Amount Obligated to Date" on the latest confirmed notice. */
  limit_cents: Cents | null;
  /** The sum of the charges on the grant's ledger. */
  spent_cents: Cents;
}

export type RecordState = "counts" | "waiting" | "rejected" | "replaced" | "retracted";

export interface TermView {
  record: FtRecord;
  state: RecordState;
  decision: FtRecord | null;
  status: RecordStatus | null;
}

/** GET /grants/{grant_id}. Carries no flagged charges (answer 2). */
export interface GrantDetail {
  /** The same row the grant list shows, so the page and the list agree. */
  summary: GrantSummary;
  terms: TermView[];
  budget: BudgetView;
  grant_notes: GrantNote[];
}

/** One row on the problem list. The server sorts the rows (answer 1). */
export type ProblemRow =
  | {
      kind: "grant";
      problem: GrantProblem;
    }
  | {
      /** One row per source document with terms waiting (answer 4). */
      kind: "terms_waiting";
      file: EvidenceFile;
      record_ids: Id[];
      /** For example "8 terms waiting to be confirmed". Worded by the server. */
      text: string;
    }
  | {
      kind: "record";
      status: RecordStatus;
      record: FtRecord | null;
      file: EvidenceFile | null;
    }
  | {
      kind: "charge";
      charge: Charge;
      status: ChargeStatus;
    };

/** GET /grants/{grant_id}/problems: the problem list as its own response (answer 2). */
export interface ProblemList {
  rows: ProblemRow[];
}

/** GET /grants/{grant_id}/charges, one row. */
export interface ChargeRow {
  charge: Charge;
  /** Null until the checks first run on it. */
  status: ChargeStatus | null;
  /** The budget_line term the charge is assigned to (answer 8). */
  budget_line: FtRecord<BudgetLineData> | null;
  /** The ledger account group's NSF categories (answer 15). */
  account_categories: BudgetCategory[];
}
