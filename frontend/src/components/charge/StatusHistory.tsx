import Link from "next/link";
import type { Bucket, Charge, EvidenceFile, FtRecord, HistoryEntry, Id } from "@/lib/api";
import { date, recordKindLabel } from "@/lib/format";
import { BucketBadge } from "../BucketBadge";
import styles from "./charge.module.css";

function bucketOf(entry: HistoryEntry | undefined): Bucket | null {
  if (!entry) return null;
  const status = entry.entry.status as { bucket?: Bucket };
  return status.bucket ?? null;
}

/** What triggered a change, named by what the body carries for it. */
function triggerName(entry: HistoryEntry, records: Record<Id, FtRecord>, files: Record<Id, EvidenceFile>, charges: Record<Id, Charge>): string | null {
  const { kind, id } = entry.entry.trigger;
  if (!id) return null;
  switch (kind) {
    case "file":
      return files[id]?.name ?? null;
    case "record":
      return records[id] ? recordKindLabel(records[id].data.kind) : null;
    case "charge":
      return charges[id]?.ledger_line_id ?? null;
    default:
      return null;
  }
}

/**
 * Every change to the charge's status, oldest first as the server sends it:
 * when, what triggered it in the server's words, and the bucket before and after.
 */
export function StatusHistory({
  history,
  records,
  files,
  charges,
  fileHref,
}: {
  history: HistoryEntry[];
  records: Record<Id, FtRecord>;
  files: Record<Id, EvidenceFile>;
  charges: Record<Id, Charge>;
  fileHref?: (fileId: Id) => string | undefined;
}) {
  if (history.length === 0) return <p className="ft-empty">No status changes yet.</p>;
  return (
    <ol className={styles.list} aria-label="Status history">
      {history.map((entry, i) => {
        const before = bucketOf(history[i - 1]);
        const after = bucketOf(entry);
        const name = triggerName(entry, records, files, charges);
        const href = entry.entry.trigger.kind === "file" && entry.entry.trigger.id ? fileHref?.(entry.entry.trigger.id) : undefined;
        return (
          <li key={`${entry.entry.changed_at}:${i}`} className={styles.row}>
            <p className={styles.line}>
              <span className="ft-num">{date(entry.entry.changed_at)}</span>
              <span>· {entry.text}</span>
              {name &&
                (href ? (
                  <Link className="ft-link" href={href}>
                    {name}
                  </Link>
                ) : (
                  <span className="ft-caption">{name}</span>
                ))}
            </p>
            {after && (
              <p className={styles.line}>
                {before && before !== after && (
                  <>
                    <BucketBadge bucket={before} />
                    <span aria-label="to">→</span>
                  </>
                )}
                <BucketBadge bucket={after} />
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
