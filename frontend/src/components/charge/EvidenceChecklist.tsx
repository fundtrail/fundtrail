import type { ChecklistEntry, EvidenceFile, FtRecord, Id, LinkView, SuggestionView } from "@/lib/api";
import { date, money } from "@/lib/format";
import { SuggestionBox } from "../thread/Decide";
import { changeFor } from "../thread/describe";
import type { OnWrite } from "../thread/useThreadActions";
import { AddChecklistItem, RemoveChecklistItem } from "./actions";
import { addedByLabel, recordName } from "./labels";
import styles from "./charge.module.css";

function entryKey(entry: ChecklistEntry): string {
  return entry.item_record_id ?? `default:${entry.default_item}`;
}

/**
 * The charge's evidence checklist as code worked it out: each item filled or
 * missing, who added it, what fills it, and any removal the agent suggested,
 * waiting. Its Accept and Reject are in the review thread, the one place the
 * agent's suggestions are decided. With `onWrite`, the accountant adds and
 * removes items, which take effect right away.
 */
export function EvidenceChecklist({
  checklist,
  links,
  waiting,
  records,
  files,
  chargeId,
  onWrite,
}: {
  checklist: ChecklistEntry[];
  links: LinkView[];
  waiting: SuggestionView[];
  records: Record<Id, FtRecord>;
  files: Record<Id, EvidenceFile>;
  chargeId?: Id;
  onWrite?: OnWrite;
}) {
  const add =
    chargeId && onWrite ? (
      <div className={styles.toolbar}>
        <AddChecklistItem chargeId={chargeId} onWrite={onWrite} />
      </div>
    ) : null;
  if (checklist.length === 0) {
    return (
      <>
        <p className="ft-empty">No items on the checklist yet.</p>
        {add}
      </>
    );
  }
  const ctx = { records, files, checklist };
  return (
    <>
    <ul className={styles.list} aria-label="Evidence checklist">
      {checklist.map((entry) => {
        const fillers = links.filter((l) => (entry.link_ids ?? []).includes(l.link.id));
        const removal = entry.removal_waiting_id ? waiting.find((w) => w.record.id === entry.removal_waiting_id) : undefined;
        return (
          <li key={entryKey(entry)} className={styles.row} data-filled={entry.filled}>
            <p className={styles.line}>
              <span className={`${styles.mark} ${entry.filled ? styles.filled : styles.missing}`} aria-hidden="true" />
              <span className={styles.label}>{entry.needed}</span>
              {entry.amount_cents !== null && entry.amount_cents !== undefined && (
                <span className="ft-num">{money(entry.amount_cents)}</span>
              )}
              <span className="ft-tag">{entry.filled ? "Filled" : "Missing"}</span>
            </p>
            <p className="ft-caption">
              {addedByLabel(entry, records)}
              {entry.period && (
                <>
                  {" · "}For {date(entry.period.start)} to {date(entry.period.end)}
                </>
              )}
              {!entry.filled && entry.expected_by && <> · Expected by {date(entry.expected_by)}</>}
            </p>
            {fillers.length > 0 && (
              <p className="ft-caption">
                Filled by {fillers.map((l) => recordName(l.record, files)).join(", ")}
              </p>
            )}
            {entry.removal_waiting_id && !removal && <p className="ft-caption">Removal waiting for you</p>}
            {removal && (
              <SuggestionBox
                record={removal.record}
                change={changeFor(removal, removal.record, removal.replaces ?? null, ctx)}
                state="waiting"
                note="Accept or reject it in the review thread."
              />
            )}
            {chargeId && onWrite && <RemoveChecklistItem chargeId={chargeId} entry={entry} onWrite={onWrite} />}
          </li>
        );
      })}
    </ul>
    {add}
    </>
  );
}
