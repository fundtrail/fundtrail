"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { ApiError, useApi, type FactView, type Id, type RecordDataInput } from "@/lib/api";
import { pageCaption } from "@/components/viewer/placement";
import styles from "./evidence.module.css";
import { viewerHref } from "./links";
import { QuoteLink } from "./QuoteLink";
import { displayValue, isCited, parseTyped, valueAt, valueLabel, valueType, withValueAt } from "./values";

type Choice = "confirm" | "type";

/**
 * The confirm screen (product.md, Confirmed values; Correcting a value): each
 * value of one record that couldn't be found, with a choice to confirm it as
 * read or type the right one.
 *
 * How it's written (the main coordinator's ruling on PR 111):
 * - Nothing typed: one confirmation listing the agent's record.
 * - Something typed: one write, a record replacing the agent's. Being the
 *   accountant's own record, it confirms everything in it. A typed value has
 *   no citation; a value left as read keeps its citation (or its `uncited`
 *   mark) exactly as the agent wrote it, so its highlight still shows and the
 *   two stay told apart.
 * The server's write check decides whether it's allowed; its problems are
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
      data = withValueAt(data, v.path, { value: parsed.value, text: null, citation: null, uncited: false });
      typedPaths.push(v.path);
    }
    setErrors(nextErrors);
    setProblems([]);
    if (Object.keys(nextErrors).length > 0) return;

    setBusy(true);
    try {
      await api.writeRecord(
        grantId,
        typedPaths.length === 0
          ? { data: { kind: "confirmation", record_ids: [record.id], decision: "confirmed" } }
          : { data, replaces_id: record.id },
      );
      onDone();
    } catch (err) {
      setProblems(err instanceof ApiError ? (err.problems ?? [err.message]) : ["Couldn't save. Try again."]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} aria-label="Confirm or correct values">
      {fact.state === "waiting" && (
        <p className={styles.waitingNote} role="note">
          This record is still waiting for you. Saving accepts the whole record, not only these values: &quot;Confirm as read&quot;
          confirms the record as the agent wrote it, and a typed value replaces it with your own.
        </p>
      )}
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
              <span className={styles.confirmLabel}>{label}</span>
              <span className={styles.readAs}>
                Read as <span className={styles.value}>{isCited(cited) ? displayValue(v.path, cited) : "nothing"}</span>
              </span>
              {citation && <QuoteLink citation={citation} href={viewerHref(grantId, citation.file_id, record.id, v.path)} />}
              <span className={styles.state}>
                {citation && pageCaption(citation) ? `${pageCaption(citation)} · ` : ""}
                Couldn&apos;t be confirmed in the file
              </span>
              <fieldset className={styles.choice}>
                <legend className="ft-sr">{label}</legend>
                <label className={styles.radio}>
                  <input
                    type="radio"
                    name={`choice-${v.path}`}
                    checked={choice === "confirm"}
                    onChange={() => setChoices((c) => ({ ...c, [v.path]: "confirm" }))}
                  />{" "}
                  Confirm as read
                </label>
                <label className={styles.radio}>
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
                <span id={`${inputId}-error`} className={`${styles.fieldError} ft-error`}>
                  {errors[v.path]}
                </span>
              )}
            </li>
          );
        })}
      </ul>

      {problems.length > 0 && (
        <ul className={`${styles.saveErrors} ft-error`} role="alert">
          {problems.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
      )}

      <div className={styles.formActions}>
        <button type="submit" className={`ft-btn ft-btn--main${busy ? " is-busy" : ""}`} aria-disabled={busy || undefined}>
          {busy ? "Saving…" : "Save"}
        </button>
        <Link className={`ft-link ${styles.quietAction}`} href={viewerHref(grantId, fileId)}>
          Open the file
        </Link>
      </div>
    </form>
  );
}
