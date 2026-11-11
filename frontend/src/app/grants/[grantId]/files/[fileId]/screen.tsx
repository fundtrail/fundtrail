"use client";

import Link from "next/link";
import { usePings } from "@/lib/api";
import { useParams, useSearchParams } from "next/navigation";
import { Loadable } from "@/components/Loadable";
import { findCitation } from "@/components/evidence/findCitation";
import { GrantFrame } from "@/components/evidence/GrantFrame";
import { useEvidence, useFileLink } from "@/components/evidence/hooks";
import { evidenceHref } from "@/components/evidence/links";
import { Viewer } from "@/components/viewer/Viewer";

/**
 * One file in the viewer, opened at a value when the query names one:
 * `?record=<record id>&value=<path>` (first version, may change).
 */
export function FileScreen() {
  const { grantId, fileId } = useParams<{ grantId: string; fileId: string }>();
  // Refetches when the backend pings this grant's channel, such as the agent replying in a thread.
  usePings(`grant:${grantId}`);
  const query = useSearchParams();
  const recordId = query.get("record");
  const path = query.get("value");
  const evidence = useEvidence(grantId);
  const link = useFileLink(fileId);
  const card = evidence.data?.find((c) => c.file.id === fileId);

  return (
    <GrantFrame grantId={grantId} crumbs={["Evidence", card?.file.name ?? "File"]}>
      <p>
        <Link className="ft-link" href={evidenceHref(grantId)}>
          All evidence
        </Link>
      </p>
      <Loadable result={evidence}>
        {(cards) => {
          const found = cards.find((c) => c.file.id === fileId);
          if (!found) return <p className="ft-empty">This file isn&apos;t on this grant.</p>;
          const spot = recordId && path ? findCitation(cards, recordId, path) : null;
          return (
            <Loadable result={link}>
              {(fileLink) => (
                <Viewer
                  key={`${recordId}:${path}`}
                  file={found.file}
                  url={fileLink.url}
                  citation={spot?.citation.file_id === fileId ? spot.citation : null}
                  valueText={spot?.valueText ?? null}
                  label={spot?.label ?? null}
                  confirmation={spot?.confirmation ?? null}
                  reading={fileLink.reading ?? null}
                />
              )}
            </Loadable>
          );
        }}
      </Loadable>
    </GrantFrame>
  );
}
