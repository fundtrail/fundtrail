"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Loadable } from "@/components/Loadable";
import { GrantList } from "@/components/GrantList";
import { TrailStart } from "@/components/TrailMark";
import { ApiError, useGrants, useWorkspaces } from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import { routes } from "@/lib/routes";
import styles from "./workspace.module.css";

/**
 * A workspace with no grants yet: what to do first, on the page itself. The
 * line says only what the Add a grant page and the product docs say.
 */
function NoGrants({ workspaceId }: { workspaceId: string }) {
  return (
    <section className={`ft-panel ${styles.empty}`} aria-labelledby="no-grants">
      <TrailStart className={styles.emptyMark} classes={styles} />
      <h2 id="no-grants" className={styles.emptyTitle}>
        No grants in this workspace yet.
      </h2>
      <p className={styles.emptyLine}>
        Add your own grant from its award letter: the agent reads its terms, and you confirm them before any check uses them. Or
        add a sample grant to try FundTrail on.
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
  const workspaces = useWorkspaces();
  const workspace = workspaces.data?.find((w) => w.id === workspaceId);
  // The title says where the workspace stands until it has loaded: loading, or the
  // same words Loadable uses when a request fails or the workspace isn't the user's.
  const missing = workspaces.error
    ? describeError(workspaces.error).message
    : workspaces.data && !workspace
      ? describeError(new ApiError(404, "Not Found")).message
      : null;
  // Add a grant takes one place, decided once everything has loaded: the header
  // when the workspace has grants, the empty state when it has none.
  const hasGrants = !!workspace && !!grants.data && grants.data.length > 0;

  return (
    <AppShell workspaceId={workspaceId} crumbs={[workspace?.name ?? "Workspace", "All grants"]}>
      <header className={styles.head}>
        {workspace ? (
          <h1 className={styles.title}>
            <span className="ft-sr">Grants in</span> {workspace.name}
          </h1>
        ) : missing ? (
          <h1 className={`${styles.title} ${styles.titleProblem}`}>
            <span role="alert">{missing}</span>
          </h1>
        ) : (
          <h1 className={`${styles.title} ${styles.titleWaiting}`}>Loading…</h1>
        )}
        {hasGrants && (
          <Link className="ft-btn ft-btn--main" href={routes.newGrant(workspaceId)}>
            Add a grant
          </Link>
        )}
      </header>
      {workspace && (
        <Loadable result={grants}>
          {(data) => (data.length === 0 ? <NoGrants workspaceId={workspaceId} /> : <GrantList grants={data} />)}
        </Loadable>
      )}
    </AppShell>
  );
}
