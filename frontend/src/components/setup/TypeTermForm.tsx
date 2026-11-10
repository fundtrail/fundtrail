"use client";

import { useId, useState, type FormEvent } from "react";
import type { BudgetCategory, FtRecord, RecordDataInput } from "@/lib/api";
import { CATEGORY_LABELS } from "@/lib/format";
import { readField, SCOPE_LABELS, TERM_FIELDS, type TermField, type TermKind } from "./termFields";

/** What the form starts from: the term's own value, written the way the input takes it. */
function startingValue(field: TermField, value: unknown): string {
  if (value === null || value === undefined) return "";
  if (field.type === "money" && typeof value === "number") return (value / 100).toFixed(2);
  return String(value);
}

/** "$12,000.00" or "12000" to cents, or null when it isn't an amount. */
export function parseCents(input: string): number | null {
  const cleaned = input.replace(/[$,\s]/g, "");
  if (!/^-?\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  return Math.round(Number(cleaned) * 100);
}

/**
 * Builds the term the accountant typed. A typed value carries no citation
 * (contracts.md, Cited values). Returns the problems instead when a required
 * value is empty or an amount can't be read.
 */
export function buildTypedTerm(kind: TermKind, values: Record<string, string>): { data: RecordDataInput } | { problems: string[] } {
  const data: Record<string, unknown> = { kind };
  const problems: string[] = [];
  for (const field of TERM_FIELDS[kind]) {
    const input = (values[field.path] ?? "").trim();
    if (input === "") {
      // The server fills in a missing document date with the workspace's "now".
      if (!field.optional && field.path !== "dated") problems.push(`${field.label} is needed.`);
      continue;
    }
    switch (field.type) {
      case "money": {
        const cents = parseCents(input);
        if (cents === null) problems.push(`${field.label} isn't an amount.`);
        else data[field.path] = { value: cents };
        break;
      }
      case "decimal": {
        // A rate is a plain number: a percent as a fraction, or cents per unit (records.py, CitedDecimal).
        if (!/^-?\d+(\.\d+)?$/.test(input)) problems.push(`${field.label} isn't a number.`);
        else data[field.path] = { value: input };
        break;
      }
      case "category":
      case "label":
        data[field.path] = input;
        break;
      default:
        data[field.path] = { value: input };
    }
  }
  return problems.length > 0 ? { problems } : { data: data as unknown as RecordDataInput };
}

function FieldInput({ field, value, onChange }: { field: TermField; value: string; onChange: (v: string) => void }) {
  const id = useId();
  const label = (
    <label htmlFor={id} className="ft-label">
      {field.label}
      {field.optional && <span className="ft-caption"> (optional)</span>}
    </label>
  );
  let control;
  if (field.type === "category") {
    control = (
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose a category</option>
        {(Object.keys(CATEGORY_LABELS) as BudgetCategory[]).map((c) => (
          <option key={c} value={c}>
            {CATEGORY_LABELS[c]}
          </option>
        ))}
      </select>
    );
  } else if (field.type === "scope") {
    control = (
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Not stated</option>
        {Object.entries(SCOPE_LABELS).map(([k, l]) => (
          <option key={k} value={k}>
            {l}
          </option>
        ))}
      </select>
    );
  } else {
    control = (
      <input
        id={id}
        type={field.type === "date" ? "date" : "text"}
        inputMode={field.type === "money" || field.type === "decimal" ? "decimal" : undefined}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <div className="ft-field">
      {label}
      {control}
    </div>
  );
}

/**
 * Typing the right value for a term. It saves a new term that replaces the
 * agent's, and a typed value counts as confirmed (product.md, Grants).
 */
export function TypeTermForm({
  term,
  kind,
  saving,
  onSave,
  onCancel,
}: {
  term: FtRecord;
  kind: TermKind;
  saving: boolean;
  onSave: (data: RecordDataInput) => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(TERM_FIELDS[kind].map((f) => [f.path, startingValue(f, readField(term, f).value)])),
  );
  const [problems, setProblems] = useState<string[]>([]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const built = buildTypedTerm(kind, values);
    if ("problems" in built) {
      setProblems(built.problems);
      return;
    }
    setProblems([]);
    onSave(built.data);
  }

  return (
    <form className="ft-typeterm" onSubmit={submit} aria-label="Type the right value">
      {TERM_FIELDS[kind].map((field) => (
        <FieldInput
          key={field.path}
          field={field}
          value={values[field.path] ?? ""}
          onChange={(v) => setValues((prev) => ({ ...prev, [field.path]: v }))}
        />
      ))}
      {problems.length > 0 && (
        <ul className="ft-error" role="alert">
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
      <div className="ft-actions">
        <button type="submit" className="ft-btn ft-btn--main ft-btn--sm" disabled={saving}>
          Save typed value
        </button>
        <button type="button" className="ft-btn ft-btn--sm" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  );
}
