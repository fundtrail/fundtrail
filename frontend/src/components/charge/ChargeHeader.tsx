import type { ChargeDetail } from "@/lib/api";
import { CATEGORY_LABELS, date, money } from "@/lib/format";
import { ChargeStatusBadge } from "../BucketBadge";
import { citedValue } from "./labels";
import styles from "./charge.module.css";

/** The charge as the ledger gives it, its budget line, and its bucket as the checks gave it. */
export function ChargeHeader({ detail }: { detail: ChargeDetail }) {
  const { charge, status, budget_line } = detail;
  const account_categories = detail.account_categories ?? [];
  const corrections = detail.corrections ?? [];
  const lineName = citedValue<string>(budget_line, "name");
  return (
    <header className={`ft-panel ${styles.body}`}>
      <div className={styles.head}>
        <div>
          <p className="ft-caption">
            <span className="ft-id">{charge.ledger_line_id}</span>
            {charge.reference && <> · {charge.reference}</>}
          </p>
          <h1 className="ft-title">{charge.description}</h1>
          {charge.vendor && <p className="ft-caption">{charge.vendor}</p>}
        </div>
        <div className={styles.side}>
          <span className="ft-amount">{money(charge.amount_cents)}</span>
          <ChargeStatusBadge status={status ?? null} />
        </div>
      </div>
      <dl className={styles.facts}>
        <dt>Cost date</dt>
        <dd className="ft-num">{date(charge.transaction_date)}</dd>
        <dt>Posted</dt>
        <dd className="ft-num">{date(charge.posting_date)}</dd>
        <dt>Ledger account</dt>
        <dd>
          {charge.account}
          {account_categories.length > 0 && (
            <span className="ft-caption"> · {account_categories.map((c) => CATEGORY_LABELS[c]).join(", ")}</span>
          )}
        </dd>
        <dt>Budget line</dt>
        <dd>{lineName ?? <span className="ft-caption">Not assigned yet</span>}</dd>
        {charge.original_line_id && (
          <>
            <dt>Corrects</dt>
            <dd className="ft-id">{charge.original_line_id}</dd>
          </>
        )}
        {status?.net_cents !== undefined && status?.net_cents !== null && (
          <>
            <dt>Net of corrections</dt>
            <dd className="ft-num">{money(status.net_cents)}</dd>
          </>
        )}
        {corrections.length > 0 && (
          <>
            <dt>Netted into it</dt>
            <dd>
              {corrections.map((c) => (
                <span key={c.id} className="ft-id">
                  {c.ledger_line_id} ({money(c.amount_cents)}){" "}
                </span>
              ))}
            </dd>
          </>
        )}
      </dl>
    </header>
  );
}
