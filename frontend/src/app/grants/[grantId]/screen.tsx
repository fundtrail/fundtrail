"use client";

import { useParams } from "next/navigation";
import { AppShell, Loadable } from "@/components/AppShell";
import { BudgetFigures } from "@/components/BudgetFigures";
import { ChargesTable } from "@/components/ChargesTable";
import { GrantHeader } from "@/components/GrantHeader";
import { grantName } from "@/components/GrantList";
import { ProblemList } from "@/components/ProblemList";
import { SampleTimeline } from "@/components/timeline/TimelinePanel";
import { useCharges, useGrant, useProblemList } from "@/lib/api";

/**
 * A grant's page: where it stands, a sample grant's timeline, its problem list,
 * its budget figures with the grant notes, and every charge. Each part is its own request, so a refetch of
 * one doesn't wait on the others.
 */
export function GrantScreen() {
  const { grantId } = useParams<{ grantId: string }>();
  const grant = useGrant(grantId);
  const problems = useProblemList(grantId);
  const charges = useCharges(grantId);
  const summary = grant.data?.summary;

  return (
    <AppShell workspaceId={summary?.grant.workspace_id ?? null} crumbs={[summary ? grantName(summary) : "Grant"]}>
      <Loadable result={grant}>{(data) => <GrantHeader summary={data.summary} />}</Loadable>

      {/* Only a sample grant has a timeline to play. */}
      {grant.data && <SampleTimeline summary={grant.data.summary} />}

      <section id="problem-list" className="ft-panel" aria-labelledby="problems-heading">
        <div className="ft-panel__head">
          <h2 id="problems-heading" className="ft-heading">
            Problem list
          </h2>
        </div>
        <Loadable result={problems}>{(data) => <ProblemList rows={data.rows} />}</Loadable>
      </section>

      <Loadable result={grant}>
        {(data) => <BudgetFigures budget={data.budget} notes={data.grant_notes} />}
      </Loadable>

      <section className="ft-panel" aria-labelledby="charges-heading">
        <div className="ft-panel__head">
          <h2 id="charges-heading" className="ft-heading">
            Charges
          </h2>
        </div>
        <Loadable result={charges}>
          {(rows) => <ChargesTable rows={rows} />}
        </Loadable>
      </section>
    </AppShell>
  );
}
