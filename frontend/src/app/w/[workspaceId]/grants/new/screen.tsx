"use client";

import { useParams, useRouter } from "next/navigation";
import { AppShell, Loadable } from "@/components/AppShell";
import { AddGrantForm } from "@/components/setup/AddGrantForm";
import { SampleCard } from "@/components/setup/SampleCard";
import { useApi, useRefresh, useSamples, useWorkspaces } from "@/lib/api";
import { routes } from "@/lib/routes";

/**
 * Adding a grant: the accountant's own, from its award letter, or a sample,
 * which opens as one grant in this workspace. First version, may change.
 */
export function NewGrantScreen() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const router = useRouter();
  const api = useApi();
  const refresh = useRefresh();
  const workspace = useWorkspaces().data?.find((w) => w.id === workspaceId);
  const samples = useSamples();

  return (
    <AppShell workspaceId={workspaceId} crumbs={[workspace?.name ?? "Workspace", "Add a grant"]}>
      <h1 className="ft-title">Add a grant</h1>
      <div className="ft-cards">
        <AddGrantForm workspaceId={workspaceId} />
        <Loadable result={samples}>
          {(options) => (
            <SampleCard
              options={options}
              openSample={(body) => api.createSample(workspaceId, body)}
              onOpened={(grantId) => {
                void refresh();
                router.push(routes.grant(grantId));
              }}
            />
          )}
        </Loadable>
      </div>
    </AppShell>
  );
}
