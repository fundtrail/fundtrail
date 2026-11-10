"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Loadable } from "@/components/AppShell";
import { ConfirmValues } from "@/components/evidence/ConfirmValues";
import { GrantFrame } from "@/components/evidence/GrantFrame";
import { useEvidence } from "@/components/evidence/hooks";
import { evidenceHref } from "@/components/evidence/links";
import { useRefresh } from "@/lib/api";
import { recordKindLabel } from "@/lib/format";

/** Confirm or correct the values of one record that couldn't be found: `?record=<record id>` (first version, may change). */
export function ConfirmScreen() {
  const { grantId, fileId } = useParams<{ grantId: string; fileId: string }>();
  const recordId = useSearchParams().get("record");
  const evidence = useEvidence(grantId);
  const refresh = useRefresh();
  const router = useRouter();

  return (
    <GrantFrame grantId={grantId} crumbs={["Evidence", "Confirm values"]}>
      <p>
        <Link className="ft-link" href={evidenceHref(grantId)}>
          All evidence
        </Link>
      </p>
      <Loadable result={evidence}>
        {(cards) => {
          const card = cards.find((c) => c.file.id === fileId);
          const fact = card?.facts?.find((f) => f.record.id === recordId);
          if (!card || !fact) return <p className="ft-empty">This record isn&apos;t on this file.</p>;
          return (
            <>
              <h1 className="ft-title">
                Confirm values: {recordKindLabel(fact.record.data.kind)} from {card.file.name}
              </h1>
              <p className="ft-caption" style={{ marginBottom: "var(--space-4)" }}>
                These values couldn&apos;t be confirmed in the file. Confirm each as read, or type the right one.
              </p>
              <ConfirmValues
                grantId={grantId}
                fileId={fileId}
                fact={fact}
                onDone={() => {
                  void refresh();
                  router.push(evidenceHref(grantId));
                }}
              />
            </>
          );
        }}
      </Loadable>
    </GrantFrame>
  );
}
