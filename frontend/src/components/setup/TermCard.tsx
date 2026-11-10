"use client";

import Link from "next/link";
import { useState } from "react";
import type { RecordData, RecordDataInput, RecordState, TermView } from "@/lib/api";
import { date, recordKindLabel } from "@/lib/format";
import { routes } from "@/lib/routes";
import { isTermKind, readField, showValue, TERM_FIELDS, TERM_KIND_LABELS } from "./termFields";
import { TypeTermForm } from "./TypeTermForm";
import { useWrite, WriteProblems } from "./useWrite";
import "./setup.css";

const STATE_LABELS: Record<RecordState, string> = {
  counts: "In force",
  waiting: "Waiting for you",
  rejected: "Rejected",
  replaced: "Replaced",
  retracted: "Withdrawn",
};

function decisionWord(data: RecordData): string {
  if (data.kind === "confirmation") return data.decision === "rejected" ? "Rejected" : "Confirmed";
  return recordKindLabel(data.kind);
}

const SAVED_LABELS ={ confirmed: "Confirmed.", rejected: "Rejected.", typed: "Your value is saved." } as const;

/**
 * One grant term: each value with its quote, the values that couldn't be found
 * in the file listed one by one, the term's own problem as the server words
 * it, and, while it waits, Confirm, Reject and Type the right value.
 */
export function TermCard({ term, settled = false }: { term: TermView; settled?: boolean }) {
  const { record } = term;
  const kind = record.data.kind;
  const { state, write } = useWrite();
  const [typing, setTyping] = useState(false);
  const [done, setDone] = useState<keyof typeof SAVED_LABELS | null>(null);

  if (!isTermKind(kind)) return null;
  const fields = TERM_FIELDS[kind];
  const unconfirmed = (term.values ?? []).filter((v) => !v.confirmed);
  const fieldLabel = (path: string) => fields.find((f) => f.path === path)?.label ?? path.replaceAll("_", " ");
  const saving = state.status === "saving";
  const waiting = term.state === "waiting";
  // A wrong term is rejected, then fixed by typing the right value (product.md, Grants).
  const rejectedNow = done === "rejected" || (done === null && term.state === "rejected");
  const fixable = record.author === "agent" && rejectedNow;

  async function decide(decision: "confirmed" | "rejected") {
    const saved = await write(record.grant_id, { data: { kind: "confirmation", record_ids: [record.id], decision } });
    if (saved) setDone(decision);
  }

  async function saveTyped(data: RecordDataInput) {
    const saved = await write(record.grant_id, { data, replaces_id: record.id });
    if (saved) {
      setTyping(false);
      setDone("typed");
    }
  }

  const muted = term.state === "rejected" || term.state === "replaced" || term.state === "retracted";

  return (
    <article className={`ft-term${muted ? " is-muted" : ""}`} aria-label={`${TERM_KIND_LABELS[kind]} term`}>
      <header className="ft-term__head">
        <span className="ft-strong">{TERM_KIND_LABELS[kind]}</span>
        <span className="ft-tag">{STATE_LABELS[term.state]}</span>
        <span className="ft-caption">
          {record.author === "agent" ? "Read by the agent" : "Typed by the accountant"}, {date(record.written_at)}
        </span>
      </header>

      <dl className="ft-term__values">
        {fields.map((field) => {
          const { value, text, citation } = readField(record, field);
          const shown = showValue(field.type, value);
          if (!shown && field.optional) return null;
          return (
            <div key={field.path} className="ft-term__value">
              <dt className="ft-label">{field.label}</dt>
              <dd>
                <span className={muted ? "ft-struck" : undefined}>{shown || "Not stated"}</span>
                {citation?.passage && (
                  <blockquote className="ft-quote">
                    {citation.passage}
                    {" "}
                    <Link className="ft-link ft-caption" href={routes.file(record.grant_id, citation.file_id)}>
                      Open the source
                    </Link>
                  </blockquote>
                )}
                {!citation && text && <span className="ft-caption"> · written “{text}”</span>}
              </dd>
            </div>
          );
        })}
      </dl>

      {unconfirmed.length > 0 && (
        <div className="ft-term__unconfirmed">
          <p className="ft-label">Couldn&apos;t be found in the file</p>
          <ul aria-label="Values not confirmed">
            {unconfirmed.map((v) => (
              <li key={v.path}>{fieldLabel(v.path)}</li>
            ))}
          </ul>
        </div>
      )}

      {term.status?.problems.map((p) => (
        <p key={`${p.check}:${p.problem}`} className="ft-problem__text">
          {p.text}
        </p>
      ))}

      {term.decision && !waiting && (
        <p className="ft-caption">
          {decisionWord(term.decision.data)} by the accountant, {date(term.decision.written_at)}
        </p>
      )}

      {waiting && !typing && done === null && !settled && (
        <div className="ft-actions">
          <button type="button" className="ft-btn ft-btn--main ft-btn--sm" disabled={saving} onClick={() => void decide("confirmed")}>
            Confirm
          </button>
          <button type="button" className="ft-btn ft-btn--sm" disabled={saving} onClick={() => void decide("rejected")}>
            Reject
          </button>
          <button type="button" className="ft-linkbtn" disabled={saving} onClick={() => setTyping(true)}>
            Type the right value
          </button>
        </div>
      )}
      {fixable && !typing && (
        <div className="ft-actions">
          <button type="button" className="ft-btn ft-btn--sm" disabled={saving} onClick={() => setTyping(true)}>
            Type the right value
          </button>
        </div>
      )}
      <p className="ft-caption">
        <Link className="ft-link" href={routes.record(record.grant_id, record.id)}>
          Open the term&apos;s thread
        </Link>
        {record.author === "agent" && " to tell the agent where to look"}
      </p>
      {typing && <TypeTermForm term={record} kind={kind} saving={saving} onSave={(d) => void saveTyped(d)} onCancel={() => setTyping(false)} />}
      {done && (
        <p className="ft-caption" role="status">
          {SAVED_LABELS[done]}
        </p>
      )}
      <WriteProblems state={state} />
    </article>
  );
}
