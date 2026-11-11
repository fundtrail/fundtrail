import type { ChargeDetail } from "@/lib/api";
import { CATEGORY_LABELS, date, money } from "@/lib/format";
import { ChargeStatusBadge } from "../BucketBadge";
import { citedValue } from "./labels";
import styles from "./charge.module.css";

/**
 * The charge as the ledger gives it, its budget line, and its bucket as the
 * checks gave it: a muted line with the ledger line, its dates and vendor and
 * the bucket at its end; the name with the amount; then the account and the
 * budget line, and any corrections netted into it.
 */
export function ChargeHeader({ detail, headingLevel = 1 }: { detail: ChargeDetail; headingLevel?: 1 | 2 }) {
  // The charge's own page titles it h1; a page that shows it inside another passes 2. The look is the class's.
  const Title = headingLevel === 2 ? "h2" : "h1";
  const { charge, status, budget_line } = detail;
  const account_categories = detail.account_categories ?? [];
  const corrections = detail.corrections ?? [];
  const lineName = citedValue<string>(budget_line, "name");
  const net = status?.net_cents !== undefined && status?.net_cents !== null ? status.net_cents : null;
  return (
    <header className={styles.header}>
      <div className={styles.headerTop}>
        <p className={styles.meta}>
          <span className="ft-id">{charge.ledger_line_id}</span>
          {charge.reference && <span>{charge.reference}</span>}
          <span>
            Cost date <span className="ft-num">{date(charge.transaction_date)}</span>
          </span>
          <span>
            Posted <span className="ft-num">{date(charge.posting_date)}</span>
          </span>
          {charge.vendor && <span>{charge.vendor}</span>}
        </p>
        <ChargeStatusBadge status={status ?? null} />
      </div>
      <div className={styles.nameRow}>
        <Title id="charge-name" className={styles.name}>{charge.description}</Title>
        <span className={`ft-num ${styles.amount}`}>{money(charge.amount_cents)}</span>
      </div>
      <p className={styles.meta}>
        <span>
          Ledger account <span className={styles.fact}>{charge.account}</span>
          {account_categories.length > 0 && <> ({account_categories.map((c) => CATEGORY_LABELS[c]).join(", ")})</>}
        </span>
        <span>
          Budget line {lineName ? <span className={styles.fact}>{lineName}</span> : <>Not assigned yet</>}
        </span>
      </p>
      {(charge.original_line_id || net !== null || corrections.length > 0) && (
        <p className={styles.meta}>
          {charge.original_line_id && (
            <span>
              Corrects <span className="ft-id">{charge.original_line_id}</span>
            </span>
          )}
          {net !== null && (
            <span>
              Net of corrections <span className={`ft-num ${styles.fact}`}>{money(net)}</span>
            </span>
          )}
          {corrections.length > 0 && (
            <span>
              Netted into it{" "}
              {corrections.map((c, i) => (
                <span key={c.id}>
                  {i > 0 && ", "}
                  <span className="ft-id">{c.ledger_line_id}</span> <span className="ft-num">({money(c.amount_cents)})</span>
                </span>
              ))}
            </span>
          )}
        </p>
      )}
    </header>
  );
}
