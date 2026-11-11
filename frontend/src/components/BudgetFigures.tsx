import Link from "next/link";
import type { BudgetLineView, BudgetView, GrantNote } from "@/lib/api";
import { CATEGORY_LABELS, money } from "@/lib/format";
import styles from "./BudgetFigures.module.css";

/** How much of a line is spent, for its bar: a plain share of the two amounts, held to the bar's length. */
function share(spent: number, amount: number): string {
  if (amount <= 0) return spent > 0 ? "100%" : "0%";
  return `${Math.min(100, Math.max(0, (spent / amount) * 100)).toFixed(1)}%`;
}

/**
 * Ruling 74: the lines in the server's order, each sub-line under the line its
 * `parent` names (the first line of that category), in the server's order
 * within it. A sub-line whose parent isn't in the list stays where it is, at
 * the top level. Nothing is added up: a sub-line's amounts are already inside
 * its parent's, as the server says.
 */
function nest(lines: BudgetLineView[]): { line: BudgetLineView; subs: BudgetLineView[] }[] {
  const parentOf = new Map<BudgetLineView, BudgetLineView>();
  for (const l of lines) {
    if (!l.parent) continue;
    const parent = lines.find((p) => p !== l && !p.parent && p.line.data.category === l.parent);
    if (parent) parentOf.set(l, parent);
  }
  return lines.filter((l) => !parentOf.has(l)).map((line) => ({ line, subs: lines.filter((l) => parentOf.get(l) === line) }));
}

/** One budget line: its name, spent of amount as the server gives them, and a thin bar. */
function Line({ l, sub = false }: { l: BudgetLineView; sub?: boolean }) {
  const name = l.line.data.name.value;
  return (
    <>
      <span className={styles.name}>
        {name}
        {CATEGORY_LABELS[l.line.data.category] !== name && <span className="ft-caption"> · {CATEGORY_LABELS[l.line.data.category]}</span>}
      </span>
      <span className={`ft-num ${styles.amounts}`}>
        {money(l.spent_cents)} of {money(l.amount_cents)}
      </span>
      <span className={`${styles.track}${sub ? ` ${styles.subTrack}` : ""}`} aria-hidden="true">
        <i style={{ width: share(l.spent_cents, l.amount_cents) }} />
      </span>
    </>
  );
}

/**
 * The grant's budget: every line with what's spent of its amount, over or not
 * (answer 8 of #22), sub-lines nested under their parent line (ruling 74), and
 * the grant notes beside them (answer 3). An overspent line is a note from
 * code, never a problem here. A page that shows the notes elsewhere leaves
 * `notes` out.
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
          {nest(budget.lines).map(({ line, subs }) => (
            <li key={line.line.id} className={styles.line}>
              <Line l={line} />
              {subs.length > 0 && (
                <ul className={styles.subs} aria-label={`Within ${line.line.data.name.value}`}>
                  {subs.map((sub) => (
                    <li key={sub.line.id} className={styles.subLine}>
                      <Line l={sub} sub />
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
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
