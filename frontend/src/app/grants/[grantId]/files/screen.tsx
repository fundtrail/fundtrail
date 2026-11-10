"use client";

import { useParams } from "next/navigation";
import { Loadable } from "@/components/AppShell";
import { EvidenceCardView } from "@/components/evidence/EvidenceCardView";
import styles from "@/components/evidence/evidence.module.css";
import { GrantFrame } from "@/components/evidence/GrantFrame";
import { useEvidence } from "@/components/evidence/hooks";

/** The grant's evidence: one card per file, in the server's order (first version, may change). */
export function EvidenceScreen() {
  const { grantId } = useParams<{ grantId: string }>();
  const evidence = useEvidence(grantId);
  return (
    <GrantFrame grantId={grantId} crumbs={["Evidence"]}>
      <h1 className="ft-title">Evidence</h1>
      <Loadable result={evidence}>
        {(cards) =>
          cards.length === 0 ? (
            <p className="ft-empty">No evidence on this grant yet.</p>
          ) : (
            <div className={styles.cards}>
              {cards.map((card) => (
                <EvidenceCardView key={card.file.id} grantId={grantId} card={card} />
              ))}
            </div>
          )
        }
      </Loadable>
    </GrantFrame>
  );
}
