"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useClock, useGrants, useWorkspaces, type Id } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { date } from "@/lib/format";
import { routes } from "@/lib/routes";
import { grantName } from "./GrantList";

function NavLink({ href, children, count }: { href: string; children: ReactNode; count?: number }) {
  const pathname = usePathname();
  const active = pathname === href;
  return (
    <Link href={href} className={`ft-nav__item${active ? " is-active" : ""}`} aria-current={active ? "page" : undefined}>
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

function Sidebar({ workspaceId }: { workspaceId: Id | null }) {
  const auth = useAuth();
  const workspaces = useWorkspaces();
  const grants = useGrants(workspaceId);
  const clock = useClock(workspaceId);
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
              <li key={g.grant.id}>
                <NavLink href={routes.grant(g.grant.id)} count={g.on_problem_list}>
                  {g.grant.award_number ?? grantName(g)}
                </NavLink>
              </li>
            ))}
          </ul>
          <NavLink href={routes.newGrant(workspaceId)}>Add a grant</NavLink>
          <NavLink href={routes.mail(workspaceId)}>Held mail</NavLink>
        </div>
      )}
      <div className="ft-sidebar__foot">
        <div className="ft-sidebar__clock">
          <span className="ft-label">Clock</span>
          {clock.data ? (
            <span className="ft-num">
              {date(clock.data.now)}
              {clock.data.simulated && <span className="ft-caption"> · demo clock</span>}
            </span>
          ) : (
            <span className="ft-caption">…</span>
          )}
        </div>
        {user && (
          <div className="ft-sidebar__account">
            <span>{user.name ?? user.email}</span>
            <span className="ft-caption">{user.email}</span>
            <span className="ft-caption">{auth.fake ? "Fake sign-in, no Supabase project" : "Signed in with Google"}</span>
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
