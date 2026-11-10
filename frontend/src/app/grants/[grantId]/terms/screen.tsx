"use client";

import { useParams } from "next/navigation";
import { AppShell, Loadable } from "@/components/AppShell";
import { grantName } from "@/components/GrantList";
import { GrantTerms } from "@/components/setup/GrantTerms";
import { ReusableNotes } from "@/components/setup/ReusableNotes";
import { NoticeFilesProvider, noticeFilesFor } from "@/components/setup/noticeFiles";
import { useEvidence, useGrant, useProblemList } from "@/lib/api";

/**
 * A grant's terms: those waiting for the accountant, one group per source
 * document, then every other term, then the grant's reusable notes.
 * First version, may change.
 */
export function TermsScreen() {
  const { grantId } = useParams<{ grantId: string }>();
  const grant = useGrant(grantId);
  const problems = useProblemList(grantId);
  const evidence = useEvidence(grantId);
  const summary = grant.data?.summary;

  return (
    <AppShell
      workspaceId={summary?.grant.workspace_id ?? null}
      crumbs={[summary ? grantName(summary) : "Grant", "Terms"]}
    >
      <h1 className="ft-title">Grant terms</h1>
      <p className="ft-caption">Checks use only confirmed terms.</p>
      <Loadable result={grant}>
        {(detail) => (
          <Loadable result={problems}>
            {(list) => (
              <NoticeFilesProvider value={noticeFilesFor(detail.terms, evidence)}>
                <GrantTerms terms={detail.terms} rows={list.rows} />
              </NoticeFilesProvider>
            )}
          </Loadable>
        )}
      </Loadable>

      <section id="reusable-notes" className="ft-panel" aria-labelledby="notes-heading">
        <div className="ft-panel__head">
          <h2 id="notes-heading" className="ft-heading">
            Reusable notes
          </h2>
        </div>
        <Loadable result={grant}>{(detail) => <ReusableNotes notes={detail.reusable_notes ?? []} />}</Loadable>
      </section>
    </AppShell>
  );
}
