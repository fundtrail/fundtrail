"use client";

import { useParams } from "next/navigation";
import { AppShell, Loadable } from "@/components/AppShell";
import { GrantList } from "@/components/GrantList";
import { useGrants, useWorkspaces } from "@/lib/api";

/** The workspace's grant list. */
export function WorkspaceScreen() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const grants = useGrants(workspaceId);
  const workspace = useWorkspaces().data?.find((w) => w.id === workspaceId);

  return (
    <AppShell workspaceId={workspaceId} crumbs={[workspace?.name ?? "Workspace", "Grants"]}>
      <Loadable result={grants}>{(data) => <GrantList grants={data} />}</Loadable>
    </AppShell>
  );
}
