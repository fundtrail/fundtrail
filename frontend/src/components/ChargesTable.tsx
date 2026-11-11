import Link from "next/link";
import type { ChargeRow } from "@/lib/api";
import { routes } from "@/lib/routes";
import { CATEGORY_LABELS, date, money } from "@/lib/format";
import { ChargeStatusBadge } from "./BucketBadge";
import styles from "./ChargesTable.module.css";

/**
 * Every charge on the grant with its bucket and budget line. Each row shows the
 * ledger's own account with its group's categories and the budget line the
 * charge is assigned to (answers 8 and 15 of #22). Rows keep the server's order,
 * and each row opens its charge.
 */
export function ChargesTable({ rows }: { rows: ChargeRow[] }) {
  if (rows.length === 0) {
    return <p className={`ft-empty ${styles.empty}`}>No charges.</p>;
  }
  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Charge</th>
            <th scope="col">Ledger account</th>
            <th scope="col">Budget line</th>
            <th scope="col" className={styles.right}>
              Amount
            </th>
            <th scope="col">Bucket</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ charge, status = null, budget_line, account_categories = [] }) => (
            <tr key={charge.id}>
              <td>
                <div className="ft-num">{date(charge.transaction_date)}</div>
                <div className="ft-id">{charge.ledger_line_id}</div>
              </td>
              <td>
                <div>
                  {/* The whole row opens the charge through this link. */}
                  <Link className={`ft-link ${styles.rowLink}`} href={routes.charge(charge.grant_id, charge.id)}>
                    {charge.description}
                  </Link>
                </div>
                {charge.vendor && <div className="ft-caption">{charge.vendor}</div>}
              </td>
              <td>
                <span className={styles.label}>Ledger account</span>
                <div>{charge.account}</div>
                {account_categories.length > 0 && <div className="ft-caption">{account_categories.map((c) => CATEGORY_LABELS[c]).join(", ")}</div>}
              </td>
              <td>
                <span className={styles.label}>Budget line</span>
                {budget_line ? budget_line.data.name.value : <span className="ft-caption">Not assigned yet</span>}
              </td>
              <td className={`ft-num ${styles.right} ${styles.amount}`}>{money(charge.amount_cents)}</td>
              <td>
                <ChargeStatusBadge status={status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
