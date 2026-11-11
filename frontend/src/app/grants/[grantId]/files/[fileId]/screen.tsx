"use client";

import Link from "next/link";
import { usePings, useRecords } from "@/lib/api";
import { useParams, useSearchParams } from "next/navigation";
import { Loadable } from "@/components/Loadable";
import { fileFacts } from "@/components/evidence/fileFacts";
import { findCitation } from "@/components/evidence/findCitation";
import { GrantFrame } from "@/components/evidence/GrantFrame";
import { useEvidence, useFileLink } from "@/components/evidence/hooks";
import { evidenceHref } from "@/components/evidence/links";
import { Viewer } from "@/components/viewer/Viewer";

/**
 * One file in the viewer, opened at a value when the query names one:
 * `?record=<record id>&value=<path>` (first version, may change). The file's
 * name is the page's heading, and the side panel lists every fact on the
 * file's card ("In this file"), each a link to its own spot.
 */
export function FileScreen() {
  const { grantId, fileId } = useParams<{ grantId: string; fileId: string }>();
  // Refetches when the backend pings this grant's channel, such as the agent replying in a thread.
  usePings(`grant:${grantId}`);
  const query = useSearchParams();
  const recordId = query.get("record");
  const path = query.get("value");
  const evidence = useEvidence(grantId);
  // Answers aren't on the evidence cards: an answer's quote is found among the grant's records.
  const records = useRecords(grantId);
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
          const spot = recordId && path ? findCitation(cards, recordId, path, records.data?.map((r) => r.record)) : null;
          return (
            <Loadable result={link}>
              {(fileLink) => (
                <Viewer
                  openAt={recordId && path ? `${recordId}:${path}` : null}
                  file={found.file}
                  url={fileLink.url}
                  citation={spot?.citation.file_id === fileId ? spot.citation : null}
                  valueText={spot?.valueText ?? null}
                  label={spot?.label ?? null}
                  confirmation={spot?.confirmation ?? null}
                  reading={fileLink.reading ?? null}
                  facts={fileFacts(grantId, found, { recordId, value: path })}
                  headingLevel={1}
                />
              )}
            </Loadable>
          );
        }}
      </Loadable>
    </GrantFrame>
  );
}
