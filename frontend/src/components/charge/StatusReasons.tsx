import type { Cents, ChargeStatus, FtRecord, Id, Reason } from "@/lib/api";
import { date, money } from "@/lib/format";
import { BucketBadge } from "../BucketBadge";
import type { OnWrite } from "../thread/useThreadActions";
import { AcceptReason, OfferedNote, ReopenReason, SnoozeCharge } from "./actions";
import { field } from "./labels";
import styles from "./charge.module.css";

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
 * Why the charge is in its bucket: every reason in the server's order and
 * words, the failing ones first as the server lists them, then the checks that
 * pass. The screen builds no status text of its own. With `onWrite`, each
 * failing reason can be accepted with a note, and the charge can be snoozed.
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
  if (!status) return <p className="ft-empty">The checks haven&apos;t run on this charge yet.</p>;
  const failing = status.reasons.filter((r) => r.bucket !== "evidence_complete");
  const passing = status.reasons.filter((r) => r.bucket === "evidence_complete");
  const id = chargeId ?? status.charge_id;
  const open = failing.filter((r) => !r.accepted_by);
  return (
    <>
      <ul className={styles.list} aria-label="Reasons">
        {failing.map((r) => (
          <li key={`${r.check}:${r.problem}`} className={styles.row} data-bucket={r.bucket}>
            <p className={styles.line}>
              <BucketBadge bucket={r.bucket} />
              <span>{r.text}</span>
            </p>
            {r.expected_cents != null && chargedCents !== undefined && (
              <p className="ft-caption">
                Expected {money(r.expected_cents)} · charged {money(chargedCents)}
              </p>
            )}
            {(r.expected_by || r.accepted_by) && (
              <p className="ft-caption">
                {r.expected_by && <>Expected by {date(r.expected_by)}</>}
                {r.accepted_by && (
                  <>
                    {r.expected_by && " · "}
                    <span className="ft-tag ft-tag--accepted">Accepted</span>
                  </>
                )}
              </p>
            )}
            {r.accepted_by && <AcceptedBy chargeId={id} reason={r} records={records} onWrite={onWrite} />}
            {!r.accepted_by && onWrite && r.offered_note_id && (
              <OfferedNote chargeId={id} reason={r} note={records[r.offered_note_id] ?? null} onWrite={onWrite} />
            )}
            {!r.accepted_by && onWrite && <AcceptReason chargeId={id} reason={r} onWrite={onWrite} />}
          </li>
        ))}
        {passing.map((r) => (
          <li key={`${r.check}:${r.problem}`} className={styles.row} data-bucket={r.bucket}>
            <p className={styles.line}>
              <span className="ft-tag">Passes</span>
              <span>{r.text}</span>
            </p>
          </li>
        ))}
      </ul>
      {onWrite && open.length > 0 && (
        <div className={styles.toolbar}>
          <SnoozeCharge chargeId={id} reasons={open} onWrite={onWrite} />
        </div>
      )}
    </>
  );
}
