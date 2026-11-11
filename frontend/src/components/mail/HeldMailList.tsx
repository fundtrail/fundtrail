"use client";

import { useState } from "react";
import type { HeldMail, MailAction, SkipReason } from "@/lib/api";
import { date, HOLD_REASON_LABELS, UNREADABLE_FROM_LABEL } from "@/lib/format";
import { useWrite, WriteProblems } from "../setup/useWrite";
import styles from "./mail.module.css";

const SKIP_REASON_LABELS: Record<SkipReason, string> = {
  too_large: "too large",
  not_exportable: "couldn't be exported to a PDF",
};

const DONE_LABELS: Record<MailAction, string> = {
  let_in: "Let in. It arrives now as evidence.",
  dismiss: "Dismissed. It stays stored and unread.",
};

/** A file's small page glyph, drawn, for the file chips. */
function FileGlyph() {
  return (
    <svg className={styles.fileGlyph} width="10" height="12" viewBox="0 0 10 12" fill="none" aria-hidden="true" focusable="false">
      <path d="M1.5 1.5h4.2L8.5 4.3v6.2h-7z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M5.5 1.5v3h3" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
    </svg>
  );
}

/** An envelope, drawn: the empty list's one mark. */
function EnvelopeGlyph() {
  return (
    <svg className={styles.emptyGlyph} width="40" height="30" viewBox="0 0 40 30" fill="none" aria-hidden="true" focusable="false">
      <rect x="1.5" y="1.5" width="37" height="27" rx="3" stroke="currentColor" strokeWidth="2" />
      <path d="M3 4l17 13L37 4" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

function HeldMessage({ held, grantName }: { held: HeldMail; grantName: string | null }) {
  const { state, write } = useWrite();
  const [done, setDone] = useState<MailAction | null>(null);
  // Which button was pressed, so only that one looks busy while it saves.
  const [pressed, setPressed] = useState<MailAction | null>(null);

  async function decide(action: MailAction) {
    const saved = await write(held.grant_id, { data: { kind: "mail_action", held_mail_id: held.id, action } });
    if (saved) setDone(action);
  }

  const skipped = held.skipped ?? [];
  const saving = state.status === "saving";
  const busy = (action: MailAction) => (saving && pressed === action ? " is-busy" : "");
  // A message whose From line couldn't be read arrives with no sender (PR 137's review).
  const sender = held.sender?.trim() || null;
  return (
    <li className={styles.message} aria-label={`Held message ${held.subject ?? "with no subject"}`}>
      <div className={styles.head}>
        <div className={styles.who}>
          {sender && (
            <p className={styles.sender}>
              <span className="ft-sr">from </span>
              {sender}
            </p>
          )}
          <p className={sender ? styles.subject : styles.subjectAlone}>{held.subject ?? "(no subject)"}</p>
        </div>
        <div className={styles.when}>
          <p className={styles.heldAt}>Held {date(held.held_at)}</p>
          {grantName && <p className={styles.grant}>{grantName}</p>}
        </div>
      </div>
      <p className={styles.reason}>{sender ? HOLD_REASON_LABELS[held.reason] : UNREADABLE_FROM_LABEL}</p>
      <div className={styles.files}>
        <p className={`ft-label ${styles.filesLabel}`}>Files</p>
        <ul className={styles.chips} aria-label="Files">
          {held.files.map((f) => (
            <li key={f.sha256 + f.name} className={styles.chip}>
              <FileGlyph />
              {f.name}
            </li>
          ))}
        </ul>
      </div>
      {skipped.length > 0 && (
        <div className={styles.files}>
          <p className={`ft-label ${styles.filesLabel}`}>Skipped files</p>
          <ul className={styles.chips} aria-label="Skipped files">
            {skipped.map((f) => (
              <li key={f.name + f.skipped_at} className={`${styles.chip} ${styles.chipSkipped}`}>
                <FileGlyph />
                <span>{f.name}</span> <span className={styles.chipNote}>({SKIP_REASON_LABELS[f.reason]})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {done ? (
        <p className={styles.done} role="status">
          {DONE_LABELS[done]}
        </p>
      ) : (
        // A row's actions repeat on every held message, so neither is the page's
        // filled main button: Let in is the outlined approve, Dismiss its quiet partner.
        <div className={styles.actions}>
          <button
            type="button"
            className={`ft-btn ft-btn--sm ft-btn--approve${busy("let_in")}`}
            disabled={saving}
            onClick={() => {
              setPressed("let_in");
              void decide("let_in");
            }}
          >
            Let in
          </button>
          <button
            type="button"
            className={`ft-btn ft-btn--sm ft-btn--quiet${busy("dismiss")}`}
            disabled={saving}
            onClick={() => {
              setPressed("dismiss");
              void decide("dismiss");
            }}
          >
            Dismiss
          </button>
        </div>
      )}
      <WriteProblems state={state} />
    </li>
  );
}

/**
 * Mail held from senders who aren't known, or couldn't be verified (decision
 * 0025): each message with why it's held, its files and its skipped files, and
 * Let in or Dismiss. Letting in and dismissing are mail_action records.
 */
export function HeldMailList({ mail, grantNames = {} }: { mail: HeldMail[]; grantNames?: Record<string, string> }) {
  if (mail.length === 0) {
    return (
      <div className={styles.empty}>
        <EnvelopeGlyph />
        <p className={styles.emptyText}>No mail is held.</p>
      </div>
    );
  }
  return (
    <ul className={styles.list} aria-label="Held mail">
      {mail.map((held) => (
        <HeldMessage key={held.id} held={held} grantName={grantNames[held.grant_id] ?? null} />
      ))}
    </ul>
  );
}
