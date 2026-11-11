"use client";

import { useEffect, useRef, useState } from "react";
import type { Bucket, Cents, ChargeStatus, FtRecord, Id, Reason, SuggestionView } from "@/lib/api";
import { date, money } from "@/lib/format";
import { BucketBadge } from "../BucketBadge";
import type { OnWrite } from "../thread/useThreadActions";
import { AcceptReason, DecideWaiting, OfferedNote, ReopenReason, SnoozeCharge } from "./actions";
import { field } from "./labels";
import { Disclosure, TrailGroup, TrailNode, TrailNote, type Mark } from "./Trail";
import styles from "./charge.module.css";

const BUCKET_MARKS: Record<Bucket, Mark> = {
  possible_conflict: "conflict",
  needs_human: "human",
  missing_evidence: "missing",
  evidence_complete: "holds",
};

function reasonKey(r: Reason): string {
  return `${r.check}:${r.problem}`;
}

/** The check code gives a reason that shows one of the agent's suggestions waiting for the accountant. */
const SUGGESTION_CHECK = "suggestion";

/**
 * The waiting record a reason shows, to decide on the reason's row: one the
 * server lists as waiting on this charge (`decideHere`) and that the reason
 * names. Undefined for any other reason.
 */
function waitingOn(r: Reason, decideHere: SuggestionView[]): Id | undefined {
  if (r.check !== SUGGESTION_CHECK || r.accepted_by) return undefined;
  return decideHere.find((w) => (r.record_ids ?? []).includes(w.record.id))?.record.id;
}

/**
 * What accepted a reason, and whether it can be reopened here. Only a one-off
 * acceptance on this charge is reopened from the charge: a reusable note
 * covers other charges too, and is withdrawn from the grant page. When the
 * accountant has just accepted it here (`justAccepted`), focus moves to this
 * result, so it is what they see and hear next.
 */
function AcceptedBy({
  chargeId,
  reason,
  records,
  onWrite,
  justAccepted = false,
}: {
  chargeId: Id;
  reason: Reason;
  records: Record<Id, FtRecord>;
  onWrite?: OnWrite;
  justAccepted?: boolean;
}) {
  const result = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (justAccepted) result.current?.focus();
  }, [justAccepted]);
  const accepted = reason.accepted_by ? records[reason.accepted_by] : undefined;
  const ownOneOff =
    accepted?.data.kind === "accepted_reason" && field<Id>(accepted, "charge_id") === chargeId && !field<boolean>(accepted, "reusable");
  const note = accepted ? field<string>(accepted, "note") : undefined;
  return (
    <div ref={result} tabIndex={-1} className={styles.result} data-testid="accepted-result">
      {note && (
        <p className="ft-caption">
          {field<boolean>(accepted, "reusable") || field<Id>(accepted, "charge_id") !== chargeId ? "Under your reusable note: " : "Your note: "}
          {note}
        </p>
      )}
      {accepted && ownOneOff && onWrite && <ReopenReason acceptedId={accepted.id} onWrite={onWrite} />}
    </div>
  );
}

/**
 * Why the charge is in its bucket, as the end of the evidence trail: every
 * failing reason in the server's order and words, each a break in the trail
 * with its detail open; Snooze for the whole charge on its own row after
 * them; then the reasons that pass, closed to one line that opens in place.
 * The screen builds no status text of its own. With `onWrite`, each failing
 * reason can be accepted with a note, and the charge can be snoozed. A
 * reason that shows one of the agent's records waiting in `decideHere` also
 * offers Confirm and Reject for that record.
 */
export function StatusReasons({
  status,
  chargeId,
  chargedCents,
  records = {},
  decideHere = [],
  onWrite,
}: {
  status: ChargeStatus | null;
  chargeId?: Id;
  /** The charge's amount, to set beside an amount code expected (ruling 61). */
  chargedCents?: Cents;
  records?: Record<Id, FtRecord>;
  /** The agent's records waiting on this charge that nothing else on the page offers to decide. */
  decideHere?: SuggestionView[];
  onWrite?: OnWrite;
}) {
  const reasons = status?.reasons ?? [];
  const openKeys = reasons.filter((r) => r.bucket !== "evidence_complete" && !r.accepted_by).map(reasonKey);
  // The reasons accepted since the last render: their result takes focus.
  const [lastOpen, setLastOpen] = useState(openKeys);
  const [justAccepted, setJustAccepted] = useState<string[]>([]);
  if (openKeys.join("|") !== lastOpen.join("|")) {
    const acceptedNow = reasons.filter((r) => r.accepted_by).map(reasonKey);
    setJustAccepted(lastOpen.filter((k) => acceptedNow.includes(k)));
    setLastOpen(openKeys);
  }

  if (!status) {
    return (
      <TrailGroup label="Reasons">
        <TrailNote>The checks haven&apos;t run on this charge yet.</TrailNote>
      </TrailGroup>
    );
  }
  const failing = status.reasons.filter((r) => r.bucket !== "evidence_complete");
  const passing = status.reasons.filter((r) => r.bucket === "evidence_complete");
  const id = chargeId ?? status.charge_id;
  const open = failing.filter((r) => !r.accepted_by);
  return (
    <>
      {failing.length > 0 && (
        <TrailGroup label="Reasons">
          {failing.map((r) => {
            const waiting = waitingOn(r, decideHere);
            const hasDetail = (r.expected_cents != null && chargedCents !== undefined) || r.expected_by || r.accepted_by || onWrite;
            return (
              <TrailNode
                key={reasonKey(r)}
                testId="reason"
                mark={BUCKET_MARKS[r.bucket]}
                broken
                open={!r.accepted_by}
                title={<span className={styles.reasonText}>{r.text}</span>}
                status={
                  <>
                    {r.accepted_by && <span className="ft-tag ft-tag--accepted">Accepted</span>}
                    <BucketBadge bucket={r.bucket} />
                  </>
                }
              >
                {hasDetail ? (
                  <>
                    {r.expected_cents != null && chargedCents !== undefined && (
                      <p className="ft-caption ft-num">
                        Expected {money(r.expected_cents)} · charged {money(chargedCents)}
                      </p>
                    )}
                    {r.expected_by && <p className="ft-caption">Expected by {date(r.expected_by)}</p>}
                    {r.accepted_by && (
                      <AcceptedBy chargeId={id} reason={r} records={records} onWrite={onWrite} justAccepted={justAccepted.includes(reasonKey(r))} />
                    )}
                    {!r.accepted_by && onWrite && r.offered_note_id && (
                      <OfferedNote chargeId={id} reason={r} note={records[r.offered_note_id] ?? null} onWrite={onWrite} />
                    )}
                    {onWrite && waiting && <DecideWaiting recordId={waiting} onWrite={onWrite} />}
                    {!r.accepted_by && onWrite && <AcceptReason chargeId={id} reason={r} onWrite={onWrite} />}
                  </>
                ) : null}
              </TrailNode>
            );
          })}
        </TrailGroup>
      )}
      {onWrite && open.length > 0 && (
        <div className={styles.chargeActions} data-testid="charge-actions">
          <SnoozeCharge chargeId={id} reasons={open} onWrite={onWrite} />
        </div>
      )}
      {passing.length > 0 && (
        <Disclosure label="Passing" count={passing.length} testId="passing">
          <ul className={styles.passes} aria-label="Reasons that pass">
            {passing.map((r) => (
              <li key={reasonKey(r)} data-bucket={r.bucket}>
                <span className={styles.passMark} aria-hidden="true" />
                <span className="ft-sr">Passes: </span>
                <span>{r.text}</span>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
    </>
  );
}
