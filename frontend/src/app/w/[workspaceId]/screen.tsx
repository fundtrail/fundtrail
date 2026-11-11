"use client";

import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Loadable } from "@/components/Loadable";
import { GrantList } from "@/components/GrantList";
import { useGrants, useWorkspaces } from "@/lib/api";

/** The workspace's grant list. */
export function WorkspaceScreen() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const grants = useGrants(workspaceId);
  const workspace = useWorkspaces().data?.find((w) => w.id === workspaceId);

  return (
    <AppShell workspaceId={workspaceId} crumbs={[workspace?.name ?? "Workspace", "Grants"]}>
      <h1 className="ft-sr">Grants in {workspace?.name ?? "this workspace"}</h1>
      <Loadable result={grants}>{(data) => <GrantList grants={data} />}</Loadable>
    </AppShell>
  );
}
