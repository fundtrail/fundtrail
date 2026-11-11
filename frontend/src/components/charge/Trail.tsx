import type { ReactNode } from "react";
import styles from "./trail.module.css";

/**
 * A node's mark on the evidence trail. `ledger`: the charge itself, a square.
 * `holds`: a link that holds, a check. `conflict`, `human` and `missing`: the
 * bucket's own mark, a diamond, a ring and a dashed ring. `plain`: a small
 * hollow ring for a line with nothing to say yet.
 */
export type Mark = "ledger" | "holds" | "conflict" | "human" | "missing" | "plain";

/**
 * One node on the evidence trail: its mark on the line, a head line with the
 * name on the left and its status on the right, and optional detail under it.
 * Detail is open by default only when it needs the accountant (`open`); a
 * closed one opens in place from its head line. `broken` turns the line dashed
 * from this node on.
 */
export function TrailNode({
  mark,
  title,
  status,
  open = false,
  broken = false,
  sub,
  children,
  testId,
}: {
  mark: Mark;
  title: ReactNode;
  status?: ReactNode;
  open?: boolean;
  broken?: boolean;
  /** A short line always shown under the head, such as an expected date. */
  sub?: ReactNode;
  children?: ReactNode;
  testId?: string;
}) {
  const head = (
    <>
      <span className={styles.title}>{title}</span>
      {status !== undefined && status !== null && status !== false && <span className={styles.status}>{status}</span>}
    </>
  );
  return (
    <li className={styles.node} data-mark={mark} data-break={broken || undefined} data-testid={testId}>
      <span className={styles.mark} aria-hidden="true" />
      <div className={styles.content}>
        {children ? (
          <details className={styles.details} open={open}>
            <summary className={styles.summary}>
              <span className={styles.head}>
                {head}
                <span className={styles.chevron} aria-hidden="true" />
              </span>
              {sub && <span className={styles.sub}>{sub}</span>}
            </summary>
            <div className={styles.more}>{children}</div>
          </details>
        ) : (
          <>
            <div className={styles.head}>{head}</div>
            {sub && <span className={styles.sub}>{sub}</span>}
          </>
        )}
      </div>
    </li>
  );
}

/** A group of nodes on the trail, named for screen readers. The line runs on across groups. */
export function TrailGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ul className={styles.group} aria-label={label}>
      {children}
    </ul>
  );
}

/** A muted line on the trail with no mark of its own to give: an empty state. */
export function TrailNote({ children }: { children: ReactNode }) {
  return (
    <li className={styles.node} data-mark="plain" data-break>
      <span className={styles.mark} aria-hidden="true" />
      <p className={`${styles.content} ${styles.note}`}>{children}</p>
    </li>
  );
}

/**
 * A closed line that opens in place: "Evidence checklist · 2 of 3 filled",
 * "3 checks pass". Open by default only when something in it needs the
 * accountant.
 */
export function Disclosure({
  label,
  count,
  open = false,
  attention = false,
  children,
}: {
  label: ReactNode;
  count?: ReactNode;
  open?: boolean;
  /** Something in it needs the accountant: the line reads in ink, not muted. */
  attention?: boolean;
  children: ReactNode;
}) {
  return (
    <details className={styles.disclosure} open={open} data-attention={attention || undefined}>
      <summary className={styles.disclosureHead}>
        <span>
          <span className={styles.disclosureLabel}>{label}</span>
          {count !== undefined && count !== null && <span className={styles.disclosureCount}> · {count}</span>}
        </span>
        <span className={styles.toggle} aria-hidden="true">
          <span className={styles.show}>Show</span>
          <span className={styles.hide}>Hide</span>
        </span>
      </summary>
      <div className={styles.disclosureBody}>{children}</div>
    </details>
  );
}

export { styles as trailStyles };
