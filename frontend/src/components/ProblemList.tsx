"use client";

import Link from "next/link";
import { useState, type MouseEvent, type ReactNode } from "react";
import type { Bucket, Cents, Charge, FtRecord, HeldMail, Id, ProblemRow, Reason } from "@/lib/api";
import { BUCKET_LABELS, date, HOLD_REASON_LABELS, money, recordKindLabel, SOURCE_LABELS, UNREADABLE_FROM_LABEL } from "@/lib/format";
import { routes } from "@/lib/routes";
import { ChargeStatusBadge } from "./BucketBadge";
import styles from "./ProblemList.module.css";

/** Picks a row to show beside the list. Absent, the rows only link to their pages. */
export type OnSelectRow = (key: string) => void;

/** A reason's text as the server sends it, with when a missing item is expected and whether it was accepted. */
function ReasonLine({ reason, chargedCents }: { reason: Reason; chargedCents?: Cents }) {
  return (
    <p className="ft-problem__text">
      {reason.text}
      {reason.expected_cents != null && chargedCents !== undefined && (
        <span className="ft-caption">
          {" "}
          · Expected {money(reason.expected_cents)}, charged {money(chargedCents)}
        </span>
      )}
      {reason.expected_by && <span className="ft-caption"> · Expected by {date(reason.expected_by)}</span>}
      {reason.accepted_by && (
        <>
          {" "}
          <span className="ft-tag">Accepted</span>
        </>
      )}
    </p>
  );
}

/** A held message's sender, or null when its From line couldn't be read. */
function heldSender(held: HeldMail): string | null {
  return held.sender?.trim() || null;
}

/**
 * A row's link to its own page. With `onSelect`, a plain click shows the item
 * beside the list instead; a click with a modifier key, or the middle button,
 * still opens the page on its own.
 */
function RowLink({ href, selectKey, onSelect, current, children }: { href: string; selectKey: string; onSelect?: OnSelectRow; current?: boolean; children: ReactNode }) {
  function click(event: MouseEvent<HTMLAnchorElement>) {
    if (!onSelect || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    onSelect(selectKey);
  }
  return (
    <Link className="ft-link" href={href} onClick={click} aria-current={current ? "true" : undefined}>
      {children}
    </Link>
  );
}

/**
 * Ruling 62: the benefit charges that wait on this salary line, listed under it
 * instead of as rows of their own. Named from the charges list when it's loaded.
 */
function WaitingCharges({ grantId, ids, charges, onSelect }: { grantId: Id; ids: Id[]; charges: Record<Id, Charge>; onSelect?: OnSelectRow }) {
  return (
    <ul className="ft-problem__waiting" aria-label="Benefit charges waiting on this line">
      {ids.map((id, i) => {
        const c = charges[id];
        return (
          <li key={id} className="ft-caption">
            Waiting on this line:{" "}
            <RowLink href={routes.charge(grantId, id)} selectKey={`charge:${id}`} onSelect={onSelect}>
              {c ? `${c.ledger_line_id} · ${c.description}` : `Benefit charge ${i + 1}`}
            </RowLink>
            {c && <> · {money(c.amount_cents)}</>}
          </li>
        );
      })}
    </ul>
  );
}

function recordName(record: FtRecord): string {
  return `${recordKindLabel(record.data.kind)}, written ${date(record.written_at)}`;
}

/** The reasons a charge is on the list: every reason that isn't a pass, in the server's order and words. */
function failing(reasons: Reason[]): Reason[] {
  return reasons.filter((r) => r.bucket !== "evidence_complete");
}

/** A row's stable key, also the grant page's `item` search param when the row is shown beside the list. */
export function problemRowKey(row: ProblemRow, index: number): string {
  switch (row.kind) {
    case "grant":
      return `grant:${row.problem.check}:${row.problem.problem}`;
    case "terms_waiting":
      return `terms:${row.file.id}`;
    case "record":
      return `record:${row.status.record_id ?? row.status.file_id ?? index}`;
    case "charge":
      return `charge:${row.charge.id}`;
    case "held_mail":
      return `held_mail:${row.held.id}`;
  }
}

/** The bucket a row is in, as the server gave it: only charge rows have one. */
function rowBucket(row: ProblemRow): Bucket | null {
  return row.kind === "charge" ? row.status.bucket : null;
}

/** The mark at the start of a row: the bucket's shape on a charge, a plain square on everything else. */
function Mark({ bucket }: { bucket: Bucket | null }) {
  return <span className={styles.mark} data-bucket={bucket ?? "none"} aria-hidden="true" />;
}

function Row({ row, rowKey, charges, onSelect, selected }: { row: ProblemRow; rowKey: string; charges: Record<Id, Charge>; onSelect?: OnSelectRow; selected: boolean }) {
  const link = (href: string, children: ReactNode) => (
    <RowLink href={href} selectKey={rowKey} onSelect={onSelect} current={selected}>
      {children}
    </RowLink>
  );
  switch (row.kind) {
    case "grant":
      return (
        <>
          <Mark bucket={null} />
          <div className="ft-problem__main">
            <p className="ft-problem__text">{row.problem.text}</p>
          </div>
          <div className="ft-problem__side">
            <span className="ft-tag">Grant</span>
            {row.problem.accepted && <span className="ft-tag">Accepted</span>}
            {row.problem.snoozed && <span className="ft-tag">Snoozed</span>}
          </div>
        </>
      );
    case "terms_waiting":
      return (
        <>
          <Mark bucket={null} />
          <div className="ft-problem__main">
            <p className="ft-problem__name">{link(routes.terms(row.file.grant_id), row.file.name)}</p>
            <p className="ft-problem__text">{row.text}</p>
            <p className={`ft-caption ${styles.when}`}>
              {SOURCE_LABELS[row.file.source]} · <span className="ft-num">{date(row.file.arrived_at)}</span>
            </p>
          </div>
          <div className="ft-problem__side">
            <span className="ft-tag">Terms</span>
          </div>
        </>
      );
    case "record":
      return (
        <>
          <Mark bucket={null} />
          <div className="ft-problem__main">
            {row.record ? (
              <p className="ft-problem__name">{link(routes.record(row.status.grant_id, row.record.id), row.file ? row.file.name : recordName(row.record))}</p>
            ) : (
              row.file && <p className="ft-problem__name">{link(routes.file(row.status.grant_id, row.file.id), row.file.name)}</p>
            )}
            {row.status.problems.map((p) => (
              <p className="ft-problem__text" key={`${p.check}:${p.problem}`}>
                {p.text}
              </p>
            ))}
          </div>
          <div className="ft-problem__side">
            <span className="ft-tag">{row.file && !row.record ? "File" : "Record"}</span>
            {row.status.accepted && <span className="ft-tag">Accepted</span>}
            {row.status.snoozed && <span className="ft-tag">Snoozed</span>}
          </div>
        </>
      );
    case "charge":
      return (
        <>
          <Mark bucket={row.status.bucket} />
          <div className="ft-problem__main">
            <p className="ft-problem__name">{link(routes.charge(row.charge.grant_id, row.charge.id), row.charge.description)}</p>
            {failing(row.status.reasons).map((r) => (
              <ReasonLine key={`${r.check}:${r.problem}`} reason={r} chargedCents={row.status.net_cents ?? row.charge.amount_cents} />
            ))}
            <p className={`ft-caption ${styles.when}`}>
              <span className="ft-id">{row.charge.ledger_line_id}</span> · <span className="ft-num">{date(row.charge.transaction_date)}</span>
              {row.charge.vendor && <> · {row.charge.vendor}</>}
            </p>
            {(row.waiting_charge_ids ?? []).length > 0 && (
              <WaitingCharges grantId={row.charge.grant_id} ids={row.waiting_charge_ids ?? []} charges={charges} onSelect={onSelect} />
            )}
          </div>
          <div className="ft-problem__side">
            <span className={`ft-amount ${styles.amount}`}>{money(row.charge.amount_cents)}</span>
            <ChargeStatusBadge status={row.status} />
          </div>
        </>
      );
    case "held_mail":
      return (
        <>
          <Mark bucket={null} />
          <div className="ft-problem__main">
            <p className="ft-problem__name">{link(routes.mail(row.held.workspace_id), row.held.subject || "No subject")}</p>
            <p className="ft-problem__text">
              {heldSender(row.held) ? (
                <>
                  {HOLD_REASON_LABELS[row.held.reason]} · {heldSender(row.held)}
                </>
              ) : (
                UNREADABLE_FROM_LABEL
              )}
            </p>
            <p className={`ft-caption ${styles.when}`}>
              Gmail · <span className="ft-num">{date(row.held.held_at)}</span>
            </p>
          </div>
          <div className="ft-problem__side">
            <span className="ft-tag">Mail</span>
          </div>
        </>
      );
  }
}

const BUCKET_ORDER: Bucket[] = ["possible_conflict", "needs_human", "missing_evidence", "evidence_complete"];

/**
 * The problem list, in the order the server sends it: grant problems, then
 * records, files and held mail, then charges by bucket, oldest first (answer
 * 1 of #22). Each row links to its page through routes.
 * The screen never sorts it. The tabs only hide rows on screen: All, and one
 * per bucket the rows are in, counted from the rows the server sent.
 *
 * With `onSelect`, clicking a row shows it beside the list (the grant page);
 * `selected` is the key of the row shown there.
 */
export function ProblemList({
  rows,
  charges = {},
  selected = null,
  onSelect,
}: {
  rows: ProblemRow[];
  charges?: Record<Id, Charge>;
  selected?: string | null;
  onSelect?: OnSelectRow;
}) {
  const [tab, setTab] = useState<Bucket | "all">("all");
  if (rows.length === 0) {
    return <p className="ft-empty">Nothing on the problem list.</p>;
  }
  const counts = new Map<Bucket, number>();
  for (const row of rows) {
    const bucket = rowBucket(row);
    if (bucket) counts.set(bucket, (counts.get(bucket) ?? 0) + 1);
  }
  // Tabs only when one would hide something: a list of one bucket's rows needs no tabs.
  const tabs = [...counts.values()].some((n) => n < rows.length) ? BUCKET_ORDER.filter((b) => counts.has(b)) : [];
  // A tab whose rows have all gone falls back to All.
  const shown = tab !== "all" && counts.has(tab) ? tab : "all";

  function clickRow(event: MouseEvent<HTMLLIElement>, key: string) {
    if (!onSelect) return;
    // Links and buttons inside the row do their own thing.
    if ((event.target as HTMLElement).closest("a, button, input, label, summary")) return;
    onSelect(key);
  }

  return (
    <div className={styles.list}>
      {tabs.length > 0 && (
        <div className={styles.tabs} role="group" aria-label="Show on the problem list">
          <button type="button" className={styles.tab} aria-pressed={shown === "all"} onClick={() => setTab("all")}>
            All <span className={styles.tabCount}>{rows.length}</span>
          </button>
          {tabs.map((b) => (
            <button key={b} type="button" className={styles.tab} aria-pressed={shown === b} onClick={() => setTab(b)}>
              {BUCKET_LABELS[b]} <span className={styles.tabCount}>{counts.get(b)}</span>
            </button>
          ))}
        </div>
      )}
      <ol className="ft-problems" aria-label="Problem list">
        {rows.map((row, i) => {
          const key = problemRowKey(row, i);
          if (shown !== "all" && rowBucket(row) !== shown) return null;
          const isSelected = selected === key;
          return (
            <li
              className={`ft-problem ${styles.row}`}
              key={key}
              data-kind={row.kind}
              data-selected={isSelected || undefined}
              data-selectable={onSelect ? "" : undefined}
              onClick={(e) => clickRow(e, key)}
            >
              <Row row={row} rowKey={key} charges={charges} onSelect={onSelect} selected={isSelected} />
            </li>
          );
        })}
      </ol>
    </div>
  );
}
