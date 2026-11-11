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
 * `write` resolves to the saved record, or to null when nothing was saved.
 * Null means one of two things, and callers treat both as "do nothing":
 * - the write failed: `state` is "failed" with the problems to show;
 * - the write was not sent: another write from this hook was still in
 *   flight. `state` is left as it is, so it keeps describing that other
 *   write, never this one.
 *
 * Never sends twice at once. A disabled button stops a real double click, but
 * two submits in the same task (requestSubmit() twice, or Confirm then Reject)
 * would otherwise both send before the button re-renders. A call that arrives
 * while a write is in flight, even with different arguments, sends nothing
 * and resolves to null; it never gets the other write's record, which could
 * show a decision that wasn't sent. The guard is released when the write
 * settles, whether it succeeds or fails.
 */
export function useWrite() {
  const api = useApi();
  const refresh = useRefresh();
  const [state, setState] = useState<WriteState>({ status: "idle" });
  const inFlight = useRef(false);

  async function write(grantId: Id, body: NewRecordInput): Promise<FtRecord | null> {
    if (inFlight.current) return null;
    // Set before anything can throw, cleared in finally, so even a client that
    // throws synchronously releases it.
    inFlight.current = true;
    setState({ status: "saving" });
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
      inFlight.current = false;
    }
  }

  return { state, write };
}
