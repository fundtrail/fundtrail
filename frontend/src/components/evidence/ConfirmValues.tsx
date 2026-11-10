"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { ApiError, useApi, type FactView, type Id, type RecordDataInput } from "@/lib/api";
import { pageCaption } from "@/components/viewer/placement";
import styles from "./evidence.module.css";
import { viewerHref } from "./links";
import { displayValue, isCited, parseTyped, valueAt, valueLabel, valueType, withValueAt } from "./values";

type Choice = "confirm" | "type";

/**
 * The confirm screen (product.md, Confirmed values; Correcting a value): each
 * value of one record that couldn't be found, with a choice to confirm it as
 * read or type the right one.
 *
 * How it's written (contracts.md, Not decided yet, "the working choice"):
 * - Nothing typed: one confirmation listing the record.
 * - Something typed: a new record replacing this one, with each typed value and
 *   no citation for it. When other values were left to confirm as read, a
 *   confirmation listing the new record follows.
 * The server's write check decides whether either is allowed; its problems are
 * shown as it words them.
 */
export function ConfirmValues({
  grantId,
  fileId,
  fact,
  onDone,
}: {
  grantId: Id;
  fileId: Id;
  fact: FactView;
  onDone: () => void;
}) {
  const api = useApi();
  const record = fact.record;
  const open = (fact.values ?? []).filter((v) => !v.confirmed);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [problems, setProblems] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  if (open.length === 0) {
    return <p className="ft-empty">Every value on this record is confirmed.</p>;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const nextErrors: Record<string, string> = {};
    let data = record.data as unknown as RecordDataInput;
    const typedPaths: string[] = [];
    for (const v of open) {
      if ((choices[v.path] ?? "confirm") !== "type") continue;
      const cited = valueAt(record.data, v.path);
      const parsed = parseTyped(valueType(v.path, isCited(cited) ? cited.value : undefined), typed[v.path] ?? "");
      if ("error" in parsed) {
        nextErrors[v.path] = parsed.error;
        continue;
      }
      // A value the accountant enters has no citation (contracts.md, Cited values).
      data = withValueAt(data, v.path, { value: parsed.value, text: null, citation: null });
      typedPaths.push(v.path);
    }
    setErrors(nextErrors);
    setProblems([]);
    if (Object.keys(nextErrors).length > 0) return;

    setBusy(true);
    let saved = false;
    try {
      if (typedPaths.length === 0) {
        await api.writeRecord(grantId, { data: { kind: "confirmation", record_ids: [record.id], decision: "confirmed" } });
      } else {
        const replacement = await api.writeRecord(grantId, { data, replaces_id: record.id });
        saved = true;
        if (typedPaths.length < open.length) {
          await api.writeRecord(grantId, { data: { kind: "confirmation", record_ids: [replacement.id], decision: "confirmed" } });
        }
      }
      onDone();
    } catch (err) {
      const said = err instanceof ApiError ? (err.problems ?? [err.message]) : ["Couldn't save. Try again."];
      setProblems(saved ? ["The typed values were saved. Confirming the rest wasn't:", ...said] : said);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} aria-label="Confirm or correct values">
      <ul className={styles.confirmList}>
        {open.map((v) => {
          const cited = valueAt(record.data, v.path);
          const label = valueLabel(v.path);
          const citation = isCited(cited) ? (cited.citation ?? null) : null;
          const type = valueType(v.path, isCited(cited) ? cited.value : undefined);
          const choice = choices[v.path] ?? "confirm";
          const inputId = `typed-${v.path}`;
          return (
            <li key={v.path} className={styles.confirmRow}>
              <span className="ft-heading">{label}</span>
              <span>
                Read as <span className="ft-strong">{isCited(cited) ? displayValue(v.path, cited) : "nothing"}</span>
              </span>
              {citation && (
                <Link className={styles.quote} href={viewerHref(grantId, citation.file_id, record.id, v.path)}>
                  {citation.passage ?? "A box on the image"}
                </Link>
              )}
              <span className="ft-caption">
                {citation && pageCaption(citation) ? `${pageCaption(citation)} · ` : ""}
                Couldn&apos;t be confirmed in the file
              </span>
              <fieldset className={styles.choice}>
                <legend className="ft-sr">{label}</legend>
                <label>
                  <input
                    type="radio"
                    name={`choice-${v.path}`}
                    checked={choice === "confirm"}
                    onChange={() => setChoices((c) => ({ ...c, [v.path]: "confirm" }))}
                  />{" "}
                  Confirm as read
                </label>
                <label>
                  <input
                    type="radio"
                    name={`choice-${v.path}`}
                    checked={choice === "type"}
                    onChange={() => setChoices((c) => ({ ...c, [v.path]: "type" }))}
                  />{" "}
                  Type the right value
                </label>
                {choice === "type" && (
                  <>
                    <label htmlFor={inputId} className="ft-sr">
                      The right {label.toLowerCase()}
                    </label>
                    <input
                      id={inputId}
                      className={styles.input}
                      type={type === "date" ? "date" : "text"}
                      inputMode={type === "money" || type === "number" ? "decimal" : undefined}
                      value={typed[v.path] ?? ""}
                      onChange={(e) => setTyped((t) => ({ ...t, [v.path]: e.target.value }))}
                      aria-invalid={errors[v.path] ? true : undefined}
                      aria-describedby={errors[v.path] ? `${inputId}-error` : undefined}
                    />
                  </>
                )}
              </fieldset>
              {errors[v.path] && (
                <span id={`${inputId}-error`} className="ft-error">
                  {errors[v.path]}
                </span>
              )}
            </li>
          );
        })}
      </ul>

      {problems.length > 0 && (
        <ul className="ft-error" role="alert">
          {problems.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
      )}

      <div className={styles.actions}>
        <button type="submit" className={`ft-btn ft-btn--main${busy ? " is-busy" : ""}`} aria-disabled={busy || undefined}>
          {busy ? "Saving…" : "Save"}
        </button>
        <Link className="ft-btn" href={viewerHref(grantId, fileId)}>
          Open the file
        </Link>
      </div>
    </form>
  );
}
