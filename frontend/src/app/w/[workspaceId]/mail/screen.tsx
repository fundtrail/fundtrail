"use client";

import { useParams } from "next/navigation";
import useSWR from "swr";
import { AppShell } from "@/components/AppShell";
import { Loadable } from "@/components/Loadable";
import { useGrantDisplayName } from "@/lib/grantName";
import { HeldMailList } from "@/components/mail/HeldMailList";
import { useApi, useGrants, useWorkspaces } from "@/lib/api";
import { useUserId } from "@/lib/auth";

/**
 * The workspace's held mail (decision 0025), gathered from each grant's
 * problem list by the client. First version, may change.
 */
export function HeldMailScreen() {
  const grantName = useGrantDisplayName();
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const api = useApi();
  const userId = useUserId();
  const workspace = useWorkspaces().data?.find((w) => w.id === workspaceId);
  const grants = useGrants(workspaceId);
  // Keyed by the signed-in user, like every other request, so one user's mail is never shown to another.
  const mail = useSWR(userId ? [userId, "held-mail", workspaceId] : null, () => api.listHeldMail(workspaceId));
  const names = Object.fromEntries((grants.data ?? []).map((g) => [g.grant.id, grantName(g)]));

  return (
    <AppShell workspaceId={workspaceId} crumbs={[workspace?.name ?? "Workspace", "Held mail"]}>
      <h1 className="ft-title">Held mail</h1>
      <p className="ft-caption">
        Mail from senders who aren&apos;t known is held: stored, unread by the agent, and used by no check until you let it in.
      </p>
      <section className="ft-panel" aria-label="Held mail">
        <Loadable result={mail}>{(data) => <HeldMailList mail={data} grantNames={names} />}</Loadable>
      </section>
    </AppShell>
  );
}
