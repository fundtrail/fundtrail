import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { FtRecord, Thread } from "@/lib/api";
import { SuggestionBox } from "./Decide";
import { ReviewThread, type ThreadContext } from "./ReviewThread";

// Two clicks or submits in the same task both run before React re-renders the
// button disabled. Each test makes both calls inside one act(), with the first
// still in flight when the second is made.

function twice(fire: () => void) {
  act(() => {
    fire();
    fire();
  });
}

const pending = () => new Promise<void>(() => {});

const suggestion = {
  id: "r-term",
  workspace_id: "ws",
  grant_id: "g",
  author: "agent",
  author_user_id: null,
  written_at: "2026-03-01T10:00:00Z",
  replaces_id: null,
  data: { kind: "period", reason: "The extension notice moves the end date." },
} as unknown as FtRecord;

describe("the thread's writes never send twice at once", () => {
  it("Accept on a waiting suggestion: two clicks send one decision", () => {
    const onDecide = vi.fn(pending);
    render(<SuggestionBox record={suggestion} change={{ title: "Add period of performance" }} state="waiting" onDecide={onDecide} />);
    const accept = within(screen.getByTestId("suggestion")).getByRole("button", { name: /Accept/ });
    twice(() => accept.click());
    expect(onDecide).toHaveBeenCalledTimes(1);
    expect(onDecide).toHaveBeenCalledWith("r-term", "confirmed");
    // The blocked click left the first one's busy state and no error line.
    expect(accept).toBeDisabled();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("Accept then Reject in the same task: only the first is sent", () => {
    const onDecide = vi.fn(pending);
    render(<SuggestionBox record={suggestion} change={{ title: "Add period of performance" }} state="waiting" onDecide={onDecide} />);
    const box = screen.getByTestId("suggestion");
    act(() => {
      within(box).getByRole("button", { name: /Accept/ }).click();
      within(box).getByRole("button", { name: /Reject/ }).click();
    });
    expect(onDecide).toHaveBeenCalledTimes(1);
    expect(onDecide).toHaveBeenCalledWith("r-term", "confirmed");
  });

  it("Send: two submits send one message and keep the typed text while it is in flight", () => {
    const onAsk = vi.fn(pending);
    const thread = { entries: [], agent_run: null } as unknown as Thread;
    const ctx: ThreadContext = { records: {}, files: {}, checklist: [], reasons: [], waiting: [] };
    render(<ReviewThread thread={thread} about="L-1002" ctx={ctx} onDecide={vi.fn()} onAsk={onAsk} />);
    const box = screen.getByLabelText("Ask the agent about L-1002") as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "Was this ordered before the end date?" } });
    const form = box.closest("form") as HTMLFormElement;
    twice(() => form.requestSubmit());
    expect(onAsk).toHaveBeenCalledTimes(1);
    expect(onAsk).toHaveBeenCalledWith("Was this ordered before the end date?");
    expect(box.value).toBe("Was this ordered before the end date?");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
