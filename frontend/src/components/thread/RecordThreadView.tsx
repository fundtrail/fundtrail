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
}) {
  const fileId = record ? citationFileId(record) : (status?.file_id ?? null);
  const file = fileId ? files[fileId] : undefined;
  const name = record ? recordKindLabel(record.data.kind) : "Record";
  const records: Record<Id, FtRecord> = record ? { [record.id]: record } : {};
  for (const entry of thread.entries) if (entry.kind === "record") records[entry.record.id] = entry.record;
  return (
    <>
      <header className="ft-panel ft-grant-head">
        <div>
          <p className="ft-caption">
            <span className="ft-id">{recordId}</span>
            {record && <> · Written by {record.author === "agent" ? "the agent" : "the accountant"}, {date(record.written_at)}</>}
          </p>
          <h1 className="ft-title">{name}</h1>
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
        </div>
        {state && <span className="ft-tag">{STATE_LABELS[state]}</span>}
      </header>
      {status && status.problems.length > 0 && (
        <section className="ft-panel" aria-labelledby="record-problems-heading">
          <div className="ft-panel__head">
            <h2 id="record-problems-heading" className="ft-heading">
              Problems
            </h2>
          </div>
          <ul className={styles.reasons}>
            {status.problems.map((p) => (
              <li key={`${p.check}:${p.problem}`}>{p.text}</li>
            ))}
          </ul>
        </section>
      )}
      <section className="ft-panel" aria-labelledby="record-thread-heading">
        <div className="ft-panel__head">
          <h2 id="record-thread-heading" className="ft-heading">
            Review thread
          </h2>
        </div>
        <div className={styles.padded}>
          <ReviewThread
            thread={thread}
            about="this record"
            ctx={{ records, files, checklist: [], reasons: [], waiting: [], quoteHref }}
            onDecide={onDecide}
            onAsk={onAsk}
          />
        </div>
      </section>
    </>
  );
}
