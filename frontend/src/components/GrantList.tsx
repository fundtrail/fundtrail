import Link from "next/link";
import type { Bucket, GrantSummary } from "@/lib/api";
import { date } from "@/lib/format";
import { grantDisplayName, useGrantDisplayName } from "@/lib/grantName";
import { routes } from "@/lib/routes";
import styles from "./GrantList.module.css";

/**
 * A grant's name, without the sample choices: "Untitled grant" until the award
 * letter is read. Screens that can should use useGrantDisplayName (lib/grantName),
 * which names a sample grant by its sample.
 */
export function grantName(summary: GrantSummary): string {
  return grantDisplayName(summary);
}

/** The bar's segments, in bucket order: the most serious first. */
const SEGMENTS: [Bucket, string][] = [
  ["possible_conflict", styles.conflict],
  ["needs_human", styles.human],
  ["missing_evidence", styles.missing],
  ["evidence_complete", styles.complete],
];

/**
 * A grant's charges as a thin bar, one segment per bucket sized by the row's
 * own counts, plus a neutral one for charges the counts don't cover. A grant
 * with no charges gets one neutral bar. The text beside it carries the meaning.
 */
function ReadyBar({ summary }: { summary: GrantSummary }) {
  const segments = SEGMENTS.map(([bucket, className]) => ({ bucket, className, count: summary.bucket_counts?.[bucket] ?? 0 }));
  const rest = Math.max(summary.charges_total - segments.reduce((sum, s) => sum + s.count, 0), 0);
  return (
    <span className={styles.bar} aria-hidden="true">
      {segments
        .filter((s) => s.count > 0)
        .map((s) => (
          <span key={s.bucket} className={s.className} style={{ flexGrow: s.count }} />
        ))}
      {(rest > 0 || summary.charges_total === 0) && <span className={styles.rest} style={{ flexGrow: rest || 1 }} />}
    </span>
  );
}

/**
 * The workspace's grants, one row each (answer 7 of #22): award number, title,
 * end date in force, charges ready out of total, rows on its problem list, and
 * the next closeout date. Rows keep the server's order.
 */
export function GrantList({ grants }: { grants: GrantSummary[] }) {
  const nameOf = useGrantDisplayName();
  if (grants.length === 0) {
    return <p className="ft-empty">No grants in this workspace yet.</p>;
  }
  return (
    <div className="ft-panel">
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Grant</th>
            <th scope="col">Ends</th>
            <th scope="col">Ready for closeout</th>
            <th scope="col">Problem list</th>
            <th scope="col">Next closeout date</th>
          </tr>
        </thead>
        <tbody>
          {grants.map((g) => (
            <tr key={g.grant.id} className={styles.row}>
              <td className={styles.grant}>
                <Link className={styles.name} href={routes.grant(g.grant.id)}>
                  {nameOf(g)}
                </Link>
                {g.grant.award_number && <div className="ft-id">{g.grant.award_number}</div>}
              </td>
              <td data-label="Ends">
                {g.end_date ? <span className={styles.date}>{date(g.end_date)}</span> : <span className="ft-caption">Not confirmed yet</span>}
              </td>
              <td data-label="Ready for closeout">
                <span className={styles.ready}>
                  <strong>{g.charges_ready}</strong> of {g.charges_total} <span className={styles.unit}>charges</span>
                </span>
                <ReadyBar summary={g} />
              </td>
              <td data-label="Problem list">
                {g.on_problem_list > 0 ? (
                  <span className="ft-count ft-count--alert">
                    {g.on_problem_list}
                    <span className="ft-sr"> on the problem list</span>
                  </span>
                ) : (
                  <span className="ft-caption">None</span>
                )}
              </td>
              <td data-label="Next closeout date">
                {g.next_closeout ? (
                  <>
                    <div className={`${styles.date} ${styles.next}`}>{date(g.next_closeout.date)}</div>
                    <div className="ft-caption">{g.next_closeout.label}</div>
                  </>
                ) : (
                  <span className="ft-caption">None</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
