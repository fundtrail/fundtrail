import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type ChargeDetail, type NewRecordInput, type Reason } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { DUPLICATE_MARK, DUPLICATE_REASON } from "@/lib/api/fixtures/duplicate";
import { sampleChargeDetails } from "@/lib/api/fixtures/charge";
import { ChargeDetailView } from "./ChargeDetailView";

// Issue 353: the agent's duplicate mark is about files, so it isn't in the
// charge's thread. While it waits, the charge's reason for it offers Confirm
// and Reject. The waiting record comes from the reason itself: the server's
// `waiting` list can leave it out (it follows only links to the copy, while
// the checks follow links to the copy or the original).

const noop = vi.fn(async () => {});

/** L-1002 as the fake serves it while the mark waits: the reason, and no `waiting` entry. */
async function waitingDetail(): Promise<ChargeDetail> {
  return createFakeApiClient().getCharge("chg-l-1002");
}

/** L-1002 with its mark reason replaced by `reason`. */
async function withReason(reason: Reason, records?: ChargeDetail["records"]): Promise<ChargeDetail> {
  const detail = await waitingDetail();
  const reasons = detail.status!.reasons.map((r) => (r.check === "suggestion" ? reason : r));
  return { ...detail, status: { ...detail.status!, reasons }, records: records ?? detail.records };
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
const noDecision = () => expect(screen.queryByRole("group", { name: "Decide the agent's suggestion" })).toBeNull();

describe("the agent's waiting duplicate mark on the charge", () => {
  it("offers Confirm and Reject on its reason when `waiting` leaves the mark out, beside Accept with a note", async () => {
    const detail = await waitingDetail();
    expect(detail.waiting).toEqual([]);
    render(<ChargeDetailView detail={detail} onDecide={noop} onAsk={noop} onWrite={noop} />);
    const group = decision();
    expect(within(group).getByRole("button", { name: "Confirm" })).toHaveClass("ft-btn", "ft-btn--sm", "ft-btn--approve");
    expect(within(group).getByRole("button", { name: "Reject" })).toHaveClass("ft-btn", "ft-btn--sm", "ft-btn--reject");
    expect(within(group).getByRole("button", { name: "Confirm" }).className).not.toContain("ft-btn--main");
    expect(within(markReason()).getByRole("button", { name: "Accept with a note" })).toBeInTheDocument();
    // The other reason, which names no waiting record, offers no decision.
    expect(screen.getAllByRole("group", { name: "Decide the agent's suggestion" })).toHaveLength(1);
  });

  for (const [name, value] of [
    ["Confirm", "confirmed"],
    ["Reject", "rejected"],
  ] as const) {
    it(`${name} sends one confirmation naming the mark, even on a double submit, and stays off after`, async () => {
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
      // Saved, but this row is still the old data (as when the refetch didn't bring the new state): both stay off.
      expect(within(decision()).getByRole("button", { name: "Confirm" })).toBeDisabled();
      expect(within(decision()).getByRole("button", { name: "Reject" })).toBeDisabled();
      fireEvent.click(within(decision()).getByRole("button", { name: "Reject" }));
      expect(onWrite).toHaveBeenCalledTimes(1);
    });
  }

  it("shows the server's words when it refuses, and lets the accountant try again", async () => {
    const onWrite = vi.fn(async () => {
      throw new ApiError(422, ["The duplicate mark isn't waiting for the accountant."]);
    });
    render(<ChargeDetailView detail={await waitingDetail()} onDecide={noop} onAsk={noop} onWrite={onWrite} />);
    fireEvent.click(within(decision()).getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(within(markReason()).getByRole("alert")).toHaveTextContent("The duplicate mark isn't waiting for the accountant."));
    expect(within(decision()).getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("offers nothing without the reason, on a page that can't write, or when the thread already offers the decision", async () => {
    const plain = sampleChargeDetails()["chg-l-1002"];
    const { unmount } = render(<ChargeDetailView detail={plain} onDecide={noop} onAsk={noop} onWrite={noop} />);
    noDecision();
    unmount();

    const waiting = await waitingDetail();
    const readOnly = render(<ChargeDetailView detail={waiting} onDecide={noop} onAsk={noop} />);
    noDecision();
    readOnly.unmount();

    // A waiting record in the review thread is decided there, not twice.
    const inThread: ChargeDetail = {
      ...waiting,
      thread: { ...waiting.thread, entries: [...waiting.thread.entries, { kind: "record", record: DUPLICATE_MARK, state: "waiting" }] },
    };
    render(<ChargeDetailView detail={inThread} onDecide={noop} onAsk={noop} onWrite={noop} />);
    noDecision();
    expect(within(screen.getByTestId("suggestion")).getByRole("button", { name: /Reject/ })).toBeInTheDocument();
  });

  it("offers nothing for a reason that doesn't name a waiting record of the agent's the server's way", async () => {
    const cases: [string, Reason, ChargeDetail["records"]?][] = [
      ["accepted", { ...DUPLICATE_REASON, accepted_by: "rec-accepted" }],
      ["problem names another id", { ...DUPLICATE_REASON, problem: "waiting:rec-other" }],
      ["problem in another form", { ...DUPLICATE_REASON, problem: DUPLICATE_MARK.id }],
      ["record not listed", { ...DUPLICATE_REASON, record_ids: [] }],
      ["another check", { ...DUPLICATE_REASON, check: "checklist" }],
      ["the accountant's record", DUPLICATE_REASON, { [DUPLICATE_MARK.id]: { ...DUPLICATE_MARK, author: "user", author_user_id: "u" } }],
    ];
    for (const [, reason, records] of cases) {
      const view = render(<ChargeDetailView detail={await withReason(reason, records)} onDecide={noop} onAsk={noop} onWrite={noop} />);
      noDecision();
      view.unmount();
    }
    // The same reason, as the server words it, does offer it.
    render(<ChargeDetailView detail={await withReason(DUPLICATE_REASON)} onDecide={noop} onAsk={noop} onWrite={noop} />);
    expect(decision()).toBeInTheDocument();
  });
});
