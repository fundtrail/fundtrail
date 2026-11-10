"use client";

import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { AddGrantForm } from "@/components/setup/AddGrantForm";
import { useWorkspaces } from "@/lib/api";

/** Adding a grant from its award letter. First version, may change. */
export function NewGrantScreen() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const workspace = useWorkspaces().data?.find((w) => w.id === workspaceId);

  return (
    <AppShell workspaceId={workspaceId} crumbs={[workspace?.name ?? "Workspace", "Add a grant"]}>
      <h1 className="ft-title">Add a grant</h1>
      <AddGrantForm workspaceId={workspaceId} />
    </AppShell>
  );
}
