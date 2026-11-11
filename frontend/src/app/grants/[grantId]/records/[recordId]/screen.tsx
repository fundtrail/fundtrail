"use client";

import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Loadable } from "@/components/Loadable";
import { grantName } from "@/components/GrantList";
import { RecordThreadView } from "@/components/thread/RecordThreadView";
import { useThreadActions } from "@/components/thread/useThreadActions";
import { useEvidence, useGrant, useProblemList, useRecords, useRecordThread, type EvidenceFile, type Id, usePings } from "@/lib/api";
import { routes } from "@/lib/routes";

/**
 * A record's thread: the record, its own problems, and the review thread with
 * the agent's suggestions and the box for asking the agent. First version; the
 * screens may change.
 */
export function RecordThreadScreen() {
  const { grantId, recordId } = useParams<{ grantId: string; recordId: string }>();
  // Refetches when the backend pings this grant's channel, such as the agent replying in a thread.
  usePings(`grant:${grantId}`);
  const grant = useGrant(grantId);
  const problems = useProblemList(grantId);
  const records = useRecords(grantId);
  const evidence = useEvidence(grantId);
  const thread = useRecordThread(recordId);
  const actions = useThreadActions(grantId, { recordId });
  const summary = grant.data?.summary;

  const view = records.data?.find((r) => r.record.id === recordId) ?? null;
  const row = problems.data?.rows.find((r) => r.kind === "record" && r.status.record_id === recordId);
  const status = row?.kind === "record" ? row.status : null;
  const files: Record<Id, EvidenceFile> = {};
  for (const card of evidence.data ?? []) files[card.file.id] = card.file;

  return (
    <AppShell workspaceId={summary?.grant.workspace_id ?? null} crumbs={[summary ? grantName(summary) : "Grant", "Record"]}>
      <Loadable result={thread}>
        {(data) => (
          <RecordThreadView
            recordId={recordId}
            record={view?.record ?? null}
            state={view?.state ?? null}
            status={status}
            files={files}
            thread={data}
            fileHref={(fileId) => routes.file(grantId, fileId)}
            quoteHref={(citation) => routes.file(grantId, citation.file_id)}
            onDecide={actions.decide}
            onAsk={actions.ask}
          />
        )}
      </Loadable>
    </AppShell>
  );
}
