import type { Bucket, BudgetView, GrantSummary, IsoDate } from "@/lib/api";
import Link from "next/link";
import { BUCKET_LABELS, date, FUNDER_LABELS, money } from "@/lib/format";
import { routes } from "@/lib/routes";
import { grantName } from "./GrantList";
import styles from "./GrantHeader.module.css";

const BAR_ORDER: Bucket[] = ["possible_conflict", "needs_human", "missing_evidence", "evidence_complete"];

/** Milliseconds since the epoch of a date the server sent. Never the browser's clock. */
function at(value: string): number {
  return new Date(value.length === 10 ? `${value}T00:00:00Z` : value).getTime();
}

/**
 * The grant's period drawn as a trail: its start, today on the grant's own
 * clock (decision 0028) and its end date in force. Every date is the server's;
 * the screen only places them along the line.
 */
function Period({ start, now, end }: { start: IsoDate; now: string; end: IsoDate }) {
  const from = at(start);
  const to = at(end);
  const today = at(now);
  if (!(to > from) || Number.isNaN(today)) return null;
  const share = Math.min(1, Math.max(0, (today - from) / (to - from)));
  const pct = `${(share * 100).toFixed(2)}%`;
  const edge = share < 0.15 ? "start" : share > 0.85 ? "end" : undefined;
  return (
    <div className={styles.span} role="group" aria-label="The grant's period" data-edge={edge}>
      <div className={styles.line} aria-hidden="true" />
      <div className={styles.done} style={{ width: pct }} aria-hidden="true" />
      <span className={`${styles.pt} ${styles.ptStart}`} aria-hidden="true" />
      <span className={`${styles.pt} ${styles.ptNow}`} style={{ left: `clamp(7px, ${pct}, calc(100% - 7px))` }} aria-hidden="true" />
      <span className={`${styles.pt} ${styles.ptEnd}`} aria-hidden="true" />
      <span className={`${styles.lb} ${styles.lbStart}`}>
        <b>Start</b> <span className="ft-num">{date(start)}</span>
      </span>
      <span className={`${styles.lb} ${styles.lbNow}`} style={{ left: pct }} data-edge={edge}>
        <b>Today</b> <span className="ft-num">{date(now)}</span>
      </span>
      <span className={`${styles.lb} ${styles.lbEnd}`}>
        <b>End date</b> <span className="ft-num">{date(end)}</span>
      </span>
    </div>
  );
}

/**
 * Where a grant stands, at the top of its pages: its name, readiness and dates.
 * Counts only, never a percentage. The readiness bar is sized by the server's
 * bucket counts. `start` is the confirmed period's start, when the page has
 * it, and `budget` gives the amounts charged and the award's limit.
 */
export function GrantHeader({ summary, start = null, budget = null }: { summary: GrantSummary; start?: IsoDate | null; budget?: BudgetView | null }) {
  const { grant } = summary;
  const counts = summary.bucket_counts;
  const segments = BAR_ORDER.filter((b) => (counts?.[b] ?? 0) > 0);
  const trail = start && summary.end_date ? <Period start={start} now={summary.now} end={summary.end_date} /> : null;
  return (
    <header className={styles.head}>
      <div className={styles.what}>
        <p className={styles.meta}>
          {grant.award_number && <span className="ft-id">{grant.award_number}</span>}
          <span>{FUNDER_LABELS[grant.funder ?? "NSF"] ?? grant.funder}</span>
          {budget && (
            <span className="ft-num">
              Charged {money(budget.spent_cents)}
              {budget.limit_cents != null && <> of the award&apos;s {money(budget.limit_cents)} limit</>}
            </span>
          )}
          {summary.next_closeout && (
            <span>
              {summary.next_closeout.label} <span className="ft-num">{date(summary.next_closeout.date)}</span>
            </span>
          )}
        </p>
        <h1 className={styles.title}>{grantName(summary)}</h1>
        <p className={styles.links}>
          <Link className="ft-link" href={routes.terms(grant.id)}>
            Grant terms
          </Link>
          <Link className="ft-link" href={routes.reusableNotes(grant.id)}>
            Reusable notes
          </Link>
          <Link className="ft-link" href={routes.ledger(grant.id)}>
            Ledger
          </Link>
        </p>
      </div>
      <div className={styles.ready}>
        <p>
          <span className={styles.count}>{summary.charges_ready}</span>
          <span className={styles.of}>of {summary.charges_total} charges ready for closeout</span>
        </p>
        {segments.length > 0 && (
          <>
            <div className={styles.bar} aria-hidden="true">
              {segments.map((b) => (
                <i key={b} data-bucket={b} style={{ flexGrow: counts[b] }} title={`${counts[b]} ${BUCKET_LABELS[b]}`} />
              ))}
            </div>
            <p className="ft-sr">{segments.map((b) => `${counts[b]} ${BUCKET_LABELS[b]}`).join(", ")}</p>
          </>
        )}
      </div>
      {trail ?? (
        <p className={`ft-caption ${styles.dates}`}>
          {start && (
            <>
              Start <span className="ft-num">{date(start)}</span>
              {" · "}
            </>
          )}
          {summary.end_date ? (
            <>
              Ends <span className="ft-num">{date(summary.end_date)}</span>
            </>
          ) : (
            <>End date not confirmed yet</>
          )}
        </p>
      )}
    </header>
  );
}
