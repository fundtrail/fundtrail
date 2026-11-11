import Link from "next/link";
import type { ChecklistEntry, EvidenceFile, FtRecord, Id, LinkView, SuggestionView } from "@/lib/api";
import { routes } from "@/lib/routes";
import { date, money, percent } from "@/lib/format";
import { SuggestionBox } from "../thread/Decide";
import { changeFor } from "../thread/describe";
import type { OnWrite } from "../thread/useThreadActions";
import { AddChecklistItem, RemoveChecklistItem } from "./actions";
import { addedByLabel, recordName } from "./labels";
import { TrailGroup, TrailNode } from "./Trail";
import styles from "./charge.module.css";

/**
 * Ruling 61: an item code fills by recalculating, such as a benefit charge's
 * rate times its salary lines. It has no links: it shows the rate term and the
 * salary lines it used.
 */
function Recalculated({ entry, records, grantId }: { entry: ChecklistEntry; records: Record<Id, FtRecord>; grantId?: Id }) {
  const rate = entry.rate_id ? records[entry.rate_id] : undefined;
  // A benefit rate is a fraction (records.py, CitedDecimal): shown as a percentage.
  const rateName = rate?.data.kind === "rate" ? `${rate.data.name.value} (${percent(rate.data.rate.value)})` : "the rate term";
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
      <div className={styles.addItem}>
        <AddChecklistItem chargeId={chargeId} onWrite={onWrite} />
      </div>
    ) : null;
  if (checklist.length === 0) {
    return (
      <>
        <p className={styles.empty}>No items on the checklist yet.</p>
        {add}
      </>
    );
  }
  const ctx = { records, files, checklist };
  return (
    <>
      <ul className={styles.items} aria-label="Evidence checklist">
        {checklist.map((entry) => {
          const fillers = links.filter((l) => (entry.link_ids ?? []).includes(l.link.id));
          const removal = entry.removal_waiting_id ? waiting.find((w) => w.record.id === entry.removal_waiting_id) : undefined;
          const partly = partlyFilledText(entry);
          return (
            <li key={entryKey(entry)} className={styles.item} data-filled={entry.filled} data-partly={partly ? true : undefined}>
              <span className={`${styles.mark} ${entry.filled ? styles.filled : partly ? styles.partly : styles.missing}`} aria-hidden="true" />
              <div className={styles.itemBody}>
                <p className={styles.itemHead}>
                  <span className={styles.label}>{entry.needed}</span>
                  <span className={styles.itemSide}>
                    {entry.amount_cents !== null && entry.amount_cents !== undefined && (
                      <span className="ft-num">{money(entry.amount_cents)}</span>
                    )}
                    <span className={styles.itemState} data-filled={entry.filled} data-partly={partly ? true : undefined}>
                      {entry.filled ? "Filled" : (partly ?? "Missing")}
                    </span>
                  </span>
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
                {fillers.length > 0 && <p className="ft-caption">Filled by {fillers.map((l) => recordName(l.record, files)).join(", ")}</p>}
                {entry.removal_waiting_id && !removal && <p className={styles.waitingWord}>Removal waiting for you</p>}
                {removal && (
                  <SuggestionBox
                    record={removal.record}
                    change={changeFor(removal, removal.record, removal.replaces ?? null, ctx)}
                    state="waiting"
                    note="Accept or reject it in the review thread."
                  />
                )}
                {chargeId && onWrite && <RemoveChecklistItem chargeId={chargeId} entry={entry} onWrite={onWrite} />}
              </div>
            </li>
          );
        })}
      </ul>
      {add}
    </>
  );
}

/**
 * The checklist items still missing, as nodes on the evidence trail: each a
 * dashed ring where the evidence should be, in the checklist's own words. An
 * item the server says is partly filled gets the half-filled ring and the
 * server's words for it instead; it is still not filled, so the trail stays
 * dashed from it.
 */
export function MissingItems({ checklist }: { checklist: ChecklistEntry[] }) {
  const missing = checklist.filter((e) => !e.filled);
  if (missing.length === 0) return null;
  return (
    <TrailGroup label="Missing from the checklist">
      {missing.map((entry) => {
        const partly = partlyFilledText(entry);
        return (
          <TrailNode
            key={entryKey(entry)}
            testId="missing-item"
            mark={partly ? "partly" : "missing"}
            broken
            title={<span className={styles.label}>{entry.needed}</span>}
            status={partly ?? "Missing"}
          />
        );
      })}
    </TrailGroup>
  );
}

/**
 * The server's words for an item that is partly filled (ruling 73), or null.
 * Only an item that isn't filled can be partly filled; the screen works out
 * nothing from `covered_cents`.
 */
function partlyFilledText(entry: ChecklistEntry): string | null {
  return !entry.filled && entry.partly_filled_text ? entry.partly_filled_text : null;
}
