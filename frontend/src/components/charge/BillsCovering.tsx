import Link from "next/link";
import type { LinkView } from "@/lib/api";
import { date, money, recordKindLabel } from "@/lib/format";
import { citedValue, field } from "./labels";
import styles from "./charge.module.css";

/** One line on what the linked record gives: "$5,000.00 of $10,000.00" for a bill. */
function uses(view: LinkView): string | null {
  const amount = field<number | null>(view.link, "amount_cents");
  const kind = view.record.data.kind;
  if (kind === "bill") {
    const total = citedValue<number>(view.record, "total");
    if (amount === null || amount === undefined) return total === undefined ? null : `Bill total ${money(total)}`;
    return total === undefined ? money(amount) : `${money(amount)} of ${money(total)}`;
  }
  if (kind === "approval") return citedValue<string>(view.record, "covers") ?? null;
  if (kind === "note") return citedValue<string>(view.record, "statement") ?? null;
  return amount === null || amount === undefined ? null : money(amount);
}

function source(view: LinkView): string | null {
  const kind = view.record.data.kind;
  if (kind === "bill") return citedValue<string>(view.record, "vendor") ?? citedValue<string>(view.record, "document_number") ?? null;
  if (kind === "approval") return citedValue<string>(view.record, "approver_name") ?? citedValue<string>(view.record, "approver_email") ?? null;
  if (kind === "note") return field<string>(view.record, "label") ?? null;
  return null;
}

/**
 * The bills, approvals and explaining notes linked to the charge, with how much
 * of each bill it uses. Each name opens the viewer at the link's part.
 */
export function BillsCovering({ links, viewerHref }: { links: LinkView[]; viewerHref?: (view: LinkView) => string | undefined }) {
  if (links.length === 0) return <p className="ft-empty">Nothing is linked to this charge yet.</p>;
  return (
    <ul className={styles.list} aria-label="Bills and evidence covering this charge">
      {links.map((view) => {
        const name = view.file?.name ?? `${recordKindLabel(view.record.data.kind)} typed by the accountant`;
        const href = viewerHref?.(view);
        const unconfirmed = (view.values ?? []).filter((v) => !v.confirmed).map((v) => v.path);
        const reason = field<string | null>(view.link, "reason");
        const what = uses(view);
        const from = source(view);
        return (
          <li key={view.link.id} className={styles.row}>
            <p className={styles.line}>
              <span className="ft-tag">{recordKindLabel(view.record.data.kind)}</span>
              {href ? (
                <Link className="ft-link" href={href}>
                  {name}
                </Link>
              ) : (
                <span>{name}</span>
              )}
              {from && <span className="ft-caption">{from}</span>}
            </p>
            {what && <p className="ft-num">{what}</p>}
            {reason && (
              <p className="ft-caption">
                {view.link.author === "agent" ? "Agent's reason: " : "Accountant's reason: "}
                {reason}
              </p>
            )}
            <p className="ft-caption">
              Linked by {view.link.author === "agent" ? "the agent" : "the accountant"}, {date(view.link.written_at)}
              {unconfirmed.length > 0 && <> · Not confirmed: {unconfirmed.join(", ")}</>}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
