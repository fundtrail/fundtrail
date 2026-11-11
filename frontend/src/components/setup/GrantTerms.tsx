"use client";

import Link from "next/link";
import { useState } from "react";
import type { EvidenceFile, Id, ProblemRow, TermView } from "@/lib/api";
import { date, SOURCE_LABELS } from "@/lib/format";
import { routes } from "@/lib/routes";
import { TermCard } from "./TermCard";
import { isTermKind } from "./termFields";
import { useWrite, WriteProblems } from "./useWrite";
import "./setup.css";

type TermsWaitingRow = Extract<ProblemRow, { kind: "terms_waiting" }>;

/** The terms in the order they come, each marked when it continues a run of the same kind, so a run reads as one group. */
function TermRows({ terms, settled = false, lead = false }: { terms: TermView[]; settled?: boolean; lead?: boolean }) {
  return (
    <div className="ft-trs">
      {terms.map((t, i) => (
        <TermCard
          key={t.record.id}
          term={t}
          settled={settled}
          lead={lead}
          continues={i > 0 && terms[i - 1]!.record.data.kind === t.record.data.kind}
        />
      ))}
    </div>
  );
}

/** One source document's waiting terms, as one problem list row names them. */
function WaitingGroup({ file, text, terms }: { file: EvidenceFile | null; text: string | null; terms: TermView[] }) {
  const { state, write } = useWrite();
  const [confirmedAll, setConfirmedAll] = useState(false);
  const waitingIds: Id[] = terms.filter((t) => t.state === "waiting").map((t) => t.record.id);
  const grantId = terms[0]?.record.grant_id;
  const saving = state.status === "saving";

  async function confirmAll() {
    if (!grantId || waitingIds.length === 0) return;
    const saved = await write(grantId, { data: { kind: "confirmation", record_ids: waitingIds, decision: "confirmed" } });
    if (saved) setConfirmedAll(true);
  }

  return (
    <section className="ft-panel ft-waiting" aria-label={file ? `Terms waiting from ${file.name}` : "Other terms waiting"}>
      <div className="ft-waiting__head">
        <div className="ft-waiting__what">
          <h3 className="ft-heading">
            {file ? (
              <Link className="ft-link" href={routes.file(file.grant_id, file.id)}>
                {file.name}
              </Link>
            ) : (
              "Other terms waiting"
            )}
          </h3>
          {file && (
            <p className="ft-waiting__meta">
              {SOURCE_LABELS[file.source]} · arrived {date(file.arrived_at)}
            </p>
          )}
          {text && <p className="ft-waiting__count">{text}</p>}
        </div>
        {waitingIds.length > 1 && !confirmedAll && (
          <button
            type="button"
            className={`ft-btn ft-btn--approve ft-btn--main${saving ? " is-busy" : ""}`}
            disabled={saving}
            onClick={() => void confirmAll()}
          >
            Confirm all {waitingIds.length}
          </button>
        )}
        {confirmedAll && (
          <p className="ft-waiting__done" role="status">
            All {waitingIds.length} confirmed.
          </p>
        )}
      </div>
      {state.status === "failed" && (
        <div className="ft-waiting__problems">
          <WriteProblems state={state} />
        </div>
      )}
      <TermRows terms={terms} settled={confirmedAll} lead={waitingIds.length === 1} />
    </section>
  );
}

/**
 * The confirm screen's body: one group per source document with terms waiting
 * (the problem list's terms rows, in the server's order), then any waiting
 * term no row names, then every other term with its state: those in force
 * first, then those no check uses any more, each in the server's order.
 */
export function GrantTerms({ terms, rows }: { terms: TermView[]; rows: ProblemRow[] }) {
  const termTerms = terms.filter((t) => isTermKind(t.record.data.kind));
  const byId = new Map(termTerms.map((t) => [t.record.id, t]));
  const waitingRows = rows.filter((r): r is TermsWaitingRow => r.kind === "terms_waiting");
  const grouped = new Set(waitingRows.flatMap((r) => r.record_ids));
  const ungrouped = termTerms.filter((t) => t.state === "waiting" && !grouped.has(t.record.id));
  const rest = termTerms.filter((t) => t.state !== "waiting");
  const inForce = rest.filter((t) => t.state === "counts");
  const retired = rest.filter((t) => t.state !== "counts");

  return (
    <>
      <section className="ft-waiting-list" aria-labelledby="waiting-heading">
        <h2 id="waiting-heading" className="ft-heading">
          Waiting for you
        </h2>
        {waitingRows.length === 0 && ungrouped.length === 0 && <p className="ft-waiting__none">No terms are waiting to be confirmed.</p>}
        {waitingRows.map((row) => (
          <WaitingGroup
            key={row.file.id}
            file={row.file}
            text={row.text}
            terms={row.record_ids.flatMap((id) => (byId.has(id) ? [byId.get(id)!] : []))}
          />
        ))}
        {ungrouped.length > 0 && <WaitingGroup file={null} text={null} terms={ungrouped} />}
      </section>

      <section className="ft-panel" aria-labelledby="terms-heading">
        <div className="ft-panel__head ft-terms-head">
          <h2 id="terms-heading" className="ft-heading">
            Terms
          </h2>
        </div>
        {rest.length === 0 ? (
          <p className="ft-empty">No terms yet. They appear as the agent reads the award letter.</p>
        ) : (
          <>
            {inForce.length > 0 && <TermRows terms={inForce} />}
            {retired.length > 0 && (
              <div className="ft-retired">
                <TermRows terms={retired} />
              </div>
            )}
          </>
        )}
      </section>
    </>
  );
}
