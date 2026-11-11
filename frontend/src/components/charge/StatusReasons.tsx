import type { Bucket, Cents, ChargeStatus, FtRecord, Id, Reason } from "@/lib/api";
import { date, money } from "@/lib/format";
import { BucketBadge } from "../BucketBadge";
import type { OnWrite } from "../thread/useThreadActions";
import { AcceptReason, OfferedNote, ReopenReason, SnoozeCharge } from "./actions";
import { field } from "./labels";
import { Disclosure, TrailGroup, TrailNode, TrailNote, type Mark } from "./Trail";
import styles from "./charge.module.css";

const BUCKET_MARKS: Record<Bucket, Mark> = {
  possible_conflict: "conflict",
  needs_human: "human",
  missing_evidence: "missing",
  evidence_complete: "holds",
};

/**
 * What accepted a reason, and whether it can be reopened here. Only a one-off
 * acceptance on this charge is reopened from the charge: a reusable note
 * covers other charges too, and is withdrawn from the grant page.
 */
function AcceptedBy({ chargeId, reason, records, onWrite }: { chargeId: Id; reason: Reason; records: Record<Id, FtRecord>; onWrite?: OnWrite }) {
  const accepted = reason.accepted_by ? records[reason.accepted_by] : undefined;
  const ownOneOff =
    accepted?.data.kind === "accepted_reason" && field<Id>(accepted, "charge_id") === chargeId && !field<boolean>(accepted, "reusable");
  const note = accepted ? field<string>(accepted, "note") : undefined;
  return (
    <>
      {note && (
        <p className="ft-caption">
          {field<boolean>(accepted, "reusable") || field<Id>(accepted, "charge_id") !== chargeId ? "Under your reusable note: " : "Your note: "}
          {note}
        </p>
      )}
      {accepted && ownOneOff && onWrite && <ReopenReason acceptedId={accepted.id} onWrite={onWrite} />}
    </>
  );
}

/**
 * Why the charge is in its bucket, as the end of the evidence trail: every
 * failing reason in the server's order and words, each a break in the trail
 * with its detail open, then the checks that pass, closed to one line that
 * opens in place. The screen builds no status text of its own. With
 * `onWrite`, each failing reason can be accepted with a note, and the charge
 * can be snoozed.
 */
export function StatusReasons({
  status,
  chargeId,
  chargedCents,
  records = {},
  onWrite,
}: {
  status: ChargeStatus | null;
  chargeId?: Id;
  /** The charge's amount, to set beside an amount code expected (ruling 61). */
  chargedCents?: Cents;
  records?: Record<Id, FtRecord>;
  onWrite?: OnWrite;
}) {
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
            const hasDetail = (r.expected_cents != null && chargedCents !== undefined) || r.expected_by || r.accepted_by || onWrite;
            // Snooze covers the whole charge: it sits with the last open reason's actions.
            const snoozeHere = onWrite && open.length > 0 && r === open[open.length - 1];
            return (
              <TrailNode
                key={`${r.check}:${r.problem}`}
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
                    {r.accepted_by && <AcceptedBy chargeId={id} reason={r} records={records} onWrite={onWrite} />}
                    {!r.accepted_by && onWrite && r.offered_note_id && (
                      <OfferedNote chargeId={id} reason={r} note={records[r.offered_note_id] ?? null} onWrite={onWrite} />
                    )}
                    {!r.accepted_by && onWrite && (
                      <div className={styles.reasonActions}>
                        <AcceptReason chargeId={id} reason={r} onWrite={onWrite} />
                        {snoozeHere && <SnoozeCharge chargeId={id} reasons={open} onWrite={onWrite} />}
                      </div>
                    )}
                  </>
                ) : null}
              </TrailNode>
            );
          })}
        </TrailGroup>
      )}
      {passing.length > 0 && (
        <Disclosure label={passing.length === 1 ? "1 check passes" : `${passing.length} checks pass`}>
          <ul className={styles.passes} aria-label="Checks that pass">
            {passing.map((r) => (
              <li key={`${r.check}:${r.problem}`} data-bucket={r.bucket}>
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
