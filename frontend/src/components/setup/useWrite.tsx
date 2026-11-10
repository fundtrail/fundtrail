"use client";

import { useState } from "react";
import { ApiError, useApi, useRefresh, type FtRecord, type Id, type NewRecordInput } from "@/lib/api";

export type WriteState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "saved"; record: FtRecord }
  | { status: "failed"; problems: string[] };

/**
 * Sends one accountant decision as a record (POST /grants/{grant_id}/records),
 * then refetches what's on screen so the server's new state shows. A write the
 * write check rejects shows its problems as the server words them.
 */
export function useWrite() {
  const api = useApi();
  const refresh = useRefresh();
  const [state, setState] = useState<WriteState>({ status: "idle" });

  async function write(grantId: Id, body: NewRecordInput): Promise<FtRecord | null> {
    setState({ status: "saving" });
    try {
      const record = await api.writeRecord(grantId, body);
      setState({ status: "saved", record });
      void refresh();
      return record;
    } catch (error) {
      const problems =
        error instanceof ApiError
          ? (error.problems ?? [error.message])
          : ["Couldn't save this. Try again."];
      setState({ status: "failed", problems });
      return null;
    }
  }

  return { state, write };
}

export function WriteProblems({ state }: { state: WriteState }) {
  if (state.status !== "failed") return null;
  return (
    <ul className="ft-error" role="alert">
      {state.problems.map((p, i) => (
        <li key={i}>{p}</li>
      ))}
    </ul>
  );
}
