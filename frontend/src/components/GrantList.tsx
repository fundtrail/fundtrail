import Link from "next/link";
import type { ReactNode } from "react";
import type { GrantSummary } from "@/lib/api";
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

/**
 * The two numbers beside it drawn as a thin bar: charges ready for closeout,
 * filled, out of every charge, the empty track. Only those two numbers, so the
 * bar can never say something the text doesn't. No bucket colors.
 */
export function ReadyBar({ ready, total }: { ready: number; total: number }) {
  const share = total > 0 ? Math.min(Math.max(ready / total, 0), 1) : 0;
  return (
    <span className={styles.bar} aria-hidden="true" data-ready-bar="">
      <span className={styles.fill} style={{ width: `${share * 100}%` }} />
    </span>
  );
}

/** One cell; on narrow screens it shows its column's name above its value. */
function Cell({ label, className, children }: { label?: string; className?: string; children: ReactNode }) {
  return (
    <div role="cell" className={className ? `${styles.cell} ${className}` : styles.cell} data-label={label}>
      {children}
    </div>
  );
}

/**
 * The workspace's grants, one row each (answer 7 of #22): award number, title,
 * end date in force, charges ready out of total, rows on its problem list, and
 * the next closeout date. Rows keep the server's order. A table by its roles,
 * laid out as a grid, so each row can be one link and phones can stack it.
 */
export function GrantList({ grants }: { grants: GrantSummary[] }) {
  const nameOf = useGrantDisplayName();
  return (
    <div className="ft-panel">
      <div role="table" aria-label="Grants" className={styles.table}>
        <div role="rowgroup" className={styles.head}>
          <div role="row" className={styles.row}>
            <span role="columnheader">Grant</span>
            <span role="columnheader">Ends</span>
            <span role="columnheader">Ready for closeout</span>
            <span role="columnheader">Problem list</span>
            <span role="columnheader">Next closeout date</span>
          </div>
        </div>
        <div role="rowgroup">
          {grants.map((g) => (
            <div role="row" key={g.grant.id} className={`${styles.row} ${styles.grantRow}`}>
              <Cell className={styles.grant}>
                <Link className={styles.name} href={routes.grant(g.grant.id)}>
                  {nameOf(g)}
                </Link>
                {g.grant.award_number && <div className="ft-id">{g.grant.award_number}</div>}
              </Cell>
              <Cell label="Ends">
                {g.end_date ? <span className={styles.date}>{date(g.end_date)}</span> : <span className="ft-caption">Not confirmed yet</span>}
              </Cell>
              <Cell label="Ready for closeout">
                <span className={styles.ready}>
                  <strong>{g.charges_ready}</strong> of {g.charges_total} <span className={styles.unit}>charges</span>
                </span>
                <ReadyBar ready={g.charges_ready} total={g.charges_total} />
              </Cell>
              <Cell label="Problem list">
                {g.on_problem_list > 0 ? (
                  <span className="ft-count ft-count--alert">
                    {g.on_problem_list}
                    <span className="ft-sr"> on the problem list</span>
                  </span>
                ) : (
                  <span className="ft-caption">None</span>
                )}
              </Cell>
              <Cell label="Next closeout date">
                {g.next_closeout ? (
                  <>
                    <div className={`${styles.date} ${styles.next}`}>{date(g.next_closeout.date)}</div>
                    <div className="ft-caption">{g.next_closeout.label}</div>
                  </>
                ) : (
                  <span className="ft-caption">None</span>
                )}
              </Cell>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
