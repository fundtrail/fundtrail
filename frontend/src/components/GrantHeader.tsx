"use client";

import type { Bucket, GrantSummary } from "@/lib/api";
import Link from "next/link";
import { BUCKET_LABELS, date, FUNDER_LABELS } from "@/lib/format";
import { routes } from "@/lib/routes";
import { useGrantDisplayName } from "@/lib/grantName";
import styles from "./GrantHeader.module.css";

const BAR_ORDER: Bucket[] = ["evidence_complete", "possible_conflict", "needs_human", "missing_evidence"];

/**
 * Where a grant stands, at the top of its pages: its name, readiness and dates.
 * Counts only, never a percentage. The readiness bar is ready of total in one
 * color; the bucket counts are their own list beneath it. The dates are the
 * server's, as text: the end date in force and the grant's today.
 */
export function GrantHeader({ summary }: { summary: GrantSummary }) {
  const grantName = useGrantDisplayName();
  const { grant } = summary;
  const counts = summary.bucket_counts;
  const segments = BAR_ORDER.filter((b) => (counts?.[b] ?? 0) > 0);
  return (
    <header className={styles.head}>
      <div className={styles.what}>
        <p className={styles.meta}>
          {grant.award_number && <span className="ft-id">{grant.award_number}</span>}
          <span>{FUNDER_LABELS[grant.funder ?? "NSF"] ?? grant.funder}</span>
          {summary.next_closeout && (
            <span>
              {summary.next_closeout.label} <span className="ft-num">{date(summary.next_closeout.date)}</span>
            </span>
          )}
        </p>
        <h1 className={`ft-title ${styles.title}`}>{grantName(summary)}</h1>
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
        {summary.charges_total > 0 && (
          <div className={styles.bar} aria-hidden="true">
            <i style={{ width: `${Math.min(100, (summary.charges_ready / summary.charges_total) * 100).toFixed(1)}%` }} />
          </div>
        )}
        {/* The buckets, as the checks gave them: a list of its own, not parts of the bar. */}
        {segments.length > 0 && (
          <ul className={styles.buckets} aria-label="Charges by bucket">
            {segments.map((b) => (
              <li key={b} data-bucket={b}>
                <span className="ft-num">{counts[b]}</span> {BUCKET_LABELS[b]}
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className={`ft-caption ${styles.dates}`}>
        {summary.end_date ? (
          <>
            Ends <span className="ft-num">{date(summary.end_date)}</span>
          </>
        ) : (
          <>End date not confirmed yet</>
        )}
        {summary.now && (
          <>
            {" · "}Today <span className="ft-num">{date(summary.now)}</span>
          </>
        )}
      </p>
    </header>
  );
}
