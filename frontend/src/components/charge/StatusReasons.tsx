"use client";

import { useEffect, useRef, useState } from "react";
import type { Bucket, Cents, ChargeStatus, FtRecord, Id, Reason } from "@/lib/api";
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

/** A reason's name among the charge's reasons: its check and its problem. */
export function reasonKey(r: Reason): string {
  return `${r.check}:${r.problem}`;
}

/**
 * The check code gives a reason that shows one of the agent's suggestions
 * waiting for the accountant, and how it names that suggestion in the
 * reason's problem: "waiting:<record id>" (backend/app/checks/charge_checks.py).
 * Code writes this reason only while the record waits.
 */
const SUGGESTION_CHECK = "suggestion";
const WAITING_PREFIX = "waiting:";

/**
 * The waiting record a reason shows, to decide on the reason's row: the one
 * its problem names, when the reason also lists it and it's the agent's.
 * Undefined for any other reason, an accepted one, or a record the review
 * thread already offers to decide (`inThread`).
 */
function waitingOn(r: Reason, records: Record<Id, FtRecord>, inThread: readonly Id[]): Id | undefined {
  if (r.check !== SUGGESTION_CHECK || r.accepted_by || !r.problem.startsWith(WAITING_PREFIX)) return undefined;
  const id = r.problem.slice(WAITING_PREFIX.length);
  if (!id || !(r.record_ids ?? []).includes(id) || inThread.includes(id)) return undefined;
  const record = records[id];
  return record && record.author !== "agent" ? undefined : id;
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
 * One failing reason as a break in the trail, in the server's words: an open
 * one with its detail and its actions open, an accepted one closed to its
 * line with what accepted it.
 */
function ReasonNode({
  reason: r,
  chargeId: id,
  chargedCents,
  records,
  inThread,
  onWrite,
  justAccepted,
}: {
  reason: Reason;
  chargeId: Id;
  chargedCents?: Cents;
  records: Record<Id, FtRecord>;
  inThread: readonly Id[];
  onWrite?: OnWrite;
  justAccepted: boolean;
}) {
  const waiting = waitingOn(r, records, inThread);
  const hasDetail = (r.expected_cents != null && chargedCents !== undefined) || r.expected_by || r.accepted_by || onWrite;
  return (
    <TrailNode
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
          {r.accepted_by && <AcceptedBy chargeId={id} reason={r} records={records} onWrite={onWrite} justAccepted={justAccepted} />}
          {!r.accepted_by && onWrite && r.offered_note_id && (
            <OfferedNote chargeId={id} reason={r} note={records[r.offered_note_id] ?? null} onWrite={onWrite} />
          )}
          {onWrite && waiting && <DecideWaiting recordId={waiting} onWrite={onWrite} />}
          {!r.accepted_by && onWrite && <AcceptReason chargeId={id} reason={r} onWrite={onWrite} />}
        </>
      ) : null}
    </TrailNode>
  );
}

/**
 * Why the charge is in its bucket: every failing reason in the server's order
 * and words, each a break in the trail with its detail open; Snooze for the
 * whole charge on its own row after them; then the reasons that pass, closed
 * to one line that opens in place. The screen builds no status text of its
 * own. With `onWrite`, each failing reason can be accepted with a note, and
 * the charge can be snoozed. A reason that shows one of the agent's records
 * waiting also offers Confirm and Reject for that record, unless the review
 * thread offers them.
 *
 * The charge view leads with this, as what needs the accountant: it leaves
 * out the reasons it shows elsewhere (`leaveOut`, the ones already accepted
 * when the charge opened) and the passing line (`passing={false}`), which it
 * folds with the rest of the story.
 */
export function StatusReasons({
  status,
  chargeId,
  chargedCents,
  records = {},
  inThread = [],
  onWrite,
  leaveOut = [],
  passing: showPassing = true,
}: {
  status: ChargeStatus | null;
  chargeId?: Id;
  /** The charge's amount, to set beside an amount code expected (ruling 61). */
  chargedCents?: Cents;
  records?: Record<Id, FtRecord>;
  /** The agent's waiting records the review thread already offers to decide. */
  inThread?: readonly Id[];
  onWrite?: OnWrite;
  /** Reasons, by `reasonKey`, that another part of the page shows. */
  leaveOut?: readonly string[];
  /** Whether to end with the closed line of reasons that pass. */
  passing?: boolean;
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
  const failing = status.reasons.filter((r) => r.bucket !== "evidence_complete" && !leaveOut.includes(reasonKey(r)));
  const id = chargeId ?? status.charge_id;
  const open = status.reasons.filter((r) => r.bucket !== "evidence_complete" && !r.accepted_by);
  return (
    <>
      {failing.length > 0 && (
        <TrailGroup label="Reasons">
          {failing.map((r) => (
            <ReasonNode
              key={reasonKey(r)}
              reason={r}
              chargeId={id}
              chargedCents={chargedCents}
              records={records}
              inThread={inThread}
              onWrite={onWrite}
              justAccepted={justAccepted.includes(reasonKey(r))}
            />
          ))}
        </TrailGroup>
      )}
      {onWrite && open.length > 0 && (
        <div className={styles.chargeActions} data-testid="charge-actions">
          <SnoozeCharge chargeId={id} reasons={open} onWrite={onWrite} />
        </div>
      )}
      {showPassing && <PassingReasons status={status} />}
    </>
  );
}

/**
 * The failing reasons the accountant had already accepted when the charge
 * opened, by `reasonKey`, as closed breaks at the end of the evidence trail:
 * each opens to what accepted it, and a one-off acceptance can be reopened.
 */
export function AcceptedReasons({
  status,
  keys,
  chargeId,
  records = {},
  onWrite,
}: {
  status: ChargeStatus | null;
  keys: readonly string[];
  chargeId?: Id;
  records?: Record<Id, FtRecord>;
  onWrite?: OnWrite;
}) {
  const accepted = (status?.reasons ?? []).filter((r) => r.bucket !== "evidence_complete" && r.accepted_by && keys.includes(reasonKey(r)));
  if (!status || accepted.length === 0) return null;
  return (
    <TrailGroup label="Accepted reasons">
      {accepted.map((r) => (
        <ReasonNode
          key={reasonKey(r)}
          reason={r}
          chargeId={chargeId ?? status.charge_id}
          records={records}
          inThread={[]}
          onWrite={onWrite}
          justAccepted={false}
        />
      ))}
    </TrailGroup>
  );
}

/** The reasons that pass, closed to one line that opens in place. Nothing when none pass. */
export function PassingReasons({ status, remember }: { status: ChargeStatus | null; remember?: string }) {
  const passing = (status?.reasons ?? []).filter((r) => r.bucket === "evidence_complete");
  if (passing.length === 0) return null;
  return (
    <Disclosure label="Passing" count={passing.length} testId="passing" remember={remember}>
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
  );
}
