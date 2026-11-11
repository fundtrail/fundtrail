import Link from "next/link";
import type { BudgetView, GrantNote } from "@/lib/api";
import { CATEGORY_LABELS, money } from "@/lib/format";
import styles from "./BudgetFigures.module.css";

/** How much of a line is spent, for its bar: a plain share of the two amounts, held to the bar's length. */
function share(spent: number, amount: number): string {
  if (amount <= 0) return spent > 0 ? "100%" : "0%";
  return `${Math.min(100, Math.max(0, (spent / amount) * 100)).toFixed(1)}%`;
}

/**
 * The grant's budget: every line with what's spent of its amount, over or not
 * (answer 8 of #22), and the grant notes beside them (answer 3). An overspent
 * line is a note from code, never a problem here. A page that shows the notes
 * elsewhere leaves `notes` out.
 */
export function BudgetFigures({ budget, notes = [], ledgerHref }: { budget: BudgetView; notes?: GrantNote[]; ledgerHref?: string }) {
  return (
    <section className={styles.budget} aria-labelledby="budget-heading">
      <h2 id="budget-heading" className={styles.heading}>
        Budget
        {ledgerHref && (
          <Link className="ft-link" href={ledgerHref}>
            Ledger
          </Link>
        )}
      </h2>
      {budget.lines.length === 0 ? (
        <p className={`ft-caption ${styles.empty}`}>No budget lines.</p>
      ) : (
        <ul className={styles.lines}>
          {budget.lines.map((l) => {
            const name = l.line.data.name.value;
            return (
              <li key={l.line.id} className={styles.line}>
                <span className={styles.name}>
                  {name}
                  {CATEGORY_LABELS[l.line.data.category] !== name && <span className="ft-caption"> · {CATEGORY_LABELS[l.line.data.category]}</span>}
                </span>
                <span className={`ft-num ${styles.amounts}`}>
                  {money(l.spent_cents)} of {money(l.amount_cents)}
                </span>
                <span className={styles.track} aria-hidden="true">
                  <i style={{ width: share(l.spent_cents, l.amount_cents) }} />
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {notes.length > 0 && (
        <ul className={styles.notes} aria-label="Grant notes">
          {notes.map((n, i) => (
            <li key={`${n.check}:${i}`}>{n.text}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
