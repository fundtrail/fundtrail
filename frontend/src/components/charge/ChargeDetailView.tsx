import type { ReactNode } from "react";
import type { Charge, ChargeDetail, Citation, Id, LinkView } from "@/lib/api";
import { ReviewThread } from "../thread/ReviewThread";
import type { OnDecide } from "../thread/Decide";
import { AgentAnswers } from "./AgentAnswers";
import { BillsCovering } from "./BillsCovering";
import { ChargeHeader } from "./ChargeHeader";
import { EvidenceChecklist } from "./EvidenceChecklist";
import { StatusHistory } from "./StatusHistory";
import { StatusReasons } from "./StatusReasons";
import styles from "./charge.module.css";

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="ft-panel" aria-labelledby={id}>
      <div className="ft-panel__head">
        <h2 id={id} className="ft-heading">
          {title}
        </h2>
      </div>
      {children}
    </section>
  );
}

export interface ChargeLinks {
  /** The viewer at a link's part, highlighted. */
  link?: (view: LinkView) => string | undefined;
  /** The viewer at a quoted passage. */
  quote?: (citation: Citation) => string | undefined;
  /** The viewer at a file. */
  file?: (fileId: Id) => string | undefined;
}

/**
 * The charge page: the charge and its bucket, the server's reasons, the
 * evidence checklist, the bills covering it, the answers, status history, and
 * the review thread beside them.
 */
export function ChargeDetailView({
  detail,
  onDecide,
  onAsk,
  links = {},
}: {
  detail: ChargeDetail;
  onDecide: OnDecide;
  onAsk: (text: string) => Promise<void>;
  links?: ChargeLinks;
}) {
  const { charge, status } = detail;
  const records = detail.records ?? {};
  const files = detail.files ?? {};
  const links_ = detail.links ?? [];
  const waiting = detail.waiting ?? [];
  const charges: Record<Id, Charge> = { [charge.id]: charge };
  for (const c of detail.corrections ?? []) charges[c.id] = c;
  return (
    <>
      <ChargeHeader detail={detail} />
      <div className={styles.layout}>
        <div className={styles.column}>
          <Section id="reasons-heading" title="Why it's in this bucket">
            <StatusReasons status={status ?? null} />
          </Section>
          <Section id="checklist-heading" title="Evidence checklist">
            <EvidenceChecklist
              checklist={status?.checklist ?? []}
              links={links_}
              waiting={waiting}
              records={records}
              files={files}
            />
          </Section>
          <Section id="bills-heading" title="Bills and evidence covering it">
            <BillsCovering links={links_} viewerHref={links.link} />
          </Section>
          <Section id="answers-heading" title="Answers">
            <AgentAnswers
              answers={detail.answers ?? []}
              questions={detail.questions ?? []}
              rechecking={status?.rechecking ?? false}
              files={files}
              quoteHref={links.quote}
            />
          </Section>
          <Section id="history-heading" title="Status history">
            <StatusHistory history={detail.history ?? []} records={records} files={files} charges={charges} fileHref={links.file} />
          </Section>
        </div>
        <div className={styles.column}>
          <Section id="thread-heading" title="Review thread">
            <div className={styles.body}>
              <ReviewThread
                thread={detail.thread}
                about={charge.ledger_line_id}
                ctx={{
                  records,
                  files,
                  checklist: status?.checklist ?? [],
                  reasons: status?.reasons ?? [],
                  waiting,
                  quoteHref: links.quote,
                }}
                onDecide={onDecide}
                onAsk={onAsk}
              />
            </div>
          </Section>
        </div>
      </div>
    </>
  );
}
