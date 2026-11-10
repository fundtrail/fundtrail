"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useWorkspaces } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Opens the first workspace's grant list, or the sign-in page when signed out. */
export default function Home() {
  const auth = useAuth();
  const router = useRouter();
  const signedIn = auth.state.status === "signed_in";
  const workspaces = useWorkspaces();
  const first = signedIn ? workspaces.data?.[0]?.id : undefined;

  useEffect(() => {
    if (auth.state.status === "signed_out") router.replace("/sign-in");
    else if (first) router.replace(`/w/${encodeURIComponent(first)}`);
  }, [auth.state.status, first, router]);

  if (signedIn && workspaces.error) {
    return (
      <p className="ft-error" role="alert">
        Couldn&apos;t load your workspaces. They reload when the window regains focus.
      </p>
    );
  }
  if (signedIn && workspaces.data?.length === 0) {
    return <p className="ft-empty">No workspace yet.</p>;
  }
  return <p className="ft-empty">Loading…</p>;
}
