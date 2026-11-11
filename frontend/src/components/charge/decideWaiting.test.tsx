import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type ChargeDetail, type NewRecordInput } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { DUPLICATE_MARK } from "@/lib/api/fixtures/duplicate";
import { sampleChargeDetails } from "@/lib/api/fixtures/charge";
import { ChargeDetailView } from "./ChargeDetailView";

// Issue 353: the agent's duplicate mark is about files, so it isn't in the
// charge's thread. While it waits, the charge's reason for it offers Confirm
// and Reject.

const noop = vi.fn(async () => {});

/** L-1002 as the fake serves it while the mark waits. */
async function waitingDetail(): Promise<ChargeDetail> {
  return createFakeApiClient().getCharge("chg-l-1002");
}

/** A write that stays in flight until the test settles it. */
function deferredWriter() {
  const settle: { resolve: () => void; reject: (e: unknown) => void }[] = [];
  const onWrite = vi.fn<(input: NewRecordInput) => Promise<void>>(
    () =>
      new Promise<void>((resolve, reject) => {
        settle.push({ resolve, reject });
      }),
  );
  return { onWrite, settle };
}

function markReason() {
  const reason = screen.getAllByTestId("reason").find((r) => r.textContent?.includes("The agent marked a file as a copy of another"));
  if (!reason) throw new Error("no reason for the mark");
  return reason;
}

const decision = () => within(markReason()).getByRole("group", { name: "Decide the agent's suggestion" });

describe("the agent's waiting duplicate mark on the charge", () => {
  it("offers Confirm and Reject on its reason, beside Accept with a note, and only there", async () => {
    render(<ChargeDetailView detail={await waitingDetail()} onDecide={noop} onAsk={noop} onWrite={noop} />);
    const group = decision();
    expect(within(group).getByRole("button", { name: "Confirm" })).toHaveClass("ft-btn", "ft-btn--sm", "ft-btn--approve");
    expect(within(group).getByRole("button", { name: "Reject" })).toHaveClass("ft-btn", "ft-btn--sm", "ft-btn--reject");
    expect(within(group).getByRole("button", { name: "Confirm" }).className).not.toContain("ft-btn--main");
    expect(within(markReason()).getByRole("button", { name: "Accept with a note" })).toBeInTheDocument();
    // The other reason, which no waiting record backs, offers no decision.
    expect(screen.getAllByRole("group", { name: "Decide the agent's suggestion" })).toHaveLength(1);
  });

  for (const [name, value] of [
    ["Confirm", "confirmed"],
    ["Reject", "rejected"],
  ] as const) {
    it(`${name} sends one confirmation naming the mark, even on a double submit`, async () => {
      const { onWrite, settle } = deferredWriter();
      render(<ChargeDetailView detail={await waitingDetail()} onDecide={noop} onAsk={noop} onWrite={onWrite} />);
      const button = within(decision()).getByRole("button", { name });
      act(() => {
        button.click();
        button.click();
      });
      expect(onWrite).toHaveBeenCalledTimes(1);
      expect(onWrite.mock.calls[0][0]).toStrictEqual({ data: { kind: "confirmation", record_ids: [DUPLICATE_MARK.id], decision: value } });
      expect(within(decision()).getByRole("button", { name: "Confirm" })).toBeDisabled();
      expect(within(decision()).getByRole("button", { name: "Reject" })).toBeDisabled();
      await act(async () => settle[0].resolve());
      expect(onWrite).toHaveBeenCalledTimes(1);
    });
  }

  it("shows the server's words when it refuses", async () => {
    const onWrite = vi.fn(async () => {
      throw new ApiError(422, ["The duplicate mark isn't waiting for the accountant."]);
    });
    render(<ChargeDetailView detail={await waitingDetail()} onDecide={noop} onAsk={noop} onWrite={onWrite} />);
    fireEvent.click(within(decision()).getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(within(markReason()).getByRole("alert")).toHaveTextContent("The duplicate mark isn't waiting for the accountant."));
  });

  it("offers nothing when no record waits, when the page can't write, or when the thread already offers the decision", async () => {
    const plain = sampleChargeDetails()["chg-l-1002"];
    const { unmount } = render(<ChargeDetailView detail={plain} onDecide={noop} onAsk={noop} onWrite={noop} />);
    expect(screen.queryByRole("group", { name: "Decide the agent's suggestion" })).toBeNull();
    unmount();

    const waiting = await waitingDetail();
    const readOnly = render(<ChargeDetailView detail={waiting} onDecide={noop} onAsk={noop} />);
    expect(screen.queryByRole("group", { name: "Decide the agent's suggestion" })).toBeNull();
    readOnly.unmount();

    // The reason names the record, but the server no longer lists it as waiting.
    const settled = { ...waiting, waiting: [] };
    const gone = render(<ChargeDetailView detail={settled} onDecide={noop} onAsk={noop} onWrite={noop} />);
    expect(screen.queryByRole("group", { name: "Decide the agent's suggestion" })).toBeNull();
    gone.unmount();

    // A waiting record in the review thread is decided there, not twice.
    const inThread: ChargeDetail = {
      ...waiting,
      thread: { ...waiting.thread, entries: [...waiting.thread.entries, { kind: "record", record: DUPLICATE_MARK, state: "waiting" }] },
    };
    render(<ChargeDetailView detail={inThread} onDecide={noop} onAsk={noop} onWrite={noop} />);
    expect(screen.queryByRole("group", { name: "Decide the agent's suggestion" })).toBeNull();
    expect(within(screen.getByTestId("suggestion")).getByRole("button", { name: /Reject/ })).toBeInTheDocument();
  });
});
