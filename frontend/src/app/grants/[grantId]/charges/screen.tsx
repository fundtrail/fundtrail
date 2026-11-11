"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ChargesTable } from "@/components/ChargesTable";
import { Loadable } from "@/components/Loadable";
import { useGrantDisplayName } from "@/lib/grantName";
import { useCharges, useGrant, usePings } from "@/lib/api";
import { routes } from "@/lib/routes";
import styles from "./charges.module.css";

/** Every charge on the grant, in the server's order, each opening its charge page. */
export function ChargesScreen() {
  const grantName = useGrantDisplayName();
  const { grantId } = useParams<{ grantId: string }>();
  // Everything on the page refetches when the backend pings this grant's channel.
  usePings(`grant:${grantId}`);
  const grant = useGrant(grantId);
  const charges = useCharges(grantId);
  const summary = grant.data?.summary;

  return (
    <AppShell workspaceId={summary?.grant.workspace_id ?? null} crumbs={[summary ? grantName(summary) : "Grant", "Charges"]}>
      <div className={styles.page}>
        <header className={styles.head}>
          {summary && (
            <Link className={styles.crumb} href={routes.grant(grantId)}>
              {grantName(summary)}
            </Link>
          )}
          <h1 className={styles.title}>
            Charges
            {charges.data && <span className={`ft-num ${styles.count}`}>{charges.data.length}</span>}
          </h1>
        </header>
        <Loadable result={charges}>{(rows) => <ChargesTable rows={rows} />}</Loadable>
      </div>
    </AppShell>
  );
}
