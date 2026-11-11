"use client";

import { useParams } from "next/navigation";
import useSWR from "swr";
import { AppShell } from "@/components/AppShell";
import { Loadable } from "@/components/Loadable";
import { grantName } from "@/components/GrantList";
import { HeldMailList } from "@/components/mail/HeldMailList";
import { useApi, useGrants, useWorkspaces } from "@/lib/api";
import { useUserId } from "@/lib/auth";
import page from "../workspace.module.css";

/**
 * The workspace's held mail (decision 0025), gathered from each grant's
 * problem list by the client. First version, may change.
 */
export function HeldMailScreen() {
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
      <header className={page.intro}>
        <h1 className={page.title}>Held mail</h1>
        <p className={page.lede}>
          Mail from senders who aren&apos;t known is held: stored, unread by the agent, and used by no check until you let it in.
        </p>
      </header>
      <section className="ft-panel" aria-label="Held mail">
        <Loadable result={mail}>{(data) => <HeldMailList mail={data} grantNames={names} />}</Loadable>
      </section>
    </AppShell>
  );
}
