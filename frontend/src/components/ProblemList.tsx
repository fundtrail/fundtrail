"use client";

import Link from "next/link";
import { useState, type MouseEvent, type ReactNode } from "react";
import type { Bucket, Cents, Charge, FtRecord, HeldMail, Id, ProblemRow, Reason } from "@/lib/api";
import { BUCKET_LABELS, date, HOLD_REASON_LABELS, money, recordKindLabel, SOURCE_LABELS, UNREADABLE_FROM_LABEL } from "@/lib/format";
import { routes } from "@/lib/routes";
import { ChargeStatusBadge } from "./BucketBadge";
import styles from "./ProblemList.module.css";

/**
 * Picks a row for the page to show. Returning false lets the row's link open
 * its own page instead (a page too narrow to show the item beside the list).
 * Absent, the rows only link to their pages.
 */
export type OnSelectRow = (key: string) => boolean | void;

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
    if (onSelect(selectKey) !== false) event.preventDefault();
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

/** How many of a row's reasons show: all of them, or the first with a count of the rest. */
export type ReasonsShown = "all" | "first";

/** The reasons a row shows, and how many more it has. */
function shownOf<T>(all: T[], reasons: ReasonsShown): { shown: T[]; more: number } {
  const shown = reasons === "first" ? all.slice(0, 1) : all;
  return { shown, more: all.length - shown.length };
}

function MoreReasons({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <p className="ft-caption">
      {count} more {count === 1 ? "reason" : "reasons"}
    </p>
  );
}

function Row({
  row,
  rowKey,
  charges,
  onSelect,
  selected,
  reasons,
}: {
  row: ProblemRow;
  rowKey: string;
  charges: Record<Id, Charge>;
  onSelect?: OnSelectRow;
  selected: boolean;
  reasons: ReasonsShown;
}) {
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
            <span className={`ft-tag ${styles.kind}`}>Grant</span>
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
            <span className={`ft-tag ${styles.kind}`}>Terms</span>
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
            {shownOf(row.status.problems, reasons).shown.map((p) => (
              <p className="ft-problem__text" key={`${p.check}:${p.problem}`}>
                {p.text}
              </p>
            ))}
            <MoreReasons count={shownOf(row.status.problems, reasons).more} />
          </div>
          <div className="ft-problem__side">
            <span className={`ft-tag ${styles.kind}`}>{row.file && !row.record ? "File" : "Record"}</span>
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
            {shownOf(failing(row.status.reasons), reasons).shown.map((r) => (
              <ReasonLine key={`${r.check}:${r.problem}`} reason={r} chargedCents={row.status.net_cents ?? row.charge.amount_cents} />
            ))}
            <MoreReasons count={shownOf(failing(row.status.reasons), reasons).more} />
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
            <span className={`ft-tag ${styles.kind}`}>Mail</span>
          </div>
        </>
      );
  }
}

const BUCKET_ORDER: Bucket[] = ["possible_conflict", "needs_human", "missing_evidence", "evidence_complete"];

/** Which rows show: all of them, or one bucket's. */
export type ProblemFilter = Bucket | "all";

/** How many rows the server sent in each bucket, in the buckets' order. Only charge rows have a bucket. */
function bucketCounts(rows: ProblemRow[]): Map<Bucket, number> {
  const counts = new Map<Bucket, number>();
  for (const b of BUCKET_ORDER) {
    const n = rows.filter((row) => rowBucket(row) === b).length;
    if (n > 0) counts.set(b, n);
  }
  return counts;
}

/**
 * The filter over the problem list: All, and one per bucket the rows are in,
 * each with its count of the rows the server sent. Shown only when a filter
 * would hide something. `look` draws it as tabs over the list or as pills in a
 * page's head.
 */
export function ProblemFilters({
  rows,
  value,
  onChange,
  look = "tabs",
}: {
  rows: ProblemRow[];
  value: ProblemFilter;
  onChange: (filter: ProblemFilter) => void;
  look?: "tabs" | "pills";
}) {
  const counts = bucketCounts(rows);
  if (![...counts.values()].some((n) => n < rows.length)) return null;
  const shown = value !== "all" && counts.has(value) ? value : "all";
  const cls = look === "pills" ? styles.pill : styles.tab;
  return (
    <div className={look === "pills" ? styles.pills : styles.tabs} role="group" aria-label="Show on the problem list">
      <button type="button" className={cls} aria-pressed={shown === "all"} onClick={() => onChange("all")}>
        All <span className={styles.tabCount}>{rows.length}</span>
      </button>
      {[...counts].map(([b, n]) => (
        <button key={b} type="button" className={cls} aria-pressed={shown === b} onClick={() => onChange(b)}>
          {BUCKET_LABELS[b]} <span className={styles.tabCount}>{n}</span>
        </button>
      ))}
    </div>
  );
}

/** The page a row opens on its own, or null for a grant problem, which has none. */
export function problemRowHref(row: ProblemRow): string | null {
  switch (row.kind) {
    case "grant":
      return null;
    case "terms_waiting":
      return routes.terms(row.file.grant_id);
    case "record":
      if (row.record) return routes.record(row.status.grant_id, row.record.id);
      return row.file ? routes.file(row.status.grant_id, row.file.id) : null;
    case "charge":
      return routes.charge(row.charge.grant_id, row.charge.id);
    case "held_mail":
      return routes.mail(row.held.workspace_id);
  }
}

/**
 * One problem in brief, for a page that shows a few: its name, the reason the
 * server lists first, and its amount with its bucket, or a neutral tag for
 * anything that isn't a charge. The whole row is one link to `href`.
 */
export function ProblemBrief({ row, href }: { row: ProblemRow; href: string }) {
  let name: ReactNode = null;
  let reason: ReactNode = null;
  let side: ReactNode = null;
  switch (row.kind) {
    case "grant":
      name = row.problem.text;
      side = <span className={`ft-tag ${styles.kind}`}>Grant</span>;
      break;
    case "terms_waiting":
      name = row.file.name;
      reason = <p className="ft-problem__text">{row.text}</p>;
      side = <span className={`ft-tag ${styles.kind}`}>Terms</span>;
      break;
    case "record": {
      name = row.file ? row.file.name : row.record ? recordName(row.record) : null;
      const first = row.status.problems[0];
      reason = first ? <p className="ft-problem__text">{first.text}</p> : null;
      side = <span className={`ft-tag ${styles.kind}`}>{row.file && !row.record ? "File" : "Record"}</span>;
      break;
    }
    case "charge": {
      name = row.charge.description;
      const first = failing(row.status.reasons)[0];
      reason = first ? <ReasonLine reason={first} chargedCents={row.status.net_cents ?? row.charge.amount_cents} /> : null;
      side = (
        <>
          <span className={`ft-amount ${styles.amount}`}>{money(row.charge.amount_cents)}</span>
          <ChargeStatusBadge status={row.status} />
        </>
      );
      break;
    }
    case "held_mail":
      name = row.held.subject || "No subject";
      reason = <p className="ft-problem__text">{heldSender(row.held) ? `${HOLD_REASON_LABELS[row.held.reason]} · ${heldSender(row.held)}` : UNREADABLE_FROM_LABEL}</p>;
      side = <span className={`ft-tag ${styles.kind}`}>Mail</span>;
      break;
  }
  return (
    <Link className={styles.brief} href={href} data-kind={row.kind}>
      <span className={styles.briefMain}>
        <span className={styles.briefName}>{name}</span>
        {reason}
      </span>
      <span className={styles.briefSide}>{side}</span>
    </Link>
  );
}

/**
 * The problem list, in the order the server sends it: grant problems, then
 * records, files and held mail, then charges by bucket, oldest first (answer
 * 1 of #22). Each row links to its page through routes.
 * The screen never sorts it. The filter only hides rows on screen.
 *
 * With `onSelect`, clicking a row picks it, for the page to show where it
 * likes; `selected` is the key of the picked row. With `reasons="first"` a
 * row shows only the reason the server lists first, with a count of the
 * rest; the item's own view shows them all. `variant="narrow"` lays each row
 * out for a column beside the picked item: name and amount, one reason line,
 * then the bucket. A page that puts the filter in its own head passes
 * `filter` and `onFilter` and turns the list's own tabs off with `tabs={false}`.
 */
export function ProblemList({
  rows,
  charges = {},
  selected = null,
  onSelect,
  reasons = "all",
  variant = "full",
  filter,
  onFilter,
  tabs = true,
}: {
  rows: ProblemRow[];
  charges?: Record<Id, Charge>;
  selected?: string | null;
  onSelect?: OnSelectRow;
  reasons?: ReasonsShown;
  variant?: "full" | "narrow";
  filter?: ProblemFilter;
  onFilter?: (filter: ProblemFilter) => void;
  tabs?: boolean;
}) {
  const [ownFilter, setOwnFilter] = useState<ProblemFilter>("all");
  if (rows.length === 0) {
    return <p className={`ft-empty ${styles.empty}`}>Nothing on the problem list.</p>;
  }
  const value = filter ?? ownFilter;
  const setFilter = onFilter ?? setOwnFilter;
  const counts = bucketCounts(rows);
  // A filter whose rows have all gone falls back to All.
  const shown = value !== "all" && counts.has(value) ? value : "all";

  function clickRow(event: MouseEvent<HTMLLIElement>, key: string) {
    if (!onSelect) return;
    // Links and buttons inside the row do their own thing.
    if ((event.target as HTMLElement).closest("a, button, input, label, summary")) return;
    // A page that can't show the item beside the list opens the row's own page.
    if (onSelect(key) === false) event.currentTarget.querySelector<HTMLAnchorElement>(".ft-problem__name a")?.click();
  }

  return (
    <div className={styles.list} data-variant={variant}>
      {tabs && <ProblemFilters rows={rows} value={shown} onChange={setFilter} />}
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
              <Row row={row} rowKey={key} charges={charges} onSelect={onSelect} selected={isSelected} reasons={reasons} />
            </li>
          );
        })}
      </ol>
    </div>
  );
}
