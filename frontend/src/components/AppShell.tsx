"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useGrants, useWorkspaces, type Id, usePings } from "@/lib/api";
import { signedInWith, useAuth } from "@/lib/auth";
import { routes } from "@/lib/routes";
import { grantName } from "./GrantList";

function NavLink({
  href,
  children,
  count,
  grant = false,
}: {
  href: string;
  children: ReactNode;
  count?: number;
  grant?: boolean;
}) {
  const pathname = usePathname();
  const active = pathname === href;
  const className = `ft-nav__item${grant ? " ft-nav__item--grant" : ""}${active ? " is-active" : ""}`;
  return (
    <Link href={href} className={className} aria-current={active ? "page" : undefined}>
      <span>{children}</span>
      {count !== undefined && count > 0 && (
        <span className="ft-count ft-count--alert">
          {count}
          <span className="ft-sr"> on the problem list</span>
        </span>
      )}
    </Link>
  );
}

/**
 * One grant in the sidebar. While one of its pages is open, it is the current
 * grant and opens to its pages, read from the path against routes.ts.
 */
function GrantItem({ grantId, count, children }: { grantId: Id; count: number; children: ReactNode }) {
  const pathname = usePathname();
  const href = routes.grant(grantId);
  const current = pathname === href || pathname.startsWith(`${href}/`);
  return (
    <li>
      <NavLink href={href} count={count} grant={current}>
        {children}
      </NavLink>
      {current && (
        <ul className="ft-nav__children">
          <li>
            <NavLink href={routes.problemList(grantId)}>Problem list</NavLink>
          </li>
          <li>
            <NavLink href={routes.evidence(grantId)}>Evidence</NavLink>
          </li>
          <li>
            <NavLink href={routes.terms(grantId)}>Grant terms</NavLink>
          </li>
          <li>
            <NavLink href={routes.ledger(grantId)}>Ledger</NavLink>
          </li>
          <li>
            <NavLink href={routes.closeout(grantId)}>Closeout</NavLink>
          </li>
        </ul>
      )}
    </li>
  );
}

function Sidebar({ workspaceId }: { workspaceId: Id | null }) {
  const auth = useAuth();
  const workspaces = useWorkspaces();
  const grants = useGrants(workspaceId);
  // The grant list refetches when the backend pings this workspace's channel.
  usePings(workspaceId ? `workspace:${workspaceId}` : null);
  const workspace = workspaces.data?.find((w) => w.id === workspaceId);
  const user = auth.state.status === "signed_in" ? auth.state.user : null;

  return (
    <nav className="ft-sidebar" aria-label="Main">
      <div className="ft-wordmark">FundTrail</div>
      <div className="ft-sidebar__workspace">
        <span className="ft-label">Workspace</span>
        <span>{workspace?.name ?? "…"}</span>
      </div>
      {workspaceId && (
        <div className="ft-nav">
          <NavLink href={routes.workspace(workspaceId)}>Grants</NavLink>
          <ul className="ft-nav__grants">
            {grants.data?.map((g) => (
              <GrantItem key={g.grant.id} grantId={g.grant.id} count={g.on_problem_list}>
                {g.grant.award_number ?? grantName(g)}
              </GrantItem>
            ))}
          </ul>
          <NavLink href={routes.newGrant(workspaceId)}>Add a grant</NavLink>
          <NavLink href={routes.mail(workspaceId)}>Held mail</NavLink>
        </div>
      )}
      <div className="ft-sidebar__foot">
        {user && (
          <div className="ft-sidebar__account">
            <span>{user.name ?? user.email}</span>
            <span className="ft-caption">{user.email}</span>
            <span className="ft-caption">{signedInWith(user)}</span>
            <button type="button" className="ft-btn ft-btn--sm" onClick={() => void auth.signOut()}>
              Sign out
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}

/**
 * The frame of every signed-in screen: the sidebar, a top bar naming the page,
 * and the main area. Sends a signed-out user to the sign-in page.
 */
export function AppShell({
  workspaceId,
  crumbs,
  children,
}: {
  workspaceId: Id | null;
  crumbs: string[];
  children: ReactNode;
}) {
  const auth = useAuth();
  const router = useRouter();
  const signedOut = auth.state.status === "signed_out";

  useEffect(() => {
    if (signedOut) router.replace("/sign-in");
  }, [signedOut, router]);

  if (auth.state.status !== "signed_in") {
    return <p className="ft-empty">Loading…</p>;
  }
  return (
    <div className="ft-app">
      <Sidebar workspaceId={workspaceId} />
      <div className="ft-main">
        <div className="ft-topbar">
          <ol className="ft-crumbs" aria-label="Breadcrumbs">
            {crumbs.map((c, i) => (
              <li key={i} aria-current={i === crumbs.length - 1 ? "page" : undefined}>
                {c}
              </li>
            ))}
          </ol>
        </div>
        <main className="ft-content">{children}</main>
      </div>
    </div>
  );
}

/** Loading and error states for one piece of server data. */
export function Loadable<T>({
  result,
  children,
}: {
  result: { data?: T; error?: unknown; isLoading: boolean };
  children: (data: T) => ReactNode;
}) {
  if (result.error) {
    return (
      <p className="ft-error" role="alert">
        Couldn&apos;t load this. It reloads when the window regains focus.
      </p>
    );
  }
  if (result.data === undefined) return <p className="ft-empty">Loading…</p>;
  return <>{children(result.data)}</>;
}
