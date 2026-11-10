import type { Bucket, ChargeStatus } from "@/lib/api";
import { BUCKET_LABELS } from "@/lib/format";

const CLASS: Record<Bucket, string> = {
  possible_conflict: "ft-badge--conflict",
  needs_human: "ft-badge--human",
  missing_evidence: "ft-badge--missing",
  evidence_complete: "ft-badge--complete",
};

/** A bucket as a word with its mark. Always the word: never a color or a mark alone. */
export function BucketBadge({ bucket }: { bucket: Bucket }) {
  return (
    <span className={`ft-badge ${CLASS[bucket]}`} data-bucket={bucket}>
      <span className="ft-badge__mark" aria-hidden="true" />
      {BUCKET_LABELS[bucket]}
    </span>
  );
}

/**
 * A charge's status as the checks gave it: its bucket, plus Rechecking and
 * Snoozed when the status says so. An accepted charge shows as Accepted first,
 * with the bucket the checks gave underneath (product.md, The problem list).
 * Null means the checks haven't run on it yet.
 */
export function ChargeStatusBadge({ status }: { status: ChargeStatus | null }) {
  if (!status) return <span className="ft-caption">Not checked yet</span>;
  const bucket = (
    <span className="ft-status">
      <BucketBadge bucket={status.bucket} />
      {status.rechecking && <span className="ft-tag ft-tag--rechecking">Rechecking</span>}
      {status.snoozed && <span className="ft-tag">Snoozed</span>}
    </span>
  );
  if (!status.accepted) return bucket;
  return (
    <span className="ft-status ft-status--accepted">
      <span className="ft-tag ft-tag--accepted">Accepted</span>
      {bucket}
    </span>
  );
}
