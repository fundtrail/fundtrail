"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell, Loadable } from "@/components/AppShell";
import { CloseoutCharges } from "@/components/closeout/CloseoutCharges";
import { CloseoutSteps } from "@/components/closeout/CloseoutSteps";
import { ReportDraft } from "@/components/closeout/ReportDraft";
import { SignOffPanel } from "@/components/closeout/SignOffPanel";
import { SnoozedCharges } from "@/components/closeout/SnoozedCharges";
import { GrantHeader } from "@/components/GrantHeader";
import { grantName } from "@/components/GrantList";
import { ProblemList } from "@/components/ProblemList";
import { useCharges, useGrant, useProblemList, useRefresh } from "@/lib/api";
import { routes } from "@/lib/routes";

/**
 * A grant's closeout view (decision 0022, product.md Closeout): the closeout
 * steps in order, what's still open, every expense with its bucket, evidence
 * and history, the evidence report and the sign-off. First version, may change.
 */
export function CloseoutScreen() {
  const { grantId } = useParams<{ grantId: string }>();
  const grant = useGrant(grantId);
  const problems = useProblemList(grantId);
  const charges = useCharges(grantId);
  const refresh = useRefresh();
  const summary = grant.data?.summary;

  return (
    <AppShell
      workspaceId={summary?.grant.workspace_id ?? null}
      crumbs={[summary ? grantName(summary) : "Grant", "Closeout"]}
    >
      <Loadable result={grant}>{(data) => <GrantHeader summary={data.summary} />}</Loadable>
      <p className="ft-caption">
        <Link className="ft-link" href={routes.grant(grantId)}>
          Back to the grant
        </Link>
        {" · "}
        <Link className="ft-link" href={routes.ledger(grantId)}>
          Upload the ledger file
        </Link>
      </p>

      <Loadable result={grant}>{(data) => <CloseoutSteps summary={data.summary} />}</Loadable>

      <section className="ft-panel" aria-labelledby="open-heading">
        <div className="ft-panel__head">
          <h2 id="open-heading" className="ft-heading">
            Still open
          </h2>
        </div>
        <Loadable result={problems}>
          {(data) =>
            data.rows.length === 0 ? (
              <p className="ft-empty">Nothing is on the problem list.</p>
            ) : (
              <ProblemList rows={data.rows} charges={Object.fromEntries((charges.data ?? []).map((r) => [r.charge.id, r.charge]))} />
            )
          }
        </Loadable>
        {charges.data && <SnoozedCharges grantId={grantId} rows={charges.data} />}
      </section>

      <section className="ft-panel" aria-labelledby="expenses-heading">
        <div className="ft-panel__head">
          <h2 id="expenses-heading" className="ft-heading">
            Every expense
          </h2>
        </div>
        <Loadable result={charges}>{(rows) => <CloseoutCharges grantId={grantId} rows={rows} />}</Loadable>
      </section>

      <Loadable result={grant}>{(data) => <ReportDraft grantId={grantId} signOff={data.sign_off} />}</Loadable>

      <Loadable result={grant}>
        {(data) => <SignOffPanel grantId={grantId} signOff={data.sign_off} onSigned={() => refresh()} />}
      </Loadable>
    </AppShell>
  );
}
