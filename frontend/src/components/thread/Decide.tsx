"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, type Citation, type EvidenceFile, type FtRecord, type Id, type RecordState } from "@/lib/api";
import { field } from "../charge/labels";
import type { Change } from "./describe";
import styles from "./thread.module.css";

export type Decision = "confirmed" | "rejected";

/** Sends the accountant's decision on one of the agent's records. The screen posts it as a confirmation record. */
export type OnDecide = (recordId: Id, decision: Decision) => Promise<void>;

/** The lines a failed write sends back: the write check's problems, or the error's message. */
export function errorLines(error: unknown): string[] {
  if (error instanceof ApiError) {
    if (Array.isArray(error.detail)) return error.detail.map((d) => (typeof d === "string" ? d : JSON.stringify(d)));
    if (typeof error.detail === "string") return [error.detail];
    return [error.message];
  }
  return [error instanceof Error ? error.message : "Something went wrong."];
}

/** Accept and Reject, in that order, with the write's problems shown if the server refuses it. */
function DecideButtons({ recordId, onDecide, what }: { recordId: Id; onDecide: OnDecide; what: string }) {
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  async function decide(decision: Decision) {
    setBusy(true);
    setErrors([]);
    try {
      await onDecide(recordId, decision);
    } catch (error) {
      setErrors(errorLines(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className={styles.actions}>
        <button type="button" className="ft-btn ft-btn--sm ft-btn--main" disabled={busy} onClick={() => void decide("confirmed")}>
          Accept<span className="ft-sr"> {what}</span>
        </button>
        <button type="button" className="ft-btn ft-btn--sm" disabled={busy} onClick={() => void decide("rejected")}>
          Reject<span className="ft-sr"> {what}</span>
        </button>
      </div>
      {errors.length > 0 && (
        <ul className="ft-error" role="alert">
          {errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
    </>
  );
}

const STATE_LABELS: Record<RecordState, string> = {
  waiting: "Waiting for you",
  counts: "Accepted",
  rejected: "Rejected",
  replaced: "Replaced",
  retracted: "Withdrawn",
};

/** A quoted passage with the file it's from. Opening the viewer is the viewer's link. */
export function Quote({ citation, files, href }: { citation: Citation; files: Record<Id, EvidenceFile>; href?: string }) {
  const file = files[citation.file_id];
  const name = file?.name ?? "a file";
  return (
    <figure className={styles.quote}>
      {citation.passage ? <blockquote>{citation.passage}</blockquote> : <p className="ft-caption">A marked area, with no text to quote.</p>}
      <figcaption className="ft-caption">
        {href ? (
          <Link className="ft-link" href={href}>
            {name}
          </Link>
        ) : (
          name
        )}
      </figcaption>
    </figure>
  );
}

/** A suggestion from the agent: the change it names, its reason, and Accept and Reject while it waits. */
export function SuggestionBox({
  record,
  change,
  state,
  onDecide,
}: {
  record: FtRecord;
  change: Change;
  state: RecordState;
  onDecide?: OnDecide;
}) {
  const waiting = state === "waiting";
  return (
    <div className={`${styles.box} ${waiting ? styles.waiting : ""}`} data-testid="suggestion" data-state={state}>
      <p className={styles.boxHead}>
        <span className="ft-label">Suggestion</span> <span className="ft-tag">{STATE_LABELS[state]}</span>
      </p>
      <p className="ft-strong">{change.title}</p>
      {(change.now || change.suggested) && (
        <dl className={styles.change}>
          {change.now && (
            <>
              <dt>Now</dt>
              <dd className={waiting ? undefined : styles.struck}>{change.now}</dd>
            </>
          )}
          {change.suggested && (
            <>
              <dt>Suggested</dt>
              <dd>{change.suggested}</dd>
            </>
          )}
        </dl>
      )}
      {change.reason && (
        <p>
          <span className="ft-label">Agent&apos;s reason</span> {change.reason}
        </p>
      )}
      {waiting && onDecide && <DecideButtons recordId={record.id} onDecide={onDecide} what={change.title} />}
      {state === "rejected" && (
        <p className="ft-caption">The agent can raise this again only if new evidence arrives.</p>
      )}
    </div>
  );
}

/** The agent's dispute of one of code's checks on this charge. */
export function DisputeBox({
  record,
  reasonText,
  state,
  files,
  quoteHref,
  onDecide,
}: {
  record: FtRecord;
  /** The disputed reason as the server words it, when the charge still has it. */
  reasonText: string | null;
  state: RecordState;
  files: Record<Id, EvidenceFile>;
  quoteHref?: (citation: Citation) => string | undefined;
  onDecide?: OnDecide;
}) {
  const waiting = state === "waiting";
  const check = field<string>(record, "check") ?? "";
  const quotes = field<Citation[]>(record, "quotes") ?? [];
  return (
    <div className={`${styles.box} ${waiting ? styles.waiting : ""}`} data-testid="dispute" data-state={state}>
      <p className={styles.boxHead}>
        <span className="ft-label">Dispute</span> <span className="ft-tag">{STATE_LABELS[state]}</span>
      </p>
      <p className="ft-strong">
        Disputes the check <span className="ft-id">{check}</span>
      </p>
      {reasonText && <p className="ft-caption">{reasonText}</p>}
      <p>
        <span className="ft-label">Agent&apos;s reasoning</span> {field<string>(record, "reasoning")}
      </p>
      {quotes.map((q, i) => (
        <Quote key={i} citation={q} files={files} href={quoteHref?.(q)} />
      ))}
      {waiting && (
        <p className="ft-caption">Accepting accepts this reason, with the agent&apos;s reasoning as the note.</p>
      )}
      {waiting && onDecide && <DecideButtons recordId={record.id} onDecide={onDecide} what="the dispute" />}
      {state === "rejected" && (
        <p className="ft-caption">The agent can dispute this check again only if new evidence arrives.</p>
      )}
    </div>
  );
}
