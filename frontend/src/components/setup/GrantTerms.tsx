"use client";

import Link from "next/link";
import { useId, useState } from "react";
import type { EvidenceFile, Id, ProblemRow, TermView } from "@/lib/api";
import { date, SOURCE_LABELS } from "@/lib/format";
import { routes } from "@/lib/routes";
import { TermCard } from "./TermCard";
import { isTermKind, TERM_GROUP_LABELS, type TermKind } from "./termFields";
import { useWrite, WriteProblems } from "./useWrite";
import "./setup.css";

type TermsWaitingRow = Extract<ProblemRow, { kind: "terms_waiting" }>;

/** The terms grouped by kind, the groups in the order their first term comes, each group's terms in the order they come. */
function byKind(terms: TermView[]): [TermKind, TermView[]][] {
  const groups = new Map<TermKind, TermView[]>();
  for (const t of terms) {
    const kind = t.record.data.kind;
    if (!isTermKind(kind)) continue;
    groups.set(kind, [...(groups.get(kind) ?? []), t]);
  }
  return [...groups.entries()];
}

/** A list of terms under a quiet heading per kind, with its count when there's more than one. */
function KindGroups({
  terms,
  settled = false,
  lead = false,
  heading: Heading,
}: {
  terms: TermView[];
  settled?: boolean;
  lead?: boolean;
  heading: "h3" | "h4";
}) {
  return (
    <div className="ft-tgroups">
      {byKind(terms).map(([kind, group]) => (
        <div key={kind} className="ft-tgroup" role="group" aria-label={TERM_GROUP_LABELS[kind]}>
          <Heading className="ft-tgroup__head">
            {TERM_GROUP_LABELS[kind]}
            {group.length > 1 && <span className="ft-count">{group.length}</span>}
          </Heading>
          {group.map((t) => (
            <TermCard key={t.record.id} term={t} settled={settled} lead={lead} />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * One source document's waiting terms, as one problem list row names them.
 * The first group on the page carries its one main button: Confirm all, or
 * its single term's Confirm when there's nothing to confirm all of.
 */
function WaitingGroup({ file, text, terms, primary }: { file: EvidenceFile | null; text: string | null; terms: TermView[]; primary: boolean }) {
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
            className={`ft-btn ft-btn--approve${primary ? " ft-btn--main" : ""}${saving ? " is-busy" : ""}`}
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
      <KindGroups terms={terms} settled={confirmedAll} lead={primary && waitingIds.length === 1} heading="h4" />
    </section>
  );
}

/** The terms no check uses any more: one closed group at the end, struck through. */
function RetiredGroup({ terms }: { terms: TermView[] }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <div className="ft-tgroup ft-tgroup--retired" role="group" aria-label="Not in force">
      <h3 className="ft-tgroup__head">
        <button type="button" className="ft-tgroup__toggle" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
          <span className="ft-trow__chev" aria-hidden="true" />
          Not in force
          <span className="ft-count">{terms.length}</span>
        </button>
      </h3>
      {open && (
        <div id={id}>
          {terms.map((t) => (
            <TermCard key={t.record.id} term={t} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * The confirm screen's body: one group per source document with terms waiting
 * (the problem list's terms rows, in the server's order), then any waiting
 * term no row names, then the terms in force grouped by kind, then those no
 * check uses any more. A term opens by itself only when it needs the
 * accountant; the rest show their values and open on a click.
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
        {waitingRows.map((row, i) => (
          <WaitingGroup
            key={row.file.id}
            file={row.file}
            text={row.text}
            terms={row.record_ids.flatMap((id) => (byId.has(id) ? [byId.get(id)!] : []))}
            primary={i === 0}
          />
        ))}
        {ungrouped.length > 0 && <WaitingGroup file={null} text={null} terms={ungrouped} primary={waitingRows.length === 0} />}
      </section>

      <section className="ft-panel" aria-labelledby="terms-heading">
        <div className="ft-panel__head ft-terms-head">
          <h2 id="terms-heading" className="ft-heading">
            Terms
          </h2>
        </div>
        {rest.length === 0 ? (
          <p className="ft-empty">
            {termTerms.some((t) => t.state === "waiting") ? "No terms in force yet. Confirm the ones waiting above." : "No terms yet. They appear as the agent reads the award letter."}
          </p>
        ) : (
          <>
            {inForce.length > 0 && <KindGroups terms={inForce} heading="h3" />}
            {retired.length > 0 && <RetiredGroup terms={retired} />}
          </>
        )}
      </section>
    </>
  );
}
