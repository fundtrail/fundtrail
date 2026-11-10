"use client";

import { useState } from "react";
import type { HeldMail, MailAction, SkipReason } from "@/lib/api";
import { date, HOLD_REASON_LABELS, UNREADABLE_FROM_LABEL } from "@/lib/format";
import { useWrite, WriteProblems } from "../setup/useWrite";
import "../setup/setup.css";

const SKIP_REASON_LABELS: Record<SkipReason, string> = {
  too_large: "too large",
  not_exportable: "couldn't be exported to a PDF",
};

const DONE_LABELS: Record<MailAction, string> = {
  let_in: "Let in. It arrives now as evidence.",
  dismiss: "Dismissed. It stays stored and unread.",
};

function HeldMessage({ held, grantName }: { held: HeldMail; grantName: string | null }) {
  const { state, write } = useWrite();
  const [done, setDone] = useState<MailAction | null>(null);

  async function decide(action: MailAction) {
    const saved = await write(held.grant_id, { data: { kind: "mail_action", held_mail_id: held.id, action } });
    if (saved) setDone(action);
  }

  const skipped = held.skipped ?? [];
  // A message whose From line couldn't be read arrives with no sender (PR 137's review).
  const sender = held.sender?.trim() || null;
  return (
    <li className="ft-term" aria-label={`Held message ${held.subject ?? "with no subject"}`}>
      <div className="ft-term__head">
        <span className="ft-strong">{held.subject ?? "(no subject)"}</span>
        <span className="ft-caption">
          {sender ? <>from {sender} · </> : null}held {date(held.held_at)}
          {grantName && <> · {grantName}</>}
        </span>
      </div>
      <p>{sender ? HOLD_REASON_LABELS[held.reason] : UNREADABLE_FROM_LABEL}</p>
      <div>
        <p className="ft-label">Files</p>
        <ul className="ft-files" aria-label="Files">
          {held.files.map((f) => (
            <li key={f.sha256 + f.name}>{f.name}</li>
          ))}
        </ul>
      </div>
      {skipped.length > 0 && (
        <div>
          <p className="ft-label">Skipped files</p>
          <ul className="ft-files" aria-label="Skipped files">
            {skipped.map((f) => (
              <li key={f.name + f.skipped_at}>
                {f.name} <span className="ft-caption">({SKIP_REASON_LABELS[f.reason]})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {done ? (
        <p className="ft-caption" role="status">
          {DONE_LABELS[done]}
        </p>
      ) : (
        <div className="ft-actions">
          <button type="button" className="ft-btn ft-btn--main ft-btn--sm" disabled={state.status === "saving"} onClick={() => void decide("let_in")}>
            Let in
          </button>
          <button type="button" className="ft-btn ft-btn--sm" disabled={state.status === "saving"} onClick={() => void decide("dismiss")}>
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
  if (mail.length === 0) return <p className="ft-empty">No mail is held.</p>;
  return (
    <ul className="ft-terms" aria-label="Held mail">
      {mail.map((held) => (
        <HeldMessage key={held.id} held={held} grantName={grantNames[held.grant_id] ?? null} />
      ))}
    </ul>
  );
}
