"use client";

import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { Charge, ChargeDetail, Id, LinkView } from "@/lib/api";
import { ReviewThread } from "../thread/ReviewThread";
import type { OnDecide } from "../thread/Decide";
import type { OnWrite } from "../thread/useThreadActions";
import { AgentAnswers, type QuoteHref } from "./AgentAnswers";
import { BillsCovering } from "./BillsCovering";
import { ChargeHeader } from "./ChargeHeader";
import { EvidenceChecklist, MissingItems } from "./EvidenceChecklist";
import { field } from "./labels";
import { StatusHistory } from "./StatusHistory";
import { AcceptedReasons, PassingReasons, reasonKey, StatusReasons } from "./StatusReasons";
import { Disclosure, TrailGroup, TrailNode } from "./Trail";
import styles from "./charge.module.css";

export interface ChargeLinks {
  /** The viewer at a link's part, highlighted. */
  link?: (view: LinkView) => string | undefined;
  /** The viewer at a quoted passage; an answer's quotes also pass the answer's id and the quote's index. */
  quote?: QuoteHref;
  /** The viewer at a file. */
  file?: (fileId: Id) => string | undefined;
}

function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** The records a link puts on the trail, named for the trail's closed line. */
const LINKED_KINDS: Record<string, [string, string]> = {
  bill: ["bill", "bills"],
  approval: ["approval", "approvals"],
  note: ["note", "notes"],
  other: ["linked record", "linked records"],
};

type Tab = "needs" | "thread";

/**
 * The two tabs of the charge in the problem list's pane: what needs the
 * accountant, and the review thread. Arrow keys move between them, as in
 * any tab list; only the chosen tab is a tab stop.
 */
function PaneTabs({
  tab,
  onTab,
  ids,
  needsCount,
  threadCount,
  threadWaiting,
}: {
  tab: Tab;
  onTab: (tab: Tab) => void;
  ids: Record<Tab, { tab: string; panel: string }>;
  needsCount: number | null;
  threadCount: number;
  threadWaiting: number;
}) {
  const refs = useRef<Record<Tab, HTMLButtonElement | null>>({ needs: null, thread: null });
  const order: Tab[] = ["needs", "thread"];
  function keyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const at = order.indexOf(tab);
    let next: Tab | null = null;
    if (event.key === "ArrowRight") next = order[(at + 1) % order.length];
    else if (event.key === "ArrowLeft") next = order[(at + order.length - 1) % order.length];
    else if (event.key === "Home") next = order[0];
    else if (event.key === "End") next = order[order.length - 1];
    if (!next) return;
    event.preventDefault();
    onTab(next);
    refs.current[next]?.focus();
  }
  const button = (which: Tab, label: ReactNode) => (
    <button
      ref={(el) => {
        refs.current[which] = el;
      }}
      type="button"
      role="tab"
      id={ids[which].tab}
      aria-selected={tab === which}
      aria-controls={ids[which].panel}
      tabIndex={tab === which ? 0 : -1}
      className={styles.tab}
      onClick={() => onTab(which)}
      onKeyDown={keyDown}
    >
      {label}
    </button>
  );
  return (
    <div className={styles.tabs} role="tablist" aria-label="The charge">
      {button(
        "needs",
        <>
          Needs you
          {needsCount !== null && needsCount > 0 && <span className="ft-count">{needsCount}</span>}
        </>,
      )}
      {button(
        "thread",
        <>
          Review thread
          <span className="ft-count">{threadCount}</span>
          {threadWaiting > 0 && <span className={styles.tabNote}>{threadWaiting} waiting</span>}
        </>,
      )}
    </div>
  );
}

/**
 * The charge, decision first. Its header (the bucket, the name and the
 * amount, the rest quieter), then what needs the accountant: the reasons the
 * server still gives, each with its actions beside it, and Snooze for the
 * whole charge. Everything else is one closed line away: the evidence trail
 * from the ledger line through the bills and answers to the reasons already
 * accepted, the reasons that pass, the evidence checklist and the status
 * history. A line opens on its own only when something in it needs the
 * accountant, and stays as the accountant leaves it from one charge to the
 * next.
 *
 * The review thread is the other main part. On the charge's own page
 * (`layout="page"`) it sits beside the charge when there's room and under it
 * when there isn't. In the problem list's pane (`layout="pane"`) the charge
 * and the thread are two tabs that fill the pane, so the thread and its ask
 * box are one click away, never under everything else.
 */
export function ChargeDetailView({
  detail,
  onDecide,
  onAsk,
  onWrite,
  links = {},
  headingLevel = 1,
  layout = "page",
  pageHref,
}: {
  detail: ChargeDetail;
  onDecide: OnDecide;
  onAsk: (text: string) => Promise<void>;
  /** The accountant's other records: answers, checklist changes, accepted reasons, snoozes. */
  onWrite?: OnWrite;
  links?: ChargeLinks;
  /** The charge's title: h1 on its own page, h2 inside another page. */
  headingLevel?: 1 | 2;
  /** The charge's own page, or the problem list's pane beside the list. */
  layout?: "page" | "pane";
  /** The charge's own page, linked from the header when another page shows the charge. */
  pageHref?: string;
}) {
  const { charge, status } = detail;
  const records = detail.records ?? {};
  const files = detail.files ?? {};
  const links_ = detail.links ?? [];
  const waiting = detail.waiting ?? [];
  const answers = detail.answers ?? [];
  const questions = detail.questions ?? [];
  // The agent's waiting records the review thread already offers to decide; the rest are decided on their reason.
  const inThread = detail.thread.entries.flatMap((e) => (e.kind === "record" && e.state === "waiting" ? [e.record.id] : []));
  const history = detail.history ?? [];
  const checklist = status?.checklist ?? [];
  const charges: Record<Id, Charge> = { [charge.id]: charge };
  for (const c of detail.corrections ?? []) charges[c.id] = c;
  const filled = checklist.filter((e) => e.filled).length;
  // An empty checklist needs the accountant too: Add item is their next step.
  const checklistNeedsYou = checklist.length === 0 || checklist.some((e) => !e.filled || e.removal_waiting_id);
  // The trail opens on its own when one of its nodes opens on its own: an answer
  // that isn't Supports, a question waiting for the accountant, a link not yet confirmed.
  const trailNeedsYou =
    answers.some((a) => field<string>(a.judgment, "answer") !== "supports") ||
    questions.some((q) => q.answer_by !== "agent") ||
    links_.some((l) => (l.values ?? []).some((v) => !v.confirmed));

  const failing = (status?.reasons ?? []).filter((r) => r.bucket !== "evidence_complete");
  const openKeys = failing.filter((r) => !r.accepted_by).map(reasonKey);
  // The reasons already accepted when the charge opened are settled: they fold
  // into the trail. One accepted here stays in view with its result; one
  // reopened comes back to the top.
  const [settled, setSettled] = useState(() => failing.filter((r) => r.accepted_by).map(reasonKey));
  if (settled.some((k) => openKeys.includes(k))) setSettled(settled.filter((k) => !openKeys.includes(k)));

  const [tab, setTab] = useState<Tab>("needs");
  const uid = useId();
  const ids: Record<Tab, { tab: string; panel: string }> = {
    needs: { tab: `${uid}-needs-tab`, panel: `${uid}-needs` },
    thread: { tab: `${uid}-thread-tab`, panel: `${uid}-thread` },
  };
  const pane = layout === "pane";

  // What the trail holds, named by kind in the order the server sent it: "1 bill, 1 answer".
  const linkedKinds: Record<string, number> = {};
  for (const l of links_) {
    const kind = LINKED_KINDS[l.record.data.kind] ? l.record.data.kind : "other";
    linkedKinds[kind] = (linkedKinds[kind] ?? 0) + 1;
  }
  const trailCount = [
    ...Object.entries(linkedKinds).map(([kind, n]) => count(n, ...LINKED_KINDS[kind])),
    answers.length > 0 && count(answers.length, "answer", "answers"),
    questions.length > 0 && count(questions.length, "open question", "open questions"),
  ]
    .filter(Boolean)
    .join(", ");

  const needsYou = (
    <>
      <div className={styles.trail}>
        <StatusReasons
          status={status ?? null}
          chargeId={charge.id}
          chargedCents={status?.net_cents ?? charge.amount_cents}
          records={records}
          inThread={inThread}
          onWrite={onWrite}
          leaveOut={settled}
          passing={false}
        />
      </div>
      {status && openKeys.length === 0 && failing.every((r) => settled.includes(reasonKey(r))) && (
        <p className={styles.clear}>No open reasons on this charge.</p>
      )}
    </>
  );

  const folds = (
    <div className={styles.folds}>
      <Disclosure label="Evidence trail" count={trailCount || undefined} open={trailNeedsYou} attention={trailNeedsYou} testId="trail" remember="charge-trail">
        <div className={styles.trail}>
          <TrailGroup label="Ledger line">
            <TrailNode
              mark="ledger"
              title={
                <>
                  Ledger line <span className="ft-id">{charge.ledger_line_id}</span>
                </>
              }
            />
          </TrailGroup>
          <BillsCovering links={links_} viewerHref={links.link} />
          <MissingItems checklist={checklist} />
          <AgentAnswers
            answers={answers}
            questions={questions}
            rechecking={status?.rechecking ?? false}
            files={files}
            quoteHref={links.quote}
            chargeId={charge.id}
            onWrite={onWrite}
          />
          <AcceptedReasons status={status ?? null} keys={settled} chargeId={charge.id} records={records} onWrite={onWrite} />
        </div>
      </Disclosure>
      <PassingReasons status={status ?? null} remember="charge-passing" />
      <Disclosure
        label="Evidence checklist"
        count={checklist.length > 0 ? `${filled} of ${checklist.length} filled` : undefined}
        open={checklistNeedsYou}
        attention={checklistNeedsYou}
        testId="checklist"
        remember="charge-checklist"
      >
        <EvidenceChecklist
          checklist={checklist}
          links={links_}
          waiting={waiting}
          records={records}
          files={files}
          chargeId={charge.id}
          grantId={charge.grant_id}
          onWrite={onWrite}
        />
      </Disclosure>
      {history.length > 0 && (
        <Disclosure
          label="Status history"
          count={history.length === 1 ? "1 change" : `${history.length} changes`}
          testId="history"
          remember="charge-history"
        >
          <StatusHistory history={history} records={records} files={files} charges={charges} fileHref={links.file} />
        </Disclosure>
      )}
    </div>
  );

  const thread = (
    <ReviewThread
      thread={detail.thread}
      about={charge.ledger_line_id}
      ctx={{
        records,
        files,
        checklist,
        reasons: status?.reasons ?? [],
        waiting,
        quoteHref: links.quote,
      }}
      onDecide={onDecide}
      onAsk={onAsk}
      fill={pane}
    />
  );

  if (pane) {
    return (
      <div className={`${styles.view} ${styles.paneView}`}>
        <article className={styles.paneCard} aria-labelledby="charge-name">
          <div className={styles.paneHead}>
            <ChargeHeader detail={detail} headingLevel={headingLevel} pageHref={pageHref} />
          </div>
          <PaneTabs
            tab={tab}
            onTab={setTab}
            ids={ids}
            needsCount={status ? openKeys.length : null}
            threadCount={detail.thread.entries.length}
            threadWaiting={inThread.length}
          />
          <div className={styles.panel} role="tabpanel" id={ids.needs.panel} aria-labelledby={ids.needs.tab} hidden={tab !== "needs"}>
            <section className={styles.needs} aria-label="Needs you">
              {needsYou}
            </section>
            {folds}
          </div>
          <div
            className={`${styles.panel} ${styles.threadPanel}`}
            role="tabpanel"
            id={ids.thread.panel}
            aria-labelledby={ids.thread.tab}
            hidden={tab !== "thread"}
          >
            {thread}
          </div>
        </article>
      </div>
    );
  }

  return (
    <div className={styles.view}>
      <div className={styles.layout}>
        <article className={styles.card} aria-labelledby="charge-name">
          <ChargeHeader detail={detail} headingLevel={headingLevel} pageHref={pageHref} />
          <section className={styles.needs} aria-labelledby="needs-heading">
            <h2 id="needs-heading" className={styles.sectionHeading}>
              Needs you
            </h2>
            {needsYou}
          </section>
          {folds}
        </article>
        <section className={styles.dock} aria-labelledby="thread-heading">
          <h2 id="thread-heading" className={`${styles.sectionHeading} ${styles.dockHeading}`}>
            Review thread
          </h2>
          {thread}
        </section>
      </div>
    </div>
  );
}
