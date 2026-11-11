import Link from "next/link";
import { ChargeStatusBadge } from "@/components/BucketBadge";
import type { ChargeRow, Id } from "@/lib/api";
import { date, money } from "@/lib/format";
import { routes } from "@/lib/routes";
import "./closeout.css";

/**
 * Snoozed charges, for "Still open" on the closeout view. A snooze hides a
 * charge from the problem list, but a snoozed charge isn't ready for closeout
 * (decision 0022), so closeout lists them. Which charges are snoozed comes from
 * each charge's status as the server sends it; the screen works nothing out.
 */
export function SnoozedCharges({ grantId, rows }: { grantId: Id; rows: ChargeRow[] }) {
  const snoozed = rows.filter((r) => r.status?.snoozed === true);
  if (snoozed.length === 0) return null;
  return (
    <div className="ft-co-snoozed" role="group" aria-labelledby="snoozed-heading">
      <p id="snoozed-heading" className="ft-label">
        Snoozed: off the problem list, not ready for closeout ({snoozed.length})
      </p>
      <ul className="ft-co-snoozed__list">
        {snoozed.map(({ charge, status }) => (
          <li key={charge.id} className="ft-co-snoozed__row">
            <div>
              <Link className="ft-link ft-strong" href={routes.charge(grantId, charge.id)}>
                {charge.description}
              </Link>
              <div className="ft-caption">
                <span className="ft-id">{charge.ledger_line_id}</span> · {date(charge.transaction_date)}
              </div>
            </div>
            <div className="ft-co-snoozed__side">
              <span className="ft-co-amount ft-strong">{money(charge.amount_cents)}</span>
              <ChargeStatusBadge status={status ?? null} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
