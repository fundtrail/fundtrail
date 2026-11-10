"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { grantName } from "@/components/GrantList";
import { useGrant } from "@/lib/api";
import { routes } from "@/lib/routes";
import { LedgerUpload } from "./LedgerUpload";

/** A grant's ledger upload page. First version, may change. */
export function LedgerScreen() {
  const { grantId } = useParams<{ grantId: string }>();
  const grant = useGrant(grantId);
  const summary = grant.data?.summary;

  return (
    <AppShell
      workspaceId={summary?.grant.workspace_id ?? null}
      crumbs={[summary ? grantName(summary) : "Grant", "Ledger file"]}
    >
      <h1 className="ft-title">Upload the ledger file</h1>
      <p className="ft-caption">
        Each row becomes one charge.{" "}
        <Link className="ft-link" href={routes.grant(grantId)}>
          Back to the grant
        </Link>
      </p>
      <LedgerUpload grantId={grantId} />
    </AppShell>
  );
}
