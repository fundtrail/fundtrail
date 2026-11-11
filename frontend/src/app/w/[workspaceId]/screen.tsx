"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Loadable } from "@/components/Loadable";
import { GrantList } from "@/components/GrantList";
import { TrailStart } from "@/components/TrailMark";
import { useGrants, useWorkspaces } from "@/lib/api";
import { routes } from "@/lib/routes";
import styles from "./workspace.module.css";

/**
 * A workspace with no grants yet: what to do first, on the page itself. The
 * line says only what the Add a grant page says.
 */
function NoGrants({ workspaceId }: { workspaceId: string }) {
  return (
    <section className={`ft-panel ${styles.empty}`} aria-labelledby="no-grants">
      <TrailStart className={styles.emptyMark} classes={styles} />
      <h2 id="no-grants" className={styles.emptyTitle}>
        No grants in this workspace yet.
      </h2>
      <p className={styles.emptyLine}>
        Add your own grant from its award letter, and the agent reads its terms. Or add a sample grant to try FundTrail on.
      </p>
      <Link className="ft-btn ft-btn--main" href={routes.newGrant(workspaceId)}>
        Add a grant
      </Link>
    </section>
  );
}

/** The workspace's grant list. */
export function WorkspaceScreen() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const grants = useGrants(workspaceId);
  const workspace = useWorkspaces().data?.find((w) => w.id === workspaceId);
  // An empty workspace offers Add a grant in its empty state instead, so the page keeps one main action.
  const empty = grants.data?.length === 0;

  return (
    <AppShell workspaceId={workspaceId} crumbs={[workspace?.name ?? "Workspace", "Grants"]}>
      <header className={styles.head}>
        <h1 className={styles.title}>
          <span className="ft-sr">Grants in </span>
          {workspace?.name ?? <span className="ft-sr">this workspace</span>}
        </h1>
        {!empty && (
          <Link className="ft-btn ft-btn--main" href={routes.newGrant(workspaceId)}>
            Add a grant
          </Link>
        )}
      </header>
      <Loadable result={grants}>
        {(data) => (data.length === 0 ? <NoGrants workspaceId={workspaceId} /> : <GrantList grants={data} />)}
      </Loadable>
    </AppShell>
  );
}
