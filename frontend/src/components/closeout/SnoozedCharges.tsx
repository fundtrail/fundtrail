import Link from "next/link";
import { ChargeStatusBadge } from "@/components/BucketBadge";
import type { ChargeRow, Id } from "@/lib/api";
import { date, money } from "@/lib/format";
import { routes } from "@/lib/routes";

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
    <div role="group" aria-labelledby="snoozed-heading">
      <p id="snoozed-heading" className="ft-label">
        Snoozed: off the problem list, not ready for closeout ({snoozed.length})
      </p>
      <ul>
        {snoozed.map(({ charge, status }) => (
          <li key={charge.id}>
            <span className="ft-id">{charge.ledger_line_id}</span>{" "}
            <Link className="ft-link" href={routes.charge(grantId, charge.id)}>
              {charge.description}
            </Link>{" "}
            <span className="ft-caption">
              {date(charge.transaction_date)} · <span className="ft-num">{money(charge.amount_cents)}</span>
            </span>{" "}
            <ChargeStatusBadge status={status ?? null} />
          </li>
        ))}
      </ul>
    </div>
  );
}
