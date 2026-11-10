import type { BudgetCategory, Bucket, Cents, HoldReason, IsoDate, IsoDatetime } from "./api/types";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

/** "$2,180.00", or "-$150.00" for a credit. */
export function money(cents: Cents): string {
  return usd.format(cents / 100);
}

const shortDate = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

/** "Feb 20, 2026". Calendar dates are read as UTC so they never shift a day. */
export function date(value: IsoDate | IsoDatetime): string {
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00Z` : value);
  return Number.isNaN(parsed.getTime()) ? value : shortDate.format(parsed);
}

/** The bucket names, written exactly as the docs write them. */
export const BUCKET_LABELS: Record<Bucket, string> = {
  possible_conflict: "Possible conflict",
  needs_human: "Needs a human",
  missing_evidence: "Missing evidence",
  evidence_complete: "Evidence complete",
};

/** NSF's standard budget categories, as the award notice names them. */
export const CATEGORY_LABELS: Record<BudgetCategory, string> = {
  senior_personnel: "Senior Personnel",
  other_personnel: "Other Personnel",
  fringe_benefits: "Fringe Benefits",
  equipment: "Equipment",
  travel: "Travel",
  participant_support: "Participant Support Costs",
  other_direct_costs: "Other Direct Costs",
  materials_and_supplies: "Materials and Supplies",
  publication: "Publication Costs",
  consultant_services: "Consultant Services",
  computer_services: "Computer Services",
  subawards: "Subawards",
  other_direct_costs_other: "Other",
};

/** Plain names for record kinds, for a row that has no file to name it by. */
const RECORD_KIND_LABELS: Record<string, string> = {
  period_of_performance: "Period of performance",
  budget_line: "Budget line",
  person: "Person",
  approval_rule: "Approval rule",
  rate: "Rate",
  notice: "Funding notice",
  other_term: "Other term",
  bill: "Bill",
  approval: "Approval",
  note: "Note",
  link: "Link",
  budget_assignment: "Budget line assignment",
  judgment: "Answer",
  checklist_item: "Checklist item",
  checklist_removal: "Checklist removal",
  dispute: "Dispute",
  duplicate: "Duplicate mark",
};

export function recordKindLabel(kind: string): string {
  return RECORD_KIND_LABELS[kind] ?? kind.replaceAll("_", " ");
}

/** Funders, spelled out with their short form. NSF only for now. */
export const FUNDER_LABELS: Record<string, string> = { NSF: "National Science Foundation (NSF)" };

/** Why mail is held, following the contract's words in mail.py (decision 0025). */
export const HOLD_REASON_LABELS: Record<HoldReason, string> = {
  unknown_sender: "The sender isn't a known sender.",
  unverified_sender: "The address is a known sender's, but it couldn't be verified as really theirs.",
};

export const SOURCE_LABELS = { gmail: "Gmail", drive: "Google Drive", upload: "Upload" } as const;
