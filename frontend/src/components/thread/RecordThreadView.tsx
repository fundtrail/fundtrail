import Link from "next/link";
import type { Citation, EvidenceFile, FtRecord, Id, RecordState, RecordStatus, Thread } from "@/lib/api";
import { date, recordKindLabel } from "@/lib/format";
import { citationFileId } from "../charge/labels";
import type { OnDecide } from "./Decide";
import { ReviewThread } from "./ReviewThread";
import styles from "./thread.module.css";

const STATE_LABELS: Record<RecordState, string> = {
  counts: "In effect",
  waiting: "Waiting for the accountant",
  rejected: "Rejected",
  replaced: "Replaced",
  retracted: "Withdrawn",
};

/**
 * A record's thread: the record, its own problems in the server's words, and
 * the same thread a charge has.
 */
export function RecordThreadView({
  recordId,
  record,
  state,
  status,
  files,
  thread,
  fileHref,
  quoteHref,
  onDecide,
  onAsk,
  headingLevel = 1,
  pageHref,
}: {
  recordId: Id;
  record: FtRecord | null;
  state: RecordState | null;
  status: RecordStatus | null;
  files: Record<Id, EvidenceFile>;
  thread: Thread;
  fileHref?: (fileId: Id) => string;
  quoteHref?: (citation: Citation) => string | undefined;
  onDecide: OnDecide;
  onAsk: (text: string) => Promise<void>;
  /** The record's title: h1 on its own page, h2 inside another page. The look is the class's. */
  headingLevel?: 1 | 2;
  /** The record's own page, linked from the header's top row when another page shows the record. */
  pageHref?: string;
}) {
  const Title = headingLevel === 2 ? "h2" : "h1";
  const fileId = record ? citationFileId(record) : (status?.file_id ?? null);
  const file = fileId ? files[fileId] : undefined;
  const name = record ? recordKindLabel(record.data.kind) : "Record";
  const records: Record<Id, FtRecord> = record ? { [record.id]: record } : {};
  for (const entry of thread.entries) if (entry.kind === "record") records[entry.record.id] = entry.record;
  return (
    <div className={styles.recordView}>
      <div className={styles.recordCard}>
        <header className={styles.recordHead}>
          {(state || pageHref) && (
            <div className={styles.recordTop}>
              {state && (
                <span className={styles.recordState} data-state={state}>
                  {STATE_LABELS[state]}
                </span>
              )}
              {pageHref && (
                <Link className={`ft-link ${styles.pageLink}`} href={pageHref}>
                  Open on its own page
                </Link>
              )}
            </div>
          )}
          <p className="ft-caption">
            <span className="ft-id">{recordId}</span>
            {record && <> · Written by {record.author === "agent" ? "the agent" : "the accountant"}, {date(record.written_at)}</>}
          </p>
          <Title className={styles.recordName}>{name}</Title>
          {file && (
            <p className="ft-caption">
              From{" "}
              {fileHref ? (
                <Link className="ft-link" href={fileHref(file.id)}>
                  {file.name}
                </Link>
              ) : (
                file.name
              )}
            </p>
          )}
        </header>
        {status && status.problems.length > 0 && (
          <section aria-labelledby="record-problems-heading">
            <h2 id="record-problems-heading" className={styles.sectionHeading}>
              Problems
            </h2>
            <ul className={styles.problems}>
              {status.problems.map((p) => (
                <li key={`${p.check}:${p.problem}`}>{p.text}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
      <section className={styles.recordDock} aria-labelledby="record-thread-heading">
        <h2 id="record-thread-heading" className={`${styles.sectionHeading} ${styles.dockHeading}`}>
          Review thread
        </h2>
        <ReviewThread
          thread={thread}
          about="this record"
          ctx={{ records, files, checklist: [], reasons: [], waiting: [], quoteHref }}
          onDecide={onDecide}
          onAsk={onAsk}
        />
      </section>
    </div>
  );
}
