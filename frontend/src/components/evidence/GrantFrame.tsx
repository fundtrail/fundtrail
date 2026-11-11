"use client";

import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { useGrant, type Id } from "@/lib/api";
import { useGrantDisplayName } from "@/lib/grantName";

/** The app frame for the evidence screens, with the grant's name first in the breadcrumbs. */
export function GrantFrame({ grantId, crumbs, children }: { grantId: Id; crumbs: string[]; children: ReactNode }) {
  const grantName = useGrantDisplayName();
  const grant = useGrant(grantId);
  const summary = grant.data?.summary;
  return (
    <AppShell workspaceId={summary?.grant.workspace_id ?? null} crumbs={[summary ? grantName(summary) : "Grant", ...crumbs]}>
      {children}
    </AppShell>
  );
}
