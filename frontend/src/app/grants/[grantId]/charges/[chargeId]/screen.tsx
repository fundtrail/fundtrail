"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Loadable } from "@/components/Loadable";
import { ChargeDetailView, type ChargeLinks } from "@/components/charge/ChargeDetailView";
import { useGrantDisplayName } from "@/lib/grantName";
import { useThreadActions } from "@/components/thread/useThreadActions";
import { useCharge, useChargeThread, useGrant, usePings } from "@/lib/api";
import { routes } from "@/lib/routes";

/**
 * A charge's page: the charge and its bucket, the server's reasons, its
 * evidence checklist, the bills covering it, the answers about it, its status
 * history, and its review thread. First version; the screens may change.
 */
export function ChargeScreen() {
  const grantName = useGrantDisplayName();
  const { grantId, chargeId } = useParams<{ grantId: string; chargeId: string }>();
  // Refetches when the backend pings this grant's channel, such as the agent replying in a thread.
  usePings(`grant:${grantId}`);
  const grant = useGrant(grantId);
  const detail = useCharge(chargeId);
  // The thread has its own route too. The page shows that one, so a message
  // posted shows up without waiting on the whole charge; until it loads, the
  // charge's own copy stands in.
  const thread = useChargeThread(chargeId);
  const actions = useThreadActions(grantId, { chargeId });
  const summary = grant.data?.summary;
  const line = detail.data?.charge.ledger_line_id;

  // The viewer is its own screen. These open the file; highlighting a link's
  // part or a quote there is the viewer's to do.
  const links: ChargeLinks = {
    link: (view) => (view.file ? routes.file(grantId, view.file.id) : undefined),
    quote: (citation) => routes.file(grantId, citation.file_id),
    file: (fileId) => routes.file(grantId, fileId),
  };

  return (
    <AppShell
      workspaceId={summary?.grant.workspace_id ?? null}
      crumbs={[summary ? grantName(summary) : "Grant", line ?? "Charge"]}
    >
      <p>
        <Link className="ft-link" href={routes.grant(grantId)}>
          Back to the grant
        </Link>
      </p>
      <Loadable result={detail}>
        {(data) => (
          <ChargeDetailView
            detail={thread.data ? { ...data, thread: thread.data } : data}
            onDecide={actions.decide}
            onWrite={actions.write}
            onAsk={actions.ask}
            links={links}
          />
        )}
      </Loadable>
    </AppShell>
  );
}
