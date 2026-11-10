// The bodies the screens read and send, written by hand to follow the contract
// models in backend/app/contracts/ (api.py and the models it uses), named as
// there. A field with a default in the contract is optional here, as
// openapi-typescript writes it.
//
// Temporary. Once the backend routes land, these are generated from FastAPI's
// OpenAPI schema with openapi-typescript, and this module re-exports the
// generated names instead. Screens import only from "@/lib/api", never from
// this file's path, so the swap touches nothing else.
//
// Conventions (contracts.md, Conventions): IDs and dates are strings, money is
// integer cents, a calendar date is "YYYY-MM-DD", a timestamp is ISO 8601 UTC,
// and a decimal (such as a rate) is a string.

export type Id = string;
/** A calendar date, "YYYY-MM-DD". */
export type IsoDate = string;
/** A timezone-aware timestamp in UTC. */
export type IsoDatetime = string;
export type Cents = number;
/** A decimal, sent as a string. */
export type Decimal = string;

// --- workspaces.py ---

export interface User {
  id: Id;
  email: string;
  name?: string | null;
}

export interface Workspace {
  id: Id;
  name: string;
  owner_id: Id;
  /** The workspace clock's "now"; null means the real date. */
  clock_now?: IsoDatetime | null;
}

export interface Grant {
  id: Id;
  workspace_id: Id;
  funder?: "NSF";
  /** Empty until the award letter is read. */
  award_number?: string | null;
  title?: string | null;
  address_code?: string | null;
  drive_folder_id?: string | null;
  /** The grant's simulated now. Set only on sample grants; null means the real date (ruling 40). */
  clock_now?: IsoDatetime | null;
  /** Set only on a sample grant. */
  sample?: GrantSample | null;
}

// --- Sample grants (ruling 40, issue 165), as in workspaces.py, api.py and timeline.py. ---

export type SampleChoice = "small_live" | "larger_live" | "larger_prerun";

/** A workspace member's role (issue 160): the person who signs in, or the workspace's sample accountant. */
export type MemberRole = "owner" | "sample";

export interface GrantSample {
  /** The sample pack's ID, for example "nitrate-sensors". */
  sample: Id;
  choice: SampleChoice;
}

// --- charges.py, evidence.py ---

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
  vendor?: string | null;
  reference?: string | null;
  original_line_id?: string | null;
  /** The order it was stored in, from one sequence shared by records, charges and files. Never the clock. Null until stored. */
  stored_seq?: number | null;
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
  document_date?: IsoDate | null;
  arrived_at: IsoDatetime;
  sender?: string | null;
  source_ref?: string | null;
  parent_id?: string | null;
  /** The Google type a stored PDF was exported from (decision 0025). */
  exported_from?: string | null;
  /** The order it was stored in, from one sequence shared by records, charges and files. Never the clock. Null until stored. */
  stored_seq?: number | null;
}

// --- records.py: citations ---

export interface CharLocation {
  type: "char_location";
  start_char_index: number;
  end_char_index: number;
}
export interface PageLocation {
  type: "page_location";
  start_page_number: number;
  end_page_number: number;
}
export interface ContentBlockLocation {
  type: "content_block_location";
  start_block_index: number;
  end_block_index: number;
}
/** A box as fractions of the page or photo. */
export interface PageBox {
  page?: number;
  left: number;
  top: number;
  width: number;
  height: number;
}
export interface ImageBox extends PageBox {
  type: "image_box";
}
export type Location = CharLocation | PageLocation | ContentBlockLocation | ImageBox;

export interface CharRange {
  start_char_index: number;
  end_char_index: number;
}

export type Match = "exact" | "close" | "not_found";

export interface Citation {
  file_id: Id;
  passage: string | null;
  location: Location;
  match?: Match | null;
  highlight?: PageBox[] | CharRange[] | null;
}

export interface Cited<T> {
  value: T;
  /** The value exactly as the document writes it. */
  text?: string | null;
  citation?: Citation | null;
  /** Read from the document, but with no citation to show for it. Always unconfirmed until the accountant confirms it. */
  uncited?: boolean;
}
export type CitedText = Cited<string>;
export type CitedDate = Cited<IsoDate>;
export type CitedMoney = Cited<Cents>;
export type CitedDecimal = Cited<Decimal>;

export interface Period {
  start: IsoDate;
  end: IsoDate;
}
export interface CitedPeriod {
  start: CitedDate;
  end: CitedDate;
}

// --- records.py: record kinds ---

export type RecordKind =
  | "period_of_performance"
  | "budget_line"
  | "person"
  | "approval_rule"
  | "rate"
  | "notice"
  | "other_term"
  | "bill"
  | "approval"
  | "note"
  | "link"
  | "budget_assignment"
  | "judgment"
  | "checklist_item"
  | "checklist_removal"
  | "dispute"
  | "duplicate"
  | "correction"
  | "remainder"
  | "confirmation"
  | "accepted_reason"
  | "snooze"
  | "sign_off"
  | "mail_action"
  | "retraction";

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
  | "other_direct_costs_other";

export interface PeriodOfPerformance {
  kind: "period_of_performance";
  dated: CitedDate;
  start?: CitedDate | null;
  end: CitedDate;
}
export interface BudgetLine {
  kind: "budget_line";
  dated: CitedDate;
  name: CitedText;
  amount: CitedMoney;
  category: BudgetCategory;
  /** The evidence file of the notice (award letter or amendment) the line belongs to (issue 104). */
  notice_file_id?: Id | null;
}
export interface Person {
  kind: "person";
  dated: CitedDate;
  name: CitedText;
  email?: CitedText | null;
  role: CitedText;
}
export type ApprovalScope = "every_charge" | "moved_out";
export interface ApprovalRule {
  kind: "approval_rule";
  dated: CitedDate;
  applies_to: CitedText;
  approver: CitedText;
  channel?: CitedText | null;
  scope?: Cited<ApprovalScope> | null;
}
export interface Rate {
  kind: "rate";
  dated: CitedDate;
  name: CitedText;
  rate: CitedDecimal;
}
export interface Notice {
  kind: "notice";
  dated: CitedDate;
  amendment_number: CitedText;
  amendment_type: CitedText;
  obligated_by_amendment?: CitedMoney | null;
  obligated_to_date?: CitedMoney | null;
  award_number?: CitedText | null;
  title?: CitedText | null;
}
export interface OtherTerm {
  kind: "other_term";
  dated: CitedDate;
  label: string;
  statement: CitedText;
}

export interface BillItem {
  description: CitedText;
  amount: CitedMoney;
}
export interface Bill {
  kind: "bill";
  total: CitedMoney;
  vendor?: CitedText | null;
  dated?: CitedDate | null;
  description?: CitedText | null;
  document_number?: CitedText | null;
  items?: BillItem[];
}
export interface Approval {
  kind: "approval";
  approver_email: CitedText;
  covers: CitedText;
  approver_name?: CitedText | null;
  approved_on?: CitedDate | null;
  channel?: CitedText | null;
}
export interface Note {
  kind: "note";
  label: string;
  statement: CitedText;
  period?: CitedPeriod | null;
}
export interface ShareBasis {
  share: CitedDecimal;
  out_of: CitedDecimal;
  total: CitedMoney;
  note?: string | null;
}
export interface Link {
  kind: "link";
  record_id: Id;
  charge_id: Id;
  amount_cents?: Cents | null;
  part?: Citation | null;
  item_record_id?: Id | null;
  default_item?: Id | null;
  reason?: string | null;
  stated_amount?: CitedMoney | null;
  share?: ShareBasis | null;
}
export interface BudgetAssignment {
  kind: "budget_assignment";
  charge_id: Id;
  record_id: Id;
  reason: string;
}

export type Question = "allowable" | "covers" | "unusual_term" | "flag";
export type Answer = "supports" | "contradicts" | "unsure";

export interface Judgment {
  kind: "judgment";
  charge_id?: Id | null;
  question: Question;
  record_id?: Id | null;
  file_id?: Id | null;
  text: string;
  answer: Answer;
  reasoning: string;
  rule?: string | null;
  quotes?: Citation[];
  rests_on?: Id[];
}
export interface RateMath {
  quantity: CitedDecimal;
  rate?: CitedDecimal | null;
  rate_id?: Id | null;
}
export interface ChecklistItem {
  kind: "checklist_item";
  charge_id: Id;
  needed: string;
  amount_cents?: Cents | null;
  rate?: RateMath | null;
  period?: Period | null;
  expected_by?: IsoDate | null;
  nsf_standing_list?: string | null;
  reason?: string | null;
}
export interface ChecklistRemoval {
  kind: "checklist_removal";
  charge_id: Id;
  item_record_id?: Id | null;
  default_item?: Id | null;
  reason?: string | null;
}
export interface Dispute {
  kind: "dispute";
  charge_id: Id;
  check: Id;
  reasoning: string;
  quotes: Citation[];
}
export interface Duplicate {
  kind: "duplicate";
  copy_file_id: Id;
  original_file_id: Id;
  reason?: string | null;
}
export interface Correction {
  kind: "correction";
  charge_id: Id;
  corrects_line_id: Id;
  reason: string;
  quotes?: Citation[];
}
export interface Remainder {
  kind: "remainder";
  record_id: Id;
  other_award: CitedText;
  reason: string;
  quotes?: Citation[];
}
export type Decision = "confirmed" | "rejected";
export interface Confirmation {
  kind: "confirmation";
  record_ids: Id[];
  decision?: Decision;
}
export interface ReasonRef {
  check: Id;
  problem: Id;
}
export interface AcceptedReason {
  kind: "accepted_reason";
  charge_id?: Id | null;
  record_id?: Id | null;
  file_id?: Id | null;
  reason: ReasonRef;
  note: string;
  reusable?: boolean;
  reuses_id?: Id | null;
  rests_on?: Id[];
  /** For the award limit's over_limit problem: the amount over that was accepted. */
  amount_cents?: Cents | null;
}
export interface Snooze {
  kind: "snooze";
  charge_id?: Id | null;
  record_id?: Id | null;
  file_id?: Id | null;
  until: IsoDate;
  note: string;
  reasons: ReasonRef[];
}
export interface SignOff {
  kind: "sign_off";
  note?: string | null;
  report_path: string;
  report_sha256: string;
  snapshot: SignOffSnapshot;
}
export type MailAction = "let_in" | "dismiss";
export interface MailDecision {
  kind: "mail_action";
  held_mail_id: Id;
  action: MailAction;
}
export interface Retraction {
  kind: "retraction";
  reason?: string | null;
}

export type RecordData =
  | PeriodOfPerformance
  | BudgetLine
  | Person
  | ApprovalRule
  | Rate
  | Notice
  | OtherTerm
  | Bill
  | Approval
  | Note
  | Link
  | BudgetAssignment
  | Judgment
  | ChecklistItem
  | ChecklistRemoval
  | Dispute
  | Duplicate
  | Correction
  | Remainder
  | Confirmation
  | AcceptedReason
  | Snooze
  | SignOff
  | MailDecision
  | Retraction;

export type Author = "agent" | "user";

/** A record, generic over its data so a screen can say which kind it holds. Named `Record` in the contract. */
export interface FtRecord<D extends RecordData = RecordData> {
  id: Id;
  workspace_id: Id;
  grant_id: Id;
  author: Author;
  author_user_id?: Id | null;
  written_at: IsoDatetime;
  replaces_id?: Id | null;
  thread_message_id?: Id | null;
  /** The order it was stored in, from one sequence shared by records, charges and files. Never the clock. Null until stored. */
  stored_seq?: number | null;
  /** On the agent's records only: the read point of the run that wrote it (AgentRun.read_through_seq). */
  read_through_seq?: number | null;
  data: D;
}

// --- buckets.py, checks.py ---

export type Bucket = "evidence_complete" | "possible_conflict" | "missing_evidence" | "needs_human";

export interface Problem {
  check: Id;
  problem: Id;
  /** Built by code. The screen shows it as sent. */
  text: string;
  record_ids?: Id[];
  /** The accepted reason, or the confirmed dispute, that accepts it. */
  accepted_by?: Id | null;
  /** For the award limit's over_limit problem: the amount over. Null for every other problem. */
  amount_cents?: Cents | null;
}

export interface Reason extends Problem {
  bucket: Bucket;
  expected_by?: IsoDate | null;
  offered_note_id?: Id | null;
  /** The dispute waiting against this reason. */
  dispute_id?: Id | null;
}

/** Who added a checklist item. `rule`: code, because one of the grant's approval rules applies (issue 115). */
export type ItemSource = "default" | "rule" | "agent" | "user";

export interface ChecklistEntry {
  item_record_id?: Id | null;
  default_item?: Id | null;
  added_by: ItemSource;
  needed: string;
  amount_cents?: Cents | null;
  period?: Period | null;
  expected_by?: IsoDate | null;
  filled: boolean;
  link_ids?: Id[];
  removal_waiting_id?: Id | null;
  /** The approval rule that added it; set exactly when added_by is "rule". */
  rule_id?: Id | null;
}

export interface ChargeStatus {
  grant_id: Id;
  charge_id: Id;
  bucket: Bucket;
  /** Every reason, passes included, in the server's order. */
  reasons: Reason[];
  checklist: ChecklistEntry[];
  flagged: boolean;
  rechecking?: boolean;
  accepted?: boolean;
  snoozed?: boolean;
  net_cents?: Cents | null;
  corrections?: Id[];
  reversed?: boolean;
}

export interface RecordStatus {
  grant_id: Id;
  record_id?: Id | null;
  file_id?: Id | null;
  problems: Problem[];
  flagged: boolean;
  accepted?: boolean;
  snoozed?: boolean;
}

export interface GrantStatus {
  grant_id: Id;
  problems: Problem[];
  flagged: boolean;
  accepted?: boolean;
  snoozed?: boolean;
}

/** Anything about the grant as a whole that isn't a problem, such as an overspent line. */
export interface GrantNote {
  grant_id: Id;
  check: Id;
  /** Built by code. */
  text: string;
  record_ids?: Id[];
}

export interface OpenQuestion {
  charge_id: Id;
  question: Question;
  record_id?: Id | null;
  answer_by: Author;
}

// --- runs.py, threads.py ---

export type TriggerKind = "record" | "charge" | "file" | "thread_message" | "open_question" | "clock";

export interface Trigger {
  kind: TriggerKind;
  /** The record, charge, file or message; null for the clock. */
  id?: Id | null;
}

export interface StatusEntry {
  changed_at: IsoDatetime;
  trigger: Trigger;
  status: ChargeStatus | RecordStatus | GrantStatus;
}

export type RunStatus = "queued" | "running" | "done" | "failed";

export interface AgentRun {
  id: Id;
  workspace_id: Id;
  grant_id: Id;
  trigger: Trigger;
  status: RunStatus;
  clock_now: IsoDatetime;
  queued_at: IsoDatetime;
  started_at?: IsoDatetime | null;
  finished_at?: IsoDatetime | null;
  summary?: string | null;
  error?: string | null;
  log_path?: string | null;
  /** The highest stored_seq the run could see when it started. Null until it starts. */
  read_through_seq?: number | null;
  thread_charge_id?: Id | null;
  thread_record_id?: Id | null;
}

export interface ThreadMessage {
  id: Id;
  workspace_id: Id;
  grant_id: Id;
  charge_id?: Id | null;
  record_id?: Id | null;
  author: Author;
  author_user_id?: Id | null;
  run_id?: Id | null;
  text: string;
  written_at: IsoDatetime;
}

// --- mail.py ---

export interface HeldFile {
  name: string;
  media_type: string;
  storage_path: string;
  sha256: string;
}

export type HoldReason = "unknown_sender" | "unverified_sender";

export interface HeldMail {
  id: Id;
  workspace_id: Id;
  grant_id: Id;
  sender?: string | null;
  reason: HoldReason;
  source_ref: string;
  subject?: string | null;
  held_at: IsoDatetime;
  /** The message first, then its attachments. */
  files: HeldFile[];
  /** The message's files that weren't taken in. */
  skipped?: SkippedFile[];
}

export type SkipReason = "too_large" | "not_exportable";

/** A file Gmail or Drive brought that wasn't taken in. */
export interface SkippedFile {
  workspace_id: Id;
  grant_id: Id;
  name: string;
  source: "gmail" | "drive";
  source_ref: string;
  reason: SkipReason;
  skipped_at: IsoDatetime;
}

// --- signoff.py ---

export interface ChargeSnapshot {
  charge_id: Id;
  bucket: Bucket;
  accepted: boolean;
  reversed: boolean;
}
export interface SnapshotTotals {
  ledger_total_cents: Cents;
  charges_total: number;
  charges_ready: number;
  accepted: number;
  reversed: number;
  bucket_counts: Record<Bucket, number>;
}
export interface SignOffSnapshot {
  charges: ChargeSnapshot[];
  problem_rows: Id[];
  totals: SnapshotTotals;
}
export type ChangeKind = "charge" | "problem_list" | "total";
export interface SnapshotChange {
  kind: ChangeKind;
  subject: Id;
  before?: string | null;
  after?: string | null;
}
export type SignOffStateName = "not_signed" | "signed" | "changed";

// --- api.py: workspaces and the clock ---

export interface WorkspaceCreate {
  name: string;
}

export type ArrivalSource = "ledger" | "gmail" | "drive" | "upload";

/** The next item waiting for the clock: when, where from and its name. Not its contents. */
export interface NextArrival {
  at: IsoDatetime;
  source: ArrivalSource;
  /** The file name, or the ledger line ID. */
  name: string;
}

export interface Clock {
  now: IsoDatetime;
  /** False when the workspace runs on the real date. */
  simulated: boolean;
  next_arrival_at?: IsoDatetime | null;
  next_arrival?: NextArrival | null;
}

/** POST /workspaces/{workspace_id}/clock. No `to` moves to the next arrival. */
export interface ClockMove {
  to?: IsoDatetime | null;
}

// --- api.py: what code works out about a record ---

export type RecordState = "counts" | "waiting" | "rejected" | "replaced" | "retracted";

export type ValueHow = "found" | "record_confirmed" | "typed";

export interface ValueState {
  /** As records.cited_values names it, for example "total" or "items[0].amount". */
  path: string;
  confirmed: boolean;
  how?: ValueHow | null;
  confirmed_at?: IsoDatetime | null;
}

/** One row of GET /grants/{grant_id}/records. */
export interface RecordView {
  record: FtRecord;
  state: RecordState;
}

// --- api.py: the grant list and the grant page ---

export interface CloseoutDate {
  date: IsoDate;
  /** For example "Notice of Expiration". Worded by the server. */
  label: string;
}

/** One row of GET /workspaces/{workspace_id}/grants (issue 22, answer 7). */
export interface GrantSummary {
  grant: Grant;
  /** The end date in force; null while no period is confirmed. */
  end_date?: IsoDate | null;
  charges_ready: number;
  charges_total: number;
  on_problem_list: number;
  waiting: number;
  bucket_counts: Record<Bucket, number>;
  next_closeout?: CloseoutDate | null;
  /** The grant's now, so screens never ask the browser for the date (ruling 40). */
  now: IsoDatetime;
}

// --- Sample grants: choosing one, and its timeline (ruling 40). ---

/** One choice in the Sample dropdown, in the order GET /samples sends them. Names and descriptions are the packs' placeholders. */
export interface SampleOption {
  choice: SampleChoice;
  name: string;
  description: string;
  /** True for the larger live sample: opening it asks the user to confirm first. */
  needs_confirm: boolean;
  available: boolean;
  unavailable_reason?: string | null;
}

/** POST /workspaces/{workspace_id}/samples. Returns the new grant's GrantSummary (201). */
export interface SampleCreate {
  choice: SampleChoice;
  confirmed?: boolean;
}

/**
 * "needs_confirm": opening the larger read-live sample needs the user's confirm.
 * "another_sample_working": moving a larger read-live sample's clock waits
 * while another of the user's larger read-live samples still has agent runs
 * from its last move.
 */
export type SampleRefusalReason = "needs_confirm" | "another_sample_working";

/** The 409 detail when opening a sample or moving its clock is refused (ruling 41). */
export interface SampleRefusal {
  reason: SampleRefusalReason;
  message: string;
  /** The grant that blocks it, for another_sample_working. */
  grant?: GrantSummary | null;
}

/** "arrival": a file, the ledger file or a ledger line. "user_delivery": an item the user brings in. "checks_date": a date the checks work out. */
export type TimelineEventKind = "arrival" | "user_delivery" | "checks_date";

export interface TimelineEvent {
  id: Id;
  at: IsoDatetime;
  kind: TimelineEventKind;
  source?: ArrivalSource | null;
  name: string;
  note?: string | null;
  /** Once played or on file. */
  charge_id?: Id | null;
  file_id?: Id | null;
}

/** An event the last move played, with what the agent wrote from it so far. */
export interface PlayedEvent {
  event: TimelineEvent;
  agent_records?: FtRecord[];
  charge_ids?: Id[];
  /** Decisions the workspace's sample accountant made in that move (ruling 47). */
  scripted_decisions?: FtRecord[];
  /** The result was loaded from the prerun, not worked live. */
  loaded?: boolean;
}

export interface UserDelivery {
  event: TimelineEvent;
  delivered: boolean;
  delivered_at?: IsoDatetime | null;
}

export interface TimelineNow {
  now: IsoDatetime;
  /** What the clock stopped on. */
  stopped_on?: TimelineEvent | null;
  /** Items for the user to bring in whose date has come and that aren't delivered yet. They stay available. */
  deliveries?: UserDelivery[];
  /** How many rows wait on the grant's problem list. */
  waiting_on_problem_list: number;
}

/** GET /grants/{grant_id}/timeline. Every timeline route is a 404 on a grant that isn't a sample. */
export interface TimelineView {
  /** The events the last move played. */
  just_happened?: PlayedEvent[];
  now: TimelineNow;
  /** In date order. */
  coming_up?: TimelineEvent[];
  finished: boolean;
  catching_up: boolean;
  /** The read-ahead sample only: whether its saved results still apply. Null on a sample read live. */
  on_run_through?: boolean | null;
}

/** POST /grants/{grant_id}/timeline. No `to` plays to the next event. Forward only: earlier is a 409. */
export interface TimelineMove {
  to?: IsoDatetime | null;
  /** The sample accountant performs the scripted human steps as the clock passes them (ruling 47). */
  skip_human_steps?: boolean;
}

/** POST /grants/{grant_id}/timeline/start-over. */
export interface TimelineStartOver {
  confirmed: boolean;
}

export interface TermView {
  record: FtRecord;
  state: RecordState;
  decision?: FtRecord | null;
  replaces?: FtRecord | null;
  values?: ValueState[];
  status?: RecordStatus | null;
}

export interface BudgetLineView {
  /** The budget_line term in force. */
  line: FtRecord<BudgetLine>;
  amount_cents: Cents;
  spent_cents: Cents;
}

export interface BudgetView {
  lines: BudgetLineView[];
  /** "Total Amount Obligated to Date" on the latest confirmed notice. */
  limit_cents?: Cents | null;
  spent_cents: Cents;
}

export interface ReusableNoteView {
  note: FtRecord<AcceptedReason>;
  charge: Charge;
  amount_limit_cents: Cents;
  covered?: Charge[];
}

export interface SignOffState {
  state: SignOffStateName;
  sign_off?: FtRecord<SignOff> | null;
  changes?: SnapshotChange[];
}

/** GET /grants/{grant_id}. Carries no flagged charges: the problem list has its own response. */
export interface GrantDetail {
  summary: GrantSummary;
  terms: TermView[];
  budget: BudgetView;
  grant_notes: GrantNote[];
  reusable_notes?: ReusableNoteView[];
  sign_off: SignOffState;
}

// --- api.py: the problem list. The server sorts the rows. ---

export interface GrantProblem extends Problem {
  flagged: boolean;
  accepted?: boolean;
  snoozed?: boolean;
}

export interface GrantProblemRow {
  kind: "grant";
  problem: GrantProblem;
}
export interface TermsWaitingRow {
  kind: "terms_waiting";
  file: EvidenceFile;
  record_ids: Id[];
  /** For example "8 terms waiting to be confirmed". Worded by the server. */
  text: string;
}
export interface RecordProblemRow {
  kind: "record";
  status: RecordStatus;
  record?: FtRecord | null;
  file?: EvidenceFile | null;
}
export interface ChargeProblemRow {
  kind: "charge";
  charge: Charge;
  status: ChargeStatus;
}
export interface HeldMailRow {
  kind: "held_mail";
  held: HeldMail;
}

export type ProblemRow = GrantProblemRow | TermsWaitingRow | RecordProblemRow | ChargeProblemRow | HeldMailRow;

/** GET /grants/{grant_id}/problems */
export interface ProblemList {
  rows: ProblemRow[];
}

// --- api.py: the charges list and the charge page ---

export interface ChargeRow {
  charge: Charge;
  status?: ChargeStatus | null;
  budget_line?: FtRecord<BudgetLine> | null;
  account_categories?: BudgetCategory[];
}

/** One status change, worded by the server. */
export interface HistoryEntry {
  entry: StatusEntry;
  /** For example "new end date confirmed". */
  text: string;
}

/** One fact covering a charge, for example "invoice 2050, $5,000 of $10,000". */
export interface LinkView {
  link: FtRecord<Link>;
  record: FtRecord;
  values?: ValueState[];
  file?: EvidenceFile | null;
}

export interface RuleSource {
  label: string;
  url: string;
}

export interface RuleView {
  id: Id;
  title: string;
  text: string;
  sources?: RuleSource[];
}

export interface AnswerView {
  judgment: FtRecord<Judgment>;
  out_of_date: boolean;
  rule?: RuleView | null;
}

/** What accepting one of the agent's waiting records changes, worded by code (issue 114). */
export interface SuggestionChange {
  /** What accepting does, in one line. */
  title: string;
  /** What's in force now, when it replaces something. */
  now?: string | null;
  /** What the agent suggests instead. */
  suggested?: string | null;
}

export interface SuggestionView {
  record: FtRecord;
  replaces?: FtRecord | null;
  charge_ids?: Id[];
  /** What accepting it changes, worded by the server. The platform fills it. */
  change?: SuggestionChange | null;
}

export interface StatusThreadEntry {
  kind: "status";
  entry: StatusEntry;
}
export interface MessageThreadEntry {
  kind: "message";
  message: ThreadMessage;
}
export interface RecordThreadEntry {
  kind: "record";
  record: FtRecord;
  state: RecordState;
}
export type ThreadEntry = StatusThreadEntry | MessageThreadEntry | RecordThreadEntry;

/** A charge's or a record's thread, merged in time order by the server. */
export interface Thread {
  entries: ThreadEntry[];
  /** A run that will reach this thread, running or queued. */
  agent_run?: AgentRun | null;
}

export interface NewMessage {
  text: string;
}

/** GET /charges/{charge_id} */
export interface ChargeDetail {
  charge: Charge;
  status?: ChargeStatus | null;
  budget_line?: FtRecord<BudgetLine> | null;
  account_categories?: BudgetCategory[];
  corrections?: Charge[];
  history?: HistoryEntry[];
  links?: LinkView[];
  answers?: AnswerView[];
  questions?: OpenQuestion[];
  waiting?: SuggestionView[];
  thread: Thread;
  records?: Record<Id, FtRecord>;
  files?: Record<Id, EvidenceFile>;
}

// --- api.py: evidence cards ---

export interface FactLink {
  link: FtRecord<Link>;
  charge: Charge;
}

export interface FactView {
  record: FtRecord;
  state: RecordState;
  values?: ValueState[];
  links?: FactLink[];
  status?: RecordStatus | null;
}

export interface DuplicateView {
  mark: FtRecord<Duplicate>;
  state: RecordState;
}

/** One row of GET /grants/{grant_id}/evidence. */
export interface EvidenceCard {
  file: EvidenceFile;
  facts?: FactView[];
  status?: RecordStatus | null;
  duplicate?: DuplicateView | null;
  files?: Record<Id, EvidenceFile>;
}

// --- api.py: uploads and files ---

export interface RowError {
  /** 1 is the first row after the header. */
  row: number;
  message: string;
}

/** POST /grants/{grant_id}/ledger */
export interface LedgerUploadResult {
  added: number;
  already_present: number;
  rejected: RowError[];
}

/** GET /evidence/{file_id}/content: a short-lived link to the original. */
export interface FileLink {
  url: string;
  media_type?: string | null;
  expires_at: IsoDatetime;
}

// --- api.py: the records request (POST /grants/{grant_id}/records) ---

type WithOptionalDated<T> = Omit<T, "dated"> & { dated?: CitedDate | null };

export type PeriodOfPerformanceInput = WithOptionalDated<PeriodOfPerformance>;
export type BudgetLineInput = WithOptionalDated<BudgetLine>;
export type PersonInput = WithOptionalDated<Person>;
export type ApprovalRuleInput = WithOptionalDated<ApprovalRule>;
export type RateInput = WithOptionalDated<Rate>;
export type NoticeInput = WithOptionalDated<Notice>;
export type OtherTermInput = WithOptionalDated<OtherTerm>;

/** A sign-off sends only its note: the server stores the report and fills in the rest. */
export interface SignOffInput {
  kind: "sign_off";
  note?: string | null;
}

export type RecordDataInput =
  | PeriodOfPerformanceInput
  | BudgetLineInput
  | PersonInput
  | ApprovalRuleInput
  | RateInput
  | NoticeInput
  | OtherTermInput
  | Bill
  | Approval
  | Note
  | Link
  | BudgetAssignment
  | Judgment
  | ChecklistItem
  | ChecklistRemoval
  | Dispute
  | Duplicate
  | Correction
  | Remainder
  | Confirmation
  | AcceptedReason
  | Snooze
  | SignOffInput
  | MailDecision
  | Retraction;

/** POST /grants/{grant_id}/records. The server fills in the ID, the author and the time. */
export interface NewRecordInput {
  data: RecordDataInput;
  replaces_id?: Id | null;
}

/** The 422 body when the write check finds problems. */
export interface WriteRejected {
  detail: string[];
}
