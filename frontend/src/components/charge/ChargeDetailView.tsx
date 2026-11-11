import type { Charge, ChargeDetail, Citation, Id, LinkView } from "@/lib/api";
import { ReviewThread } from "../thread/ReviewThread";
import type { OnDecide } from "../thread/Decide";
import type { OnWrite } from "../thread/useThreadActions";
import { AgentAnswers } from "./AgentAnswers";
import { BillsCovering } from "./BillsCovering";
import { ChargeHeader } from "./ChargeHeader";
import { EvidenceChecklist, MissingItems } from "./EvidenceChecklist";
import { StatusHistory } from "./StatusHistory";
import { StatusReasons } from "./StatusReasons";
import { Disclosure, TrailGroup, TrailNode } from "./Trail";
import styles from "./charge.module.css";

export interface ChargeLinks {
  /** The viewer at a link's part, highlighted. */
  link?: (view: LinkView) => string | undefined;
  /** The viewer at a quoted passage. */
  quote?: (citation: Citation) => string | undefined;
  /** The viewer at a file. */
  file?: (fileId: Id) => string | undefined;
}

/**
 * The charge: its header, then one evidence trail from the ledger line through
 * the bills and evidence covering it, what's missing, the answers, and the
 * server's failing reasons; then the evidence checklist and the status history,
 * each closed to one line unless something in it needs the accountant; and
 * the review thread docked under it, or beside it when there's room.
 */
export function ChargeDetailView({
  detail,
  onDecide,
  onAsk,
  onWrite,
  links = {},
}: {
  detail: ChargeDetail;
  onDecide: OnDecide;
  onAsk: (text: string) => Promise<void>;
  /** The accountant's other records: answers, checklist changes, accepted reasons, snoozes. */
  onWrite?: OnWrite;
  links?: ChargeLinks;
}) {
  const { charge, status } = detail;
  const records = detail.records ?? {};
  const files = detail.files ?? {};
  const links_ = detail.links ?? [];
  const waiting = detail.waiting ?? [];
  const history = detail.history ?? [];
  const checklist = status?.checklist ?? [];
  const charges: Record<Id, Charge> = { [charge.id]: charge };
  for (const c of detail.corrections ?? []) charges[c.id] = c;
  const filled = checklist.filter((e) => e.filled).length;
  // An empty checklist needs the accountant too: Add item is their next step.
  const checklistNeedsYou = checklist.length === 0 || checklist.some((e) => !e.filled || e.removal_waiting_id);
  return (
    <div className={styles.view}>
      <div className={styles.layout}>
        <article className={styles.card} aria-labelledby="charge-name">
          <ChargeHeader detail={detail} />
          <section className={styles.section} aria-labelledby="trail-heading">
            <h2 id="trail-heading" className={styles.sectionHeading}>
              Evidence trail
            </h2>
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
                answers={detail.answers ?? []}
                questions={detail.questions ?? []}
                rechecking={status?.rechecking ?? false}
                files={files}
                quoteHref={links.quote}
                chargeId={charge.id}
                onWrite={onWrite}
              />
              <StatusReasons
                status={status ?? null}
                chargeId={charge.id}
                chargedCents={status?.net_cents ?? charge.amount_cents}
                records={records}
                onWrite={onWrite}
              />
            </div>
          <div className={styles.closedLines}>
            <Disclosure
              label="Evidence checklist"
              count={checklist.length > 0 ? `${filled} of ${checklist.length} filled` : undefined}
              open={checklistNeedsYou}
              attention={checklistNeedsYou}
              testId="checklist"
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
              <Disclosure label="Status history" count={history.length === 1 ? "1 change" : `${history.length} changes`} testId="history">
                <StatusHistory history={history} records={records} files={files} charges={charges} fileHref={links.file} />
              </Disclosure>
            )}
          </div>
          </section>
        </article>
        <section className={styles.dock} aria-labelledby="thread-heading">
          <h2 id="thread-heading" className={`${styles.sectionHeading} ${styles.dockHeading}`}>
            Review thread
          </h2>
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
          />
        </section>
      </div>
    </div>
  );
}
