// The fields of each grant term kind (contracts.md section 1), in the order the
// award notice gives them, with a plain label and how a value is shown and typed.
// Only presentation lives here: whether a value counts is the server's call.

import type { ApprovalScope, BudgetCategory, Cited, FtRecord, RecordData } from "@/lib/api";
import { CATEGORY_LABELS, date, money } from "@/lib/format";

export type FieldType = "text" | "date" | "money" | "decimal" | "category" | "scope" | "label";

export interface TermField {
  /** The data key, as ValueState.path names a top-level value. */
  path: string;
  label: string;
  type: FieldType;
  /** The contract lets it be left out. */
  optional?: boolean;
}

export type TermKind = "period_of_performance" | "budget_line" | "person" | "approval_rule" | "rate" | "notice" | "other_term";

const DATED: TermField = { path: "dated", label: "Document date", type: "date" };

export const TERM_FIELDS: Record<TermKind, TermField[]> = {
  period_of_performance: [
    { path: "start", label: "Start date", type: "date", optional: true },
    { path: "end", label: "End date", type: "date" },
    DATED,
  ],
  budget_line: [
    { path: "name", label: "Budget line", type: "text" },
    { path: "amount", label: "Amount", type: "money" },
    { path: "category", label: "Category", type: "category" },
    DATED,
  ],
  person: [
    { path: "name", label: "Name", type: "text" },
    { path: "role", label: "Role", type: "text" },
    { path: "email", label: "Email", type: "text", optional: true },
    DATED,
  ],
  approval_rule: [
    { path: "applies_to", label: "Applies to", type: "text" },
    { path: "approver", label: "Approver", type: "text" },
    { path: "channel", label: "How", type: "text", optional: true },
    { path: "scope", label: "Scope", type: "scope", optional: true },
    DATED,
  ],
  rate: [
    { path: "name", label: "Rate", type: "text" },
    { path: "rate", label: "Value", type: "decimal" },
    DATED,
  ],
  notice: [
    { path: "amendment_number", label: "Amendment number", type: "text" },
    { path: "amendment_type", label: "Amendment type", type: "text" },
    { path: "obligated_by_amendment", label: "Amount obligated by this amendment", type: "money", optional: true },
    { path: "obligated_to_date", label: "Total amount obligated to date", type: "money", optional: true },
    DATED,
  ],
  other_term: [
    { path: "label", label: "Name", type: "label" },
    { path: "statement", label: "Statement", type: "text" },
    DATED,
  ],
};

export const TERM_KIND_LABELS: Record<TermKind, string> = {
  period_of_performance: "Dates",
  budget_line: "Budget line",
  person: "Person",
  approval_rule: "Approval rule",
  rate: "Rate",
  notice: "Funding notice",
  other_term: "Other term",
};

export const SCOPE_LABELS: Record<ApprovalScope, string> = {
  every_charge: "Every charge in the category",
  moved_out: "Only money moved out of the category",
};

export function isTermKind(kind: string): kind is TermKind {
  return kind in TERM_FIELDS;
}

export function isCited(value: unknown): value is Cited<unknown> {
  return typeof value === "object" && value !== null && "value" in value;
}

/** A field's raw value on a record: a cited value, a category, a label, or nothing. */
export function fieldValue(data: RecordData, path: string): unknown {
  return (data as unknown as Record<string, unknown>)[path];
}

/** A value as the screen shows it. */
export function showValue(type: FieldType, value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  switch (type) {
    case "money":
      return typeof value === "number" ? money(value) : String(value);
    case "date":
      return typeof value === "string" ? date(value) : String(value);
    case "category":
      return CATEGORY_LABELS[value as BudgetCategory] ?? String(value);
    case "scope":
      return SCOPE_LABELS[value as ApprovalScope] ?? String(value);
    default:
      return String(value);
  }
}

/** One field of a term, unwrapped: its value, and its quote when it has one. */
export function readField(record: FtRecord, field: TermField) {
  const raw = fieldValue(record.data, field.path);
  if (isCited(raw)) {
    return { value: raw.value, text: raw.text ?? null, citation: raw.citation ?? null };
  }
  return { value: raw, text: null, citation: null };
}
