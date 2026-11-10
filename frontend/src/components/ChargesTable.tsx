import Link from "next/link";
import type { ChargeRow } from "@/lib/api";
import { routes } from "@/lib/routes";
import { CATEGORY_LABELS, date, money } from "@/lib/format";
import { ChargeStatusBadge } from "./BucketBadge";

/**
 * Every charge on the grant with its bucket and budget line. Each row shows the
 * ledger's own account with its group's categories and the budget line the
 * charge is assigned to (answers 8 and 15 of #22). Rows keep the server's order.
 */
export function ChargesTable({ rows }: { rows: ChargeRow[] }) {
  if (rows.length === 0) {
    return <p className="ft-empty">No charges.</p>;
  }
  return (
    <table className="ft-ledger ft-ledger--flush">
      <thead>
        <tr>
          <th scope="col">Date</th>
          <th scope="col">Charge</th>
          <th scope="col">Ledger account</th>
          <th scope="col">Budget line</th>
          <th scope="col" className="ft-right">
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
                <Link className="ft-link" href={routes.charge(charge.grant_id, charge.id)}>
                  {charge.description}
                </Link>
              </div>
              {charge.vendor && <div className="ft-caption">{charge.vendor}</div>}
            </td>
            <td>
              <div>{charge.account}</div>
              {account_categories.length > 0 && (
                <div className="ft-caption">{account_categories.map((c) => CATEGORY_LABELS[c]).join(", ")}</div>
              )}
            </td>
            <td>{budget_line ? budget_line.data.name.value : <span className="ft-caption">Not assigned yet</span>}</td>
            <td className="ft-right ft-num">{money(charge.amount_cents)}</td>
            <td>
              <ChargeStatusBadge status={status} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
