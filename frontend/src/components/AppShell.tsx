"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useGrants, useWorkspaces, type Id, usePings } from "@/lib/api";
import { signedInWith, useAuth } from "@/lib/auth";
import { useGrantDisplayName } from "@/lib/grantName";
import { routes } from "@/lib/routes";

/** The wordmark's glyph: a trail with a dot, a ring, a dashed stretch and the now diamond. */
function TrailMark() {
  return (
    <svg className="ft-wordmark__mark" width="30" height="16" viewBox="0 0 30 16" fill="none" aria-hidden="true">
      <path d="M3 8h9" stroke="currentColor" strokeWidth="2" />
      <path d="M15 8h6" stroke="currentColor" strokeWidth="2" strokeDasharray="2 2" />
      <circle cx="3.5" cy="8" r="3.5" fill="currentColor" />
      <circle cx="13" cy="8" r="2.6" fill="none" stroke="currentColor" strokeWidth="2" />
      <rect className="ft-wordmark__diamond" x="21.2" y="4.2" width="7.6" height="7.6" transform="rotate(45 25 8)" />
    </svg>
  );
}

/** A 16px stroke icon for a sidebar item, in the item's own color. */
function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="ft-nav__icon"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const icons = {
  grants: (
    <Icon>
      <path d="M2 6.5 8 2l6 4.5V14H2z" />
    </Icon>
  ),
  mail: (
    <Icon>
      <rect x="2" y="3.5" width="12" height="9" rx="1.5" />
      <path d="m2.5 4.5 5.5 4 5.5-4" />
    </Icon>
  ),
  problems: (
    <Icon>
      <path d="M6 4h8M6 8h8M6 12h8" />
      <circle cx="2.8" cy="4" r=".9" fill="currentColor" />
      <circle cx="2.8" cy="8" r=".9" fill="currentColor" />
      <circle cx="2.8" cy="12" r=".9" fill="currentColor" />
    </Icon>
  ),
  evidence: (
    <Icon>
      <path d="M4 1.8h5l3 3V14H4z" />
      <path d="M9 1.8v3h3" />
    </Icon>
  ),
  terms: (
    <Icon>
      <path d="M3 2h10v12H3z" />
      <path d="m5.5 8 1.8 1.8L10.5 6.5" />
    </Icon>
  ),
  ledger: (
    <Icon>
      <rect x="2" y="3" width="12" height="10" rx="1" />
      <path d="M2 6.5h12M2 9.8h12M6.5 3v10" />
    </Icon>
  ),
  closeout: (
    <Icon>
      <circle cx="8" cy="8" r="6" />
      <path d="m5.2 8.2 2 2 3.6-4" />
    </Icon>
  ),
  add: (
    <Icon>
      <path d="M8 3v10M3 8h10" />
    </Icon>
  ),
};

/**
 * Where a link stands against the page that is open: the page itself, the
 * page one level above it (a charge under the problem list), or neither.
 */
type Current = "page" | "parent" | null;

function NavLink({
  href,
  children,
  icon,
  count,
  current,
  quiet = false,
  title,
}: {
  href: string;
  children: ReactNode;
  icon?: ReactNode;
  count?: number;
  /** Set by the caller when the path alone can't tell; otherwise the exact path decides. */
  current?: Current;
  quiet?: boolean;
  title?: string;
}) {
  const pathname = usePathname();
  const where: Current = current !== undefined ? current : pathname === href ? "page" : null;
  const className = `ft-nav__item${quiet ? " ft-nav__item--quiet" : ""}${where ? " is-active" : ""}`;
  return (
    <Link
      href={href}
      className={className}
      aria-current={where === "page" ? "page" : where === "parent" ? "true" : undefined}
      title={title}
    >
      {icon}
      <span className="ft-nav__text">{children}</span>
      {count !== undefined && count > 0 && (
        <span className="ft-count ft-count--alert">
          {count}
          <span className="ft-sr"> on the problem list</span>
        </span>
      )}
    </Link>
  );
}

/** A route without its hash: the path usePathname() reports for that page. */
function pathOf(href: string): string {
  const hash = href.indexOf("#");
  return hash === -1 ? href : href.slice(0, hash);
}

/** The page itself, a page under it, or neither. */
function standing(pathname: string, href: string, under: string[] = [pathOf(href)]): Current {
  if (pathname === pathOf(href)) return "page";
  if (under.some((prefix) => pathname.startsWith(`${prefix}/`))) return "parent";
  return null;
}

/** True while the path is the grant's page or any page under it. */
function isInside(pathname: string, grantId: Id): boolean {
  const href = routes.grant(grantId);
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * The open grant's pages, under a quiet label with its name. The open page is
 * marked, or the page above it: the grant page is the problem list, and a
 * charge or a record sits under it. All of it is read from the path against
 * routes.ts.
 */
function GrantPages({ grantId, name, count }: { grantId: Id; name: string; count: number }) {
  const pathname = usePathname();
  const grant = routes.grant(grantId);
  const page = (href: string) => standing(pathname, href);
  return (
    <div className="ft-nav__section">
      <span className="ft-nav__label" title={name}>
        {name}
      </span>
      <ul>
        <li>
          <NavLink
            href={routes.problemList(grantId)}
            icon={icons.problems}
            count={count}
            current={standing(pathname, routes.problemList(grantId), [`${grant}/charges`, `${grant}/records`])}
          >
            Problem list
          </NavLink>
        </li>
        <li>
          <NavLink href={routes.evidence(grantId)} icon={icons.evidence} current={page(routes.evidence(grantId))}>
            Evidence
          </NavLink>
        </li>
        <li>
          <NavLink href={routes.terms(grantId)} icon={icons.terms} current={page(routes.terms(grantId))}>
            Grant terms
          </NavLink>
        </li>
        <li>
          <NavLink href={routes.ledger(grantId)} icon={icons.ledger} current={page(routes.ledger(grantId))}>
            Ledger
          </NavLink>
        </li>
        <li>
          <NavLink href={routes.closeout(grantId)} icon={icons.closeout} current={page(routes.closeout(grantId))}>
            Closeout
          </NavLink>
        </li>
      </ul>
    </div>
  );
}

function Sidebar({ workspaceId }: { workspaceId: Id | null }) {
  const grantName = useGrantDisplayName();
  const auth = useAuth();
  const pathname = usePathname();
  const workspaces = useWorkspaces();
  const grants = useGrants(workspaceId);
  // The grant list refetches when the backend pings this workspace's channel.
  usePings(workspaceId ? `workspace:${workspaceId}` : null);
  const workspace = workspaces.data?.find((w) => w.id === workspaceId);
  const user = auth.state.status === "signed_in" ? auth.state.user : null;
  const open = grants.data?.find((g) => isInside(pathname, g.grant.id));
  // On a grant's page, wait for its name rather than flash the grants list.
  const onGrantPage = pathname.startsWith(routes.grant(""));

  return (
    <nav className="ft-sidebar" aria-label="Main">
      <div className="ft-wordmark">
        <TrailMark />
        FundTrail
      </div>
      <div className="ft-sidebar__workspace">
        <span className="ft-label">Workspace</span>
        <span title={workspace?.name}>{workspace?.name ?? "…"}</span>
      </div>
      {workspaceId && (
        <div className="ft-nav">
          <ul>
            <li>
              <NavLink href={routes.workspace(workspaceId)} icon={icons.grants}>
                All grants
              </NavLink>
            </li>
            <li>
              <NavLink href={routes.mail(workspaceId)} icon={icons.mail}>
                Held mail
              </NavLink>
            </li>
          </ul>
          {open ? (
            <GrantPages
              grantId={open.grant.id}
              name={open.grant.award_number ?? grantName(open)}
              count={open.on_problem_list}
            />
          ) : (
            !onGrantPage && (
              <div className="ft-nav__section">
                <span className="ft-nav__label">Grants</span>
                <ul className="ft-nav__grants">
                  {grants.data?.map((g) => {
                    const name = g.grant.award_number ?? grantName(g);
                    return (
                      <li key={g.grant.id}>
                        <NavLink href={routes.grant(g.grant.id)} count={g.on_problem_list} title={name}>
                          {name}
                        </NavLink>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )
          )}
          <ul>
            <li>
              <NavLink href={routes.newGrant(workspaceId)} icon={icons.add} quiet>
                Add a grant
              </NavLink>
            </li>
          </ul>
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
