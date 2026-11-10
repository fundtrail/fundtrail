import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type ChargeStatus, type EvidenceFile, type FtRecord, type Reason, type Thread } from "@/lib/api";
import { ReviewThread, type ThreadContext } from "./ReviewThread";

function record(id: string, author: "agent" | "user", data: Record<string, unknown>, extra: Partial<FtRecord> = {}): FtRecord {
  return {
    id,
    workspace_id: "ws",
    grant_id: "g",
    author,
    author_user_id: author === "user" ? "u" : null,
    written_at: "2026-02-25T10:00:00Z",
    replaces_id: null,
    data: data as unknown as FtRecord["data"],
    ...extra,
  } as FtRecord;
}

const notice = { id: "f-ext", name: "extension_notice.txt" } as EvidenceFile;
const reason: Reason = {
  check: "period_of_performance",
  problem: "after_end_date",
  text: "Cost date Feb 20, 2026 is after the grant's end date, Jan 31, 2026. The agent disputes this, waiting for the accountant.",
  record_ids: [],
  bucket: "needs_human",
  expected_by: null,
  accepted_by: null,
  offered_note_id: null,
  dispute_id: "r-dispute",
} as Reason;
const status = {
  grant_id: "g",
  charge_id: "c",
  bucket: "possible_conflict",
  reasons: [reason],
  checklist: [],
  flagged: true,
  rechecking: false,
  accepted: false,
  snoozed: false,
} as unknown as ChargeStatus;

const oldAnswer = record("r-old", "agent", { kind: "judgment", charge_id: "c", question: "allowable", text: "Allowable?", answer: "contradicts", reasoning: "Old." });
const newAnswer = record(
  "r-new",
  "agent",
  { kind: "judgment", charge_id: "c", question: "allowable", text: "Allowable?", answer: "supports", reasoning: "The fare class is economy." },
  { replaces_id: "r-old" },
);
const dispute = record("r-dispute", "agent", {
  kind: "dispute",
  charge_id: "c",
  check: "period_of_performance",
  reasoning: "The extension notice moves the end date to Jan 31, 2027.",
  quotes: [{ file_id: "f-ext", passage: "the end date is extended to January 31, 2027", location: { type: "char_location" } }],
});
const accepted = record("r-confirm", "user", { kind: "confirmation", record_ids: ["r-old"], decision: "confirmed" });

const thread: Thread = {
  entries: [
    { kind: "status", entry: { changed_at: "2026-02-24T12:00:00Z", trigger: { kind: "charge", id: "c" }, status } },
    {
      kind: "message",
      message: { id: "m1", workspace_id: "ws", grant_id: "g", charge_id: "c", record_id: null, author: "user", author_user_id: "u", run_id: null, text: "Was this ordered before the end date?", written_at: "2026-02-25T09:00:00Z" },
    },
    {
      kind: "message",
      message: { id: "m2", workspace_id: "ws", grant_id: "g", charge_id: "c", record_id: null, author: "agent", author_user_id: null, run_id: "run-1", text: "The order was placed on Jan 20.", written_at: "2026-02-25T09:05:00Z" },
    },
    { kind: "record", record: newAnswer, state: "waiting" },
    { kind: "record", record: dispute, state: "waiting" },
    { kind: "record", record: accepted, state: "counts" },
  ],
  agent_run: null,
} as unknown as Thread;

const ctx: ThreadContext = {
  records: { [oldAnswer.id]: oldAnswer, [newAnswer.id]: newAnswer, [dispute.id]: dispute },
  files: { [notice.id]: notice },
  checklist: [],
  reasons: [reason],
  waiting: [
    { record: newAnswer, replaces: oldAnswer, charge_ids: ["c"] },
    { record: dispute, replaces: null, charge_ids: ["c"] },
  ],
};

function renderThread(onDecide = vi.fn(async () => {}), onAsk = vi.fn(async () => {}), t: Thread = thread) {
  render(<ReviewThread thread={t} about="L-1002" ctx={ctx} onDecide={onDecide} onAsk={onAsk} />);
  return { onDecide, onAsk };
}

describe("ReviewThread", () => {
  it("reads top to bottom in the server's order, with who wrote each entry", () => {
    renderThread();
    const entries = within(screen.getByRole("list", { name: "Review thread" })).getAllByRole("listitem").filter((li) => li.dataset.kind);
    expect(entries.map((li) => `${li.dataset.kind}:${li.dataset.who}`)).toEqual([
      "status:code",
      "message:user",
      "message:agent",
      "record:agent",
      "record:agent",
      "record:user",
    ]);
    expect(within(entries[0]).getByText("Code")).toBeInTheDocument();
    expect(within(entries[0]).getByText(reason.text)).toBeInTheDocument();
    expect(within(entries[2]).getByText("Agent")).toBeInTheDocument();
    expect(within(entries[1]).getByText("Accountant")).toBeInTheDocument();
  });

  it("shows a suggestion's change, now and suggested", () => {
    renderThread();
    const box = screen.getByTestId("suggestion");
    expect(within(box).getByText("Change answer", { selector: "p" })).toBeInTheDocument();
    expect(within(box).getByText("Contradicts")).toBeInTheDocument();
    expect(within(box).getByText("Supports")).toBeInTheDocument();
    expect(within(box).getByText("The fare class is economy.")).toBeInTheDocument();
  });

  it("accepts a suggestion", async () => {
    const { onDecide } = renderThread();
    fireEvent.click(within(screen.getByTestId("suggestion")).getByRole("button", { name: /Accept/ }));
    await waitFor(() => expect(onDecide).toHaveBeenCalledWith("r-new", "confirmed"));
  });

  it("rejects a suggestion", async () => {
    const { onDecide } = renderThread();
    fireEvent.click(within(screen.getByTestId("suggestion")).getByRole("button", { name: /Reject/ }));
    await waitFor(() => expect(onDecide).toHaveBeenCalledWith("r-new", "rejected"));
  });

  it("shows the write check's problems when the server refuses a decision", async () => {
    const onDecide = vi.fn(async () => {
      throw new ApiError(422, ["That record no longer waits for a confirmation."]);
    });
    renderThread(onDecide);
    fireEvent.click(within(screen.getByTestId("suggestion")).getByRole("button", { name: /Accept/ }));
    expect(await screen.findByText("That record no longer waits for a confirmation.")).toBeInTheDocument();
  });

  it("shows a plain line, never a raw body, when a refusal isn't the write check's", async () => {
    const onDecide = vi.fn(async () => {
      throw new ApiError(422, [{ loc: ["body", "data"], msg: "field required", type: "missing" }]);
    });
    renderThread(onDecide);
    fireEvent.click(within(screen.getByTestId("suggestion")).getByRole("button", { name: /Accept/ }));
    expect(await screen.findByText("The server refused this (status 422). Nothing was saved.")).toBeInTheDocument();
    expect(screen.queryByText(/field required/)).toBeNull();
  });

  it("says Accepted only when the accountant's confirmation decided it", () => {
    const decided = { ...thread, entries: [{ kind: "record", record: newAnswer, state: "counts" }, { kind: "record", record: record("r-c2", "user", { kind: "confirmation", record_ids: ["r-new"], decision: "confirmed" }, { written_at: "2026-02-26T10:00:00Z" }), state: "counts" }] } as unknown as Thread;
    renderThread(undefined, undefined, decided);
    expect(within(screen.getByTestId("suggestion")).getByText("Accepted by the accountant, Feb 26, 2026")).toBeInTheDocument();
  });

  it("says Counts for an agent record that took effect without a decision", () => {
    const settled = { ...thread, entries: [{ kind: "record", record: newAnswer, state: "counts" }] } as unknown as Thread;
    renderThread(undefined, undefined, settled);
    const box = screen.getByTestId("suggestion");
    expect(within(box).getByText("Counts")).toBeInTheDocument();
    expect(within(box).queryByText(/Accepted/)).toBeNull();
  });

  it("names the withdrawal of a flag as a flag", () => {
    const flag = record("r-flag", "agent", { kind: "judgment", charge_id: "c", question: "flag", text: "Bought late?", answer: "unsure", reasoning: "Close to the end date." });
    const withdraw = record("r-withdraw", "agent", { kind: "retraction", reason: "The order was placed in January." }, { replaces_id: "r-flag" });
    const t = { entries: [{ kind: "record", record: withdraw, state: "waiting" }], agent_run: null } as unknown as Thread;
    render(<ReviewThread thread={t} about="L-1002" ctx={{ ...ctx, records: { ...ctx.records, [flag.id]: flag } }} onDecide={vi.fn()} onAsk={vi.fn()} />);
    expect(within(screen.getByTestId("suggestion")).getByText("Withdraw flag", { selector: "p" })).toBeInTheDocument();
  });

  it("says a rejected suggestion comes back only with new evidence, and offers no buttons", () => {
    const rejected = { ...thread, entries: [{ kind: "record", record: newAnswer, state: "rejected" }] } as unknown as Thread;
    renderThread(undefined, undefined, rejected);
    const box = screen.getByTestId("suggestion");
    expect(within(box).getByText("Rejected")).toBeInTheDocument();
    expect(within(box).getByText(/only if new evidence arrives/)).toBeInTheDocument();
    expect(within(box).queryByRole("button")).toBeNull();
  });

  it("shows a dispute with the check, the server's reason, the agent's reasoning and its quote", () => {
    renderThread();
    const box = screen.getByTestId("dispute");
    expect(within(box).getByText(`The agent disputes: ${reason.text}`)).toBeInTheDocument();
    expect(within(box).getByText("period_of_performance")).toBeInTheDocument();
    expect(within(box).getByText("The extension notice moves the end date to Jan 31, 2027.")).toBeInTheDocument();
    expect(within(box).getByText("the end date is extended to January 31, 2027")).toBeInTheDocument();
    expect(within(box).getByText("extension_notice.txt")).toBeInTheDocument();
    expect(within(box).getByText(/with the agent's reasoning as the note/)).toBeInTheDocument();
  });

  it("accepts a dispute by confirming it", async () => {
    const { onDecide } = renderThread();
    fireEvent.click(within(screen.getByTestId("dispute")).getByRole("button", { name: /Accept/ }));
    await waitFor(() => expect(onDecide).toHaveBeenCalledWith("r-dispute", "confirmed"));
  });

  it("rejects a dispute", async () => {
    const { onDecide } = renderThread();
    fireEvent.click(within(screen.getByTestId("dispute")).getByRole("button", { name: /Reject/ }));
    await waitFor(() => expect(onDecide).toHaveBeenCalledWith("r-dispute", "rejected"));
  });

  it("names the accountant's decision", () => {
    renderThread();
    expect(screen.getByText("Accepted answer")).toBeInTheDocument();
  });

  it("asks the agent and clears the box", async () => {
    const { onAsk } = renderThread();
    const box = screen.getByLabelText("Ask the agent about L-1002");
    fireEvent.change(box, { target: { value: "Is there a quote for this?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(onAsk).toHaveBeenCalledWith("Is there a quote for this?"));
    await waitFor(() => expect(box).toHaveValue(""));
  });

  it("says when the agent is working on the thread", () => {
    const busy = { ...thread, agent_run: { status: "running" } } as unknown as Thread;
    renderThread(undefined, undefined, busy);
    expect(screen.getByRole("status")).toHaveTextContent("The agent is working on this now.");
  });
});
