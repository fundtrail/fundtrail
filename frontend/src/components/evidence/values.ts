// Reading a record's cited values by the paths the server names them with
// (records.cited_values: "total", "items[0].amount", "period.start"), and the
// words a card shows for each. Whether a value is confirmed comes from the
// server's ValueState; nothing here works it out.

import type { Citation, Cited, IsoDate, ValueState } from "@/lib/api";
import { date, money } from "@/lib/format";

type Step = string | number;

/** "items[0].amount" -> ["items", 0, "amount"]. */
export function parsePath(path: string): Step[] {
  const steps: Step[] = [];
  for (const part of path.split(".")) {
    const m = /^([^[\]]+)((?:\[\d+\])*)$/.exec(part);
    if (!m) return [];
    steps.push(m[1]);
    for (const idx of m[2].matchAll(/\[(\d+)\]/g)) steps.push(Number(idx[1]));
  }
  return steps;
}

/** The thing at `path` inside a record's data, or undefined. */
export function valueAt(data: unknown, path: string): unknown {
  let at: unknown = data;
  for (const step of parsePath(path)) {
    if (at === null || typeof at !== "object") return undefined;
    at = (at as Record<string | number, unknown>)[step];
  }
  return at;
}

/** A copy of `data` with `next` put at `path`. The original is never changed. */
export function withValueAt<T>(data: T, path: string, next: unknown): T {
  const steps = parsePath(path);
  if (steps.length === 0) return data;
  const copy = structuredClone(data) as unknown as Record<string | number, unknown>;
  let at = copy;
  steps.slice(0, -1).forEach((step) => {
    at = at[step] as Record<string | number, unknown>;
  });
  at[steps[steps.length - 1]] = next;
  return copy as unknown as T;
}

export function isCited(v: unknown): v is Cited<unknown> {
  return v !== null && typeof v === "object" && "value" in v;
}

export function isCitation(v: unknown): v is Citation {
  return v !== null && typeof v === "object" && "file_id" in v && "location" in v;
}

/** The citation for a path: a cited value's citation, or the path's own citation (a link's part). */
export function citationAt(data: unknown, path: string): Citation | null {
  const v = valueAt(data, path);
  if (isCited(v)) return v.citation ?? null;
  return isCitation(v) ? v : null;
}

/**
 * Every CitedMoney field in backend/app/contracts/records.py, by its name:
 * BudgetLine.amount, BillItem.amount, Bill.total, ShareBasis.total,
 * Notice.obligated_by_amendment, Notice.obligated_to_date, Link.stated_amount.
 * Money is typed in dollars and sent in cents.
 */
export const MONEY_KEYS: ReadonlySet<string> = new Set([
  "amount",
  "total",
  "obligated_by_amendment",
  "obligated_to_date",
  "stated_amount",
]);

/** How a value is typed in and shown: money in cents, a calendar date, a number, or text. */
export type ValueType = "money" | "date" | "number" | "text";

export function valueType(path: string, value: unknown): ValueType {
  const last = parsePath(path).filter((s): s is string => typeof s === "string").pop() ?? "";
  if (typeof value === "number") return MONEY_KEYS.has(last) || last.endsWith("_cents") ? "money" : "number";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return "date";
  return "text";
}

/** What a card shows for a value: as the document writes it, or formatted when it was typed. */
export function displayValue(path: string, cited: Cited<unknown>): string {
  if (cited.text) return cited.text;
  const v = cited.value;
  switch (valueType(path, v)) {
    case "money":
      return money(v as number);
    case "date":
      return date(v as IsoDate);
    default:
      return String(v);
  }
}

const SINGULAR: Record<string, string> = { items: "Item", quotes: "Quote" };

/** "items[0].amount" -> "Item 1 amount", "approver_email" -> "Approver email". */
export function valueLabel(path: string): string {
  const words: string[] = [];
  for (const step of parsePath(path)) {
    if (typeof step === "number") {
      words.push(String(step + 1));
    } else {
      words.push(SINGULAR[step] ?? step.replaceAll("_", " "));
    }
  }
  const text = words.join(" ").toLowerCase();
  return text ? text[0].toUpperCase() + text.slice(1) : path;
}

/**
 * The words for a value's state (product.md, Evidence cards): found in its file
 * is "Confirmed on the page"; confirmed or typed by the accountant shows
 * "Confirmed by the accountant" with the date.
 */
export function confirmationText(state: ValueState): string {
  if (!state.confirmed) return "Unconfirmed";
  if (state.how === "found") return "Confirmed on the page";
  if (state.how === "record_confirmed" || state.how === "typed") {
    return state.confirmed_at ? `Confirmed by the accountant, ${date(state.confirmed_at)}` : "Confirmed by the accountant";
  }
  return "Confirmed";
}

/**
 * Reads what the accountant typed for a value of this type. Money becomes
 * cents ("$1,240.00" -> 124000). Returns an error sentence when it can't be read.
 */
export function parseTyped(type: ValueType, input: string): { value: unknown } | { error: string } {
  const raw = input.trim();
  if (!raw) return { error: "Type a value, or choose to confirm it as read." };
  if (type === "money") {
    const negative = /^\(.*\)$/.test(raw) || raw.startsWith("-") || raw.startsWith("−");
    const digits = raw.replace(/[()$,\s\-−]/g, "");
    if (!/^\d+(\.\d{1,2})?$/.test(digits)) return { error: "Type an amount such as 1,240.00." };
    const [whole, cents = ""] = digits.split(".");
    const value = Number(whole) * 100 + Number(cents.padEnd(2, "0"));
    return { value: negative ? -value : value };
  }
  if (type === "date") {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(raw) || Number.isNaN(Date.parse(`${raw}T00:00:00Z`))) return { error: "Choose a date." };
    return { value: raw };
  }
  if (type === "number") {
    const n = Number(raw.replace(/,/g, ""));
    return Number.isFinite(n) ? { value: n } : { error: "Type a number." };
  }
  return { value: raw };
}
