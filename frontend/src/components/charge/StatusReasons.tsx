import type { ChargeStatus } from "@/lib/api";
import { date } from "@/lib/format";
import { BucketBadge } from "../BucketBadge";
import styles from "./charge.module.css";

/**
 * Why the charge is in its bucket: every reason in the server's order and
 * words, the failing ones first as the server lists them, then the checks that
 * pass. The screen builds no status text of its own.
 */
export function StatusReasons({ status }: { status: ChargeStatus | null }) {
  if (!status) return <p className="ft-empty">The checks haven&apos;t run on this charge yet.</p>;
  const failing = status.reasons.filter((r) => r.bucket !== "evidence_complete");
  const passing = status.reasons.filter((r) => r.bucket === "evidence_complete");
  return (
    <ul className={styles.list} aria-label="Reasons">
      {failing.map((r) => (
        <li key={`${r.check}:${r.problem}`} className={styles.row} data-bucket={r.bucket}>
          <p className={styles.line}>
            <BucketBadge bucket={r.bucket} />
            <span>{r.text}</span>
          </p>
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
  );
}
