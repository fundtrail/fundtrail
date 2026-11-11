"use client";

import type { DuplicateView, Id } from "@/lib/api";
import { useWrite, WriteProblems } from "@/components/setup/useWrite";
import styles from "./evidence.module.css";

/**
 * Confirm and Reject for the agent's duplicate mark on a file, while the
 * server says it waits for the accountant. Each writes a confirmation naming
 * the mark, the way Grant terms confirms a term, and shows nothing of its own
 * after: the screen refetches and the card shows the server's new state. A
 * refusal shows the server's words.
 */
export function DecideDuplicate({ grantId, duplicate }: { grantId: Id; duplicate: DuplicateView }) {
  const { state, write } = useWrite();
  // Kept off after a write goes through too, until the refetch replaces this card's state.
  const busy = state.status === "saving" || state.status === "saved";
  const reason = duplicate.mark.data.reason;

  function decide(decision: "confirmed" | "rejected") {
    void write(grantId, { data: { kind: "confirmation", record_ids: [duplicate.mark.id], decision } });
  }

  return (
    <div className={styles.decide} role="group" aria-label="The agent's duplicate mark">
      {reason && <p className={styles.decideReason}>{reason}</p>}
      <div className={styles.decideButtons}>
        <button type="button" className="ft-btn ft-btn--sm ft-btn--approve" disabled={busy} onClick={() => decide("confirmed")}>
          Confirm
        </button>
        <button type="button" className="ft-btn ft-btn--sm ft-btn--reject" disabled={busy} onClick={() => decide("rejected")}>
          Reject
        </button>
      </div>
      <WriteProblems state={state} />
    </div>
  );
}
