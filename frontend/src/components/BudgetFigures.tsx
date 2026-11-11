import type { BudgetView, GrantNote } from "@/lib/api";
import { CATEGORY_LABELS, money } from "@/lib/format";
import styles from "./Disclosure.module.css";

/**
 * The grant's budget: every line with its amount and what's spent, over or not
 * (answer 8 of #22), the award's limit, and the grant notes beside them
 * (answer 3). An overspent line is a note from code, never a problem here.
 * The lines open from a one-line summary; the notes always show.
 */
export function BudgetFigures({ budget, notes }: { budget: BudgetView; notes: GrantNote[] }) {
  return (
    <section className={`ft-panel ${styles.panel}`} aria-labelledby="budget-heading">
      <details className={styles.details}>
        <summary className={styles.summary}>
          <span className={styles.chevron} aria-hidden="true" />
          <h2 id="budget-heading" className="ft-heading">
            Budget
          </h2>
          <span className={`ft-caption ft-num ${styles.aside}`}>
            Charged {money(budget.spent_cents)}
            {budget.limit_cents != null && <> of the award&apos;s {money(budget.limit_cents)} limit</>}
          </span>
        </summary>
        <div className={styles.body}>
          <table className="ft-ledger ft-ledger--flush">
            <thead>
              <tr>
                <th scope="col">Budget line</th>
                <th scope="col" className="ft-right">
                  Amount
                </th>
                <th scope="col" className="ft-right">
                  Spent
                </th>
              </tr>
            </thead>
            <tbody>
              {budget.lines.map((l) => {
                const name = l.line.data.name.value;
                return (
                  <tr key={l.line.id}>
                    <td>
                      {name}
                      {CATEGORY_LABELS[l.line.data.category] !== name && (
                        <span className="ft-caption"> · {CATEGORY_LABELS[l.line.data.category]}</span>
                      )}
                    </td>
                    <td className="ft-right ft-num">{money(l.amount_cents)}</td>
                    <td className="ft-right ft-num">{money(l.spent_cents)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>
      {notes.length > 0 && (
        <ul className={`ft-notes ${styles.notes}`} aria-label="Grant notes">
          {notes.map((n, i) => (
            <li key={`${n.check}:${i}`}>{n.text}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
