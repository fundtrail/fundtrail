"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { Loadable } from "@/components/Loadable";
import { ChargeDetailView, type ChargeLinks } from "@/components/charge/ChargeDetailView";
import { RecordThreadView } from "@/components/thread/RecordThreadView";
import { useThreadActions } from "@/components/thread/useThreadActions";
import { useCharge, useChargeThread, useEvidence, useProblemList, useRecords, useRecordThread, type EvidenceFile, type Id, type ProblemRow } from "@/lib/api";
import { date, HOLD_REASON_LABELS, SOURCE_LABELS, UNREADABLE_FROM_LABEL } from "@/lib/format";
import { routes } from "@/lib/routes";
import { GrantProblemPane } from "./GrantProblemPane";
import styles from "./SelectedProblem.module.css";

/** The bar over the item: a link to open it on its own page. */
function Bar({ href }: { href?: string }) {
  if (!href) return null;
  return (
    <div className={styles.paneBar}>
      <Link className="ft-link" href={href}>
        Open on its own page
      </Link>
    </div>
  );
}

/** A charge beside the list, as the charge page shows it. */
function ChargePane({ grantId, chargeId }: { grantId: Id; chargeId: Id }) {
  const detail = useCharge(chargeId);
  const thread = useChargeThread(chargeId);
  const actions = useThreadActions(grantId, { chargeId });
  const links: ChargeLinks = {
    link: (view) => (view.file ? routes.file(grantId, view.file.id) : undefined),
    quote: (citation) => routes.file(grantId, citation.file_id),
    file: (fileId) => routes.file(grantId, fileId),
  };
  return (
    <>
      <Bar href={routes.charge(grantId, chargeId)} />
      <div className={styles.charge}>
        <Loadable result={detail}>
          {(data) => (
            <ChargeDetailView
              detail={thread.data ? { ...data, thread: thread.data } : data}
              onDecide={actions.decide}
              onWrite={actions.write}
              onAsk={actions.ask}
              links={links}
              headingLevel={2}
            />
          )}
        </Loadable>
      </div>
    </>
  );
}

/** A record's thread beside the list, as the record page shows it. */
function RecordPane({ grantId, recordId }: { grantId: Id; recordId: Id }) {
  const problems = useProblemList(grantId);
  const records = useRecords(grantId);
  const evidence = useEvidence(grantId);
  const thread = useRecordThread(recordId);
  const actions = useThreadActions(grantId, { recordId });
  const view = records.data?.find((r) => r.record.id === recordId) ?? null;
  const row = problems.data?.rows.find((r) => r.kind === "record" && r.status.record_id === recordId);
  const status = row?.kind === "record" ? row.status : null;
  const files: Record<Id, EvidenceFile> = {};
  for (const card of evidence.data ?? []) files[card.file.id] = card.file;
  return (
    <>
      <Bar href={routes.record(grantId, recordId)} />
      <div className={styles.charge}>
        <Loadable result={thread}>
          {(data) => (
            <RecordThreadView
              recordId={recordId}
              record={view?.record ?? null}
              state={view?.state ?? null}
              status={status}
              files={files}
              thread={data}
              fileHref={(fileId) => routes.file(grantId, fileId)}
              quoteHref={(citation) => routes.file(grantId, citation.file_id)}
              onDecide={actions.decide}
              onAsk={actions.ask}
              headingLevel={2}
            />
          )}
        </Loadable>
      </div>
    </>
  );
}

/** A row that has no thread of its own here: the same words as its row, and its page. */
function Summary({ href, tag, name, children }: { href?: string; tag: string; name?: ReactNode; children: ReactNode }) {
  return (
    <div className={`ft-panel ${styles.summary}`}>
      <div className={styles.summaryTop}>
        <span className="ft-tag">{tag}</span>
        {href && (
          <Link className={`ft-link ${styles.open}`} href={href}>
            Open on its own page
          </Link>
        )}
      </div>
      {name && <h2 className={styles.summaryName}>{name}</h2>}
      {children}
    </div>
  );
}

function RowPane({ grantId, row, focusHeading }: { grantId: Id; row: ProblemRow; focusHeading: boolean }) {
  switch (row.kind) {
    case "charge":
      return <ChargePane grantId={grantId} chargeId={row.charge.id} />;
    case "record":
      if (row.record) return <RecordPane grantId={grantId} recordId={row.record.id} />;
      return (
        <Summary href={row.file ? routes.file(grantId, row.file.id) : undefined} tag="File" name={row.file?.name}>
          {row.status.problems.map((p) => (
            <p key={`${p.check}:${p.problem}`}>{p.text}</p>
          ))}
        </Summary>
      );
    case "terms_waiting":
      return (
        <Summary href={routes.terms(row.file.grant_id)} tag="Terms" name={row.file.name}>
          <p>{row.text}</p>
          <p className="ft-caption">
            {SOURCE_LABELS[row.file.source]} · <span className="ft-num">{date(row.file.arrived_at)}</span>
          </p>
        </Summary>
      );
    case "held_mail":
      return (
        <Summary href={routes.mail(row.held.workspace_id)} tag="Mail" name={row.held.subject || "No subject"}>
          <p>{row.held.sender?.trim() ? `${HOLD_REASON_LABELS[row.held.reason]} · ${row.held.sender.trim()}` : UNREADABLE_FROM_LABEL}</p>
          <p className="ft-caption">
            Gmail · <span className="ft-num">{date(row.held.held_at)}</span>
          </p>
        </Summary>
      );
    case "grant":
      return <GrantProblemPane grantId={grantId} problem={row.problem} focusHeading={focusHeading} />;
  }
}

/**
 * The item picked on the problem list, shown wherever the page puts it: a charge as the charge
 * page shows it, a record's thread as the record page shows it, and anything
 * else with the words from its row and a link to its page. A charge or record
 * that isn't a row of its own (a benefit charge waiting on its salary line)
 * still shows by its ID.
 */
export function SelectedProblem({
  grantId,
  itemKey,
  row,
  focusHeading = false,
}: {
  grantId: Id;
  itemKey: string;
  row: ProblemRow | null;
  /** Move focus to the item's heading when it opens, as a page change would. */
  focusHeading?: boolean;
}) {
  return <div className={styles.pane}>{paneFor(grantId, itemKey, row, focusHeading)}</div>;
}

function paneFor(grantId: Id, itemKey: string, row: ProblemRow | null, focusHeading: boolean) {
  if (row) return <RowPane grantId={grantId} row={row} focusHeading={focusHeading} />;
  const [kind, ...rest] = itemKey.split(":");
  const id = rest.join(":");
  if (kind === "charge" && id) return <ChargePane grantId={grantId} chargeId={id} />;
  if (kind === "record" && id) return <RecordPane grantId={grantId} recordId={id} />;
  return null;
}
