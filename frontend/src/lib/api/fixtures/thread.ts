// Review threads for the sample grant. Owned by the thread screen's builder.
//
// L-1002's thread: code's status when the line arrived, the accountant asking
// about it, and the agent's answer. The waiting extension term's thread: the
// agent's term, waiting. Posting adds the message to the thread in memory and
// queues nothing: the fake has no agent.

import type { ApiClient } from "../client";
import type { AgentRun, Id, Thread, ThreadMessage } from "../types";
import { chargeStatusAt } from "./statuses";
import { FAKE_NOW, sample, sampleRecord, served, fakeId, WORKSPACE_ID, SAMPLE_GRANT_ID } from "./sample";

const AGENT_RUN: AgentRun = {
  id: "run-thread-l-1002",
  workspace_id: WORKSPACE_ID,
  grant_id: SAMPLE_GRANT_ID,
  trigger: { kind: "thread_message", id: "msg-l-1002-ask" },
  status: "done",
  clock_now: "2026-04-09T17:00:00Z",
  queued_at: "2026-04-09T17:00:05Z",
  started_at: "2026-04-09T17:00:06Z",
  finished_at: "2026-04-09T17:00:40Z",
  summary: "Answered a question about L-1002.",
  thread_charge_id: "chg-l-1002",
};

const message = (m: Omit<ThreadMessage, "workspace_id" | "grant_id">): ThreadMessage => ({
  workspace_id: WORKSPACE_ID,
  grant_id: SAMPLE_GRANT_ID,
  ...m,
});

export function sampleThreads(): { charges: Record<Id, Thread>; records: Record<Id, Thread> } {
  return {
    charges: {
      "chg-l-1001": {
        entries: [{ kind: "status", entry: { changed_at: "2025-11-14T00:00:00Z", trigger: { kind: "charge", id: "chg-l-1001" }, status: chargeStatusAt("chg-l-1001") } }],
      },
      "chg-l-1002": {
        entries: [
          { kind: "status", entry: { changed_at: "2026-02-24T00:00:00Z", trigger: { kind: "charge", id: "chg-l-1002" }, status: chargeStatusAt("chg-l-1002") } },
          {
            kind: "message",
            message: message({
              id: "msg-l-1002-ask",
              charge_id: "chg-l-1002",
              author: "user",
              author_user_id: sample.user.id,
              text: "Is there anything on file that extends the grant past January 31?",
              written_at: "2026-04-09T17:00:00Z",
            }),
          },
          {
            kind: "message",
            message: message({
              id: "msg-l-1002-answer",
              charge_id: "chg-l-1002",
              author: "agent",
              run_id: AGENT_RUN.id,
              text: "Yes. extension_notice.txt arrived from Drive today and moves the end date to January 31, 2027. It's waiting for you to confirm it on the grant's terms.",
              written_at: "2026-04-09T17:00:00Z",
            }),
          },
        ],
        agent_run: null,
      },
    },
    records: {
      "rec-period-extension": {
        entries: [{ kind: "record", record: sampleRecord("rec-period-extension"), state: "waiting" }],
      },
    },
  };
}

export function threadFake(): Pick<ApiClient, "getChargeThread" | "getRecordThread" | "postChargeMessage" | "postRecordMessage"> {
  const threads = sampleThreads();
  const post = (subject: { charge_id?: Id; record_id?: Id }, store: Record<Id, Thread>, id: Id, text: string) => {
    if (!store[id]) return served<ThreadMessage>(undefined);
    const posted = message({ id: fakeId("msg"), ...subject, author: "user", author_user_id: sample.user.id, text, written_at: FAKE_NOW });
    store[id].entries.push({ kind: "message", message: posted });
    return served(posted);
  };
  return {
    getChargeThread: (chargeId) => served(threads.charges[chargeId]),
    getRecordThread: (recordId) => served(threads.records[recordId]),
    postChargeMessage: (chargeId, text) => post({ charge_id: chargeId }, threads.charges, chargeId, text),
    postRecordMessage: (recordId, text) => post({ record_id: recordId }, threads.records, recordId, text),
  };
}
