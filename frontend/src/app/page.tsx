"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useRefresh, useWorkspaces } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { routes } from "@/lib/routes";

/**
 * Opens the first workspace's grant list, or the sign-in page when signed out.
 * Ruling 64: every user's first workspace is created when they first sign in,
 * so a signed-in user with no workspace, or a failed request, is an error.
 */
export default function Home() {
  const auth = useAuth();
  const router = useRouter();
  const refresh = useRefresh();
  const signedIn = auth.state.status === "signed_in";
  const workspaces = useWorkspaces();
  const first = signedIn ? workspaces.data?.[0]?.id : undefined;

  useEffect(() => {
    if (auth.state.status === "signed_out") router.replace(routes.signIn());
    else if (first) router.replace(routes.workspace(first));
  }, [auth.state.status, first, router]);

  const failed = signedIn && (workspaces.error || workspaces.data?.length === 0);
  if (failed) {
    return (
      <div className="ft-empty" role="alert">
        <p className="ft-error">
          {workspaces.error ? "Couldn't load your workspace." : "Your workspace wasn't set up when you signed in."}
        </p>
        <p>
          <button type="button" className="ft-btn ft-btn--sm" onClick={() => void refresh()}>
            Try again
          </button>
        </p>
      </div>
    );
  }
  return <p className="ft-empty">Loading…</p>;
}
