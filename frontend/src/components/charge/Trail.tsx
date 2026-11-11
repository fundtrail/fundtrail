"use client";

import { useId, useState, type ReactNode } from "react";
import styles from "./trail.module.css";

/**
 * A node's mark on the evidence trail. `ledger`: the charge itself, a square.
 * `holds`: a link that holds, a check. `conflict`, `human` and `missing`: the
 * bucket's own mark, a diamond, a ring and a dashed ring. `partly`: a
 * checklist item the server says is partly filled, a ring half filled in ink,
 * neither the check nor the dashed ring. `plain`: a small hollow ring for a
 * line with nothing to say yet.
 */
export type Mark = "ledger" | "holds" | "conflict" | "human" | "missing" | "partly" | "plain";

/**
 * One node on the evidence trail: its mark on the line, a head line with the
 * name on the left and its status on the right, lines always shown under it
 * (`sub`), and optional detail. Detail is open by default only when it needs
 * the accountant (`open`); a closed one opens in place from its head line.
 * `broken` turns the line dashed from this node on.
 *
 * The head line is the toggle when its title holds no link. When it does
 * (`toggleLabel` set), the link and a small toggle at the end of the line are
 * siblings: one tab stop each, and the link is never inside a control.
 *
 * A node opened by default stays open when it no longer needs the accountant,
 * so the result of what they just did stays in view; it opens again when it
 * comes to need them.
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
  toggleLabel,
}: {
  mark: Mark;
  title: ReactNode;
  status?: ReactNode;
  open?: boolean;
  broken?: boolean;
  /** Lines always shown under the head, such as what a bill is and how much of it the charge uses. */
  sub?: ReactNode;
  children?: ReactNode;
  testId?: string;
  /** The toggle's name when the title is a link, so the toggle stands beside it. */
  toggleLabel?: string;
}) {
  const [isOpen, setIsOpen] = useState(open);
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) setIsOpen(true);
  }
  const detailId = useId();
  const hasDetail = Boolean(children);
  const statusEl = status !== undefined && status !== null && status !== false && <span className={styles.status}>{status}</span>;
  const chevron = <span className={styles.chevron} aria-hidden="true" />;
  const toggle = { "aria-expanded": isOpen, "aria-controls": detailId, onClick: () => setIsOpen((o) => !o) };

  let head: ReactNode;
  if (!hasDetail) {
    head = (
      <div className={styles.head}>
        <span className={styles.title}>{title}</span>
        {statusEl}
      </div>
    );
  } else if (toggleLabel) {
    head = (
      <div className={styles.head}>
        <span className={styles.title}>{title}</span>
        {statusEl}
        <button type="button" className={styles.chevronButton} aria-label={toggleLabel} {...toggle}>
          {chevron}
        </button>
      </div>
    );
  } else {
    head = (
      <button type="button" className={`${styles.head} ${styles.headButton}`} {...toggle}>
        <span className={styles.title}>{title}</span>
        {statusEl}
        {chevron}
      </button>
    );
  }
  return (
    <li
      className={styles.node}
      data-mark={mark}
      data-break={broken || undefined}
      data-open={hasDetail ? isOpen : undefined}
      data-testid={testId}
    >
      <span className={styles.mark} aria-hidden="true" />
      <div className={styles.content}>
        {head}
        {sub && <div className={styles.sub}>{sub}</div>}
        {hasDetail && (
          <div id={detailId} className={styles.more}>
            {children}
          </div>
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
 * The folded lines the accountant opened or closed, by name, while the app
 * stays loaded: opening the evidence trail on one charge keeps it open on the
 * next one picked from the problem list. A reload forgets.
 */
const remembered = new Map<string, boolean>();

/**
 * A closed line that opens in place: "Evidence checklist · 2 of 3 filled",
 * "Passing · 3". Open by default only when something in it needs the
 * accountant, or when the accountant left the line of the same name
 * (`remember`) open; like a trail node, it stays open once opened until the
 * accountant closes it.
 */
export function Disclosure({
  label,
  count,
  open = false,
  attention = false,
  children,
  testId,
  remember,
}: {
  label: ReactNode;
  count?: ReactNode;
  open?: boolean;
  /** Something in it needs the accountant: the line reads in ink, not muted. */
  attention?: boolean;
  children: ReactNode;
  testId?: string;
  /** A name to keep the accountant's open or closed choice under, across the charges they pick. */
  remember?: string;
}) {
  const [isOpen, setIsOpen] = useState(() => open || (remember !== undefined && remembered.get(remember) === true));
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) setIsOpen(true);
  }
  return (
    <details
      className={styles.disclosure}
      open={isOpen}
      onToggle={(e) => {
        const next = e.currentTarget.open;
        setIsOpen(next);
        if (remember !== undefined) remembered.set(remember, next);
      }}
      data-attention={attention || undefined}
      data-testid={testId}
    >
      <summary className={styles.disclosureHead}>
        <span>
          <span className={styles.disclosureLabel}>{label}</span>
          {count !== undefined && count !== null && <span> · {count}</span>}
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
