"use client";

import { useApi, useGrant, useRecords, useRefresh, type GrantProblem, type Id, type NewRecordInput } from "@/lib/api";
import { useGrantDisplayName } from "@/lib/grantName";
import { AcceptReason, ReopenReason } from "./charge/actions";
import { field } from "./charge/labels";
import styles from "./SelectedProblem.module.css";

/**
 * Writes one of the accountant's records on the grant, then refetches what's on
 * screen, the way a charge's thread actions do.
 */
function useGrantWrite(grantId: Id) {
  const api = useApi();
  const refresh = useRefresh();
  return async (input: NewRecordInput) => {
    await api.writeRecord(grantId, input);
    await refresh();
  };
}

/**
 * A problem on the grant itself, picked on the problem list: its text in the
 * server's words, and Accept with a note (issue 301). The acceptance is an
 * accepted_reason with no charge, record or file, so it's about the grant; it's
 * always a one-off. Once accepted, it shows as an accepted charge reason does:
 * the Accepted tag, the note, and Reopen.
 */
export function GrantProblemPane({ grantId, problem }: { grantId: Id; problem: GrantProblem }) {
  const grantName = useGrantDisplayName();
  const grant = useGrant(grantId);
  const records = useRecords(grantId);
  const write = useGrantWrite(grantId);
  const acceptedBy = problem.accepted_by ?? null;
  const accepted = acceptedBy ? records.data?.find((r) => r.record.id === acceptedBy)?.record : undefined;
  const note = accepted ? field<string>(accepted, "note") : undefined;
  return (
    <div className={`ft-panel ${styles.summary}`}>
      <div className={styles.summaryTop}>
        <span className="ft-tag">Grant</span>
      </div>
      <h2 className={styles.summaryName}>{grant.data ? grantName(grant.data.summary) : "This grant"}</h2>
      <p className={styles.problemText}>
        {problem.text}
        {problem.accepted && (
          <>
            {" "}
            <span className="ft-tag ft-tag--accepted">Accepted</span>
          </>
        )}
      </p>
      {problem.accepted ? (
        <div className={styles.accepted} data-testid="accepted-result">
          {note && <p className="ft-caption">Your note: {note}</p>}
          {acceptedBy && <ReopenReason acceptedId={acceptedBy} onWrite={write} />}
        </div>
      ) : (
        <div className={styles.accept}>
          <AcceptReason chargeId={null} reason={problem} onWrite={write} />
        </div>
      )}
    </div>
  );
}
