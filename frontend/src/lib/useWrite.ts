"use client";

import { useRef, useState } from "react";
import { ApiError, useApi, useRefresh, type FtRecord, type Id, type NewRecordInput } from "./api";

export type WriteState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "saved"; record: FtRecord }
  | { status: "failed"; problems: string[] };

/**
 * Sends one accountant decision as a record (POST /grants/{grant_id}/records),
 * then refetches what's on screen so the server's new state shows. A write the
 * write check rejects shows its problems as the server words them.
 *
 * Never sends twice at once: a second call while one is in flight sends
 * nothing and returns the in-flight write's result. A disabled button stops a
 * real double click, but two submits in the same task (requestSubmit() twice,
 * say) would otherwise both send before the button re-renders. The guard is
 * released when the write settles, whether it succeeds or fails.
 */
export function useWrite() {
  const api = useApi();
  const refresh = useRefresh();
  const [state, setState] = useState<WriteState>({ status: "idle" });
  const inFlight = useRef<Promise<FtRecord | null> | null>(null);

  function write(grantId: Id, body: NewRecordInput): Promise<FtRecord | null> {
    if (inFlight.current) return inFlight.current;
    setState({ status: "saving" });
    const sending = (async () => {
      try {
        const record = await api.writeRecord(grantId, body);
        setState({ status: "saved", record });
        void refresh();
        return record;
      } catch (error) {
        const problems = error instanceof ApiError ? (error.problems ?? [error.message]) : ["Couldn't save this. Try again."];
        setState({ status: "failed", problems });
        return null;
      } finally {
        inFlight.current = null;
      }
    })();
    inFlight.current = sending;
    return sending;
  }

  return { state, write };
}
