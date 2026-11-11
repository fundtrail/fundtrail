import Link from "next/link";
import type { ChecklistEntry, EvidenceFile, FtRecord, Id, LinkView, SuggestionView } from "@/lib/api";
import { routes } from "@/lib/routes";
import { date, money } from "@/lib/format";
import { SuggestionBox } from "../thread/Decide";
import { changeFor } from "../thread/describe";
import type { OnWrite } from "../thread/useThreadActions";
import { AddChecklistItem, RemoveChecklistItem } from "./actions";
import { addedByLabel, recordName } from "./labels";
import styles from "./charge.module.css";

/**
 * Ruling 61: an item code fills by recalculating, such as a benefit charge's
 * rate times its salary lines. It has no links: it shows the rate term and the
 * salary lines it used.
 */
function Recalculated({ entry, records, grantId }: { entry: ChecklistEntry; records: Record<Id, FtRecord>; grantId?: Id }) {
  const rate = entry.rate_id ? records[entry.rate_id] : undefined;
  const rateName = rate?.data.kind === "rate" ? `${rate.data.name.value} (${rate.data.rate.value})` : "the rate term";
  const lines = entry.charge_ids ?? [];
  return (
    <p className="ft-caption">
      Recalculated from{" "}
      {entry.rate_id && grantId ? (
        <Link className="ft-link" href={routes.record(grantId, entry.rate_id)}>
          {rateName}
        </Link>
      ) : (
        rateName
      )}
      {lines.length > 0 && (
        <>
          {" "}
          on {lines.length} salary {lines.length === 1 ? "line" : "lines"}:{" "}
          {lines.map((id, i) => (
            <span key={id}>
              {i > 0 && ", "}
              {grantId ? (
                <Link className="ft-link" href={routes.charge(grantId, id)}>
                  salary line {i + 1}
                </Link>
              ) : (
                `salary line ${i + 1}`
              )}
            </span>
          ))}
        </>
      )}
    </p>
  );
}

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
  grantId,
  onWrite,
}: {
  checklist: ChecklistEntry[];
  links: LinkView[];
  waiting: SuggestionView[];
  records: Record<Id, FtRecord>;
  files: Record<Id, EvidenceFile>;
  chargeId?: Id;
  /** For linking a recalculation's rate term and salary lines. */
  grantId?: Id;
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
            {(entry.rate_id || (entry.charge_ids ?? []).length > 0) && (
              <Recalculated entry={entry} records={records} grantId={grantId} />
            )}
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
