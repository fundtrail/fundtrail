import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ChargeDetail, ChargeStatus, FtRecord } from "@/lib/api";
import { sampleChargeDetails } from "@/lib/api/fixtures/charge";
import { ChargeDetailView } from "./ChargeDetailView";

const noop = vi.fn(async () => {});
// The server's words for a partly filled item (ruling 73). The screen shows them as they are.
const PARTLY = "Partly filled: $500.00 of $1,240.00 covered";

/** L-1001 with its one checklist item made partly filled by the server, or left as the fixture has it. */
function sample(partly: boolean): ChargeDetail & { status: ChargeStatus } {
  const detail = structuredClone(sampleChargeDetails()["chg-l-1001"]) as ChargeDetail & { status: ChargeStatus };
  const item = detail.status.checklist[0];
  item.filled = false;
  if (partly) {
    item.covered_cents = 50_000;
    item.partly_filled_text = PARTLY;
  }
  return detail;
}

function checklistItem(): HTMLElement {
  return within(screen.getByRole("list", { name: "Evidence checklist" })).getByRole("listitem");
}

describe("a partly filled checklist item", () => {
  it("shows the server's words as the item's state, with its own mark, and still names what fills it", () => {
    render(<ChargeDetailView detail={sample(true)} onDecide={noop} onAsk={noop} />);
    const item = checklistItem();
    expect(item).toHaveAttribute("data-partly", "true");
    expect(item).toHaveAttribute("data-filled", "false");
    expect(within(item).getByText(PARTLY)).toBeInTheDocument();
    expect(within(item).queryByText("Missing")).toBeNull();
    expect(within(item).queryByText("Filled")).toBeNull();
    expect(within(item).getByText(/Filled by Bill, invoice_1001.txt/)).toBeInTheDocument();
    const mark = item.querySelector("[aria-hidden='true']");
    expect(mark?.className).toMatch(/partly/);
    expect(mark?.className).not.toMatch(/filled|missing/);
  });

  it("uses the same mark and words on the evidence trail, where the line stays dashed from it", () => {
    render(<ChargeDetailView detail={sample(true)} onDecide={noop} onAsk={noop} />);
    const node = screen.getByTestId("missing-item");
    expect(node).toHaveAttribute("data-mark", "partly");
    expect(node).toHaveAttribute("data-break");
    expect(within(node).getByText(PARTLY)).toBeInTheDocument();
    expect(within(node).queryByText("Missing")).toBeNull();
  });

  it("isn't filled: the checklist opens by default and its count is the server's filled flags", () => {
    render(<ChargeDetailView detail={sample(true)} onDecide={noop} onAsk={noop} />);
    const checklist = screen.getByTestId("checklist") as HTMLDetailsElement;
    expect(checklist.open).toBe(true);
    expect(checklist.querySelector("summary")).toHaveTextContent("Evidence checklist · 0 of 1 filled");
  });

  it("renders exactly as a missing item when the server sends no partly filled text", () => {
    render(<ChargeDetailView detail={sample(false)} onDecide={noop} onAsk={noop} />);
    const item = checklistItem();
    expect(item).not.toHaveAttribute("data-partly");
    expect(within(item).getByText("Missing")).toBeInTheDocument();
    expect(item.querySelector("[aria-hidden='true']")?.className).toMatch(/missing/);
    const node = screen.getByTestId("missing-item");
    expect(node).toHaveAttribute("data-mark", "missing");
    expect(within(node).getByText("Missing")).toBeInTheDocument();
  });

  it("keeps a waiting removal's suggestion under a partly filled item", () => {
    const detail = sample(true);
    const removal = {
      id: "r-removal",
      workspace_id: "ws",
      grant_id: "grant-sample",
      author: "agent",
      author_user_id: null,
      written_at: "2026-03-01T10:00:00Z",
      replaces_id: null,
      data: { kind: "checklist_removal", charge_id: detail.charge.id, default_item: "bill", reason: "The usage statement is the bill here." },
    } as unknown as FtRecord;
    detail.status.checklist[0].removal_waiting_id = removal.id;
    detail.waiting = [{ record: removal, replaces: null, charge_ids: [detail.charge.id] }];
    detail.records = { ...(detail.records ?? {}), [removal.id]: removal };
    render(<ChargeDetailView detail={detail} onDecide={noop} onAsk={noop} />);
    const item = checklistItem();
    expect(within(item).getByText(PARTLY)).toBeInTheDocument();
    const box = within(item).getByTestId("suggestion");
    expect(within(box).getByText("The usage statement is the bill here.")).toBeInTheDocument();
    expect(within(box).getByText("Waiting for you")).toBeInTheDocument();
  });

  it("never draws the check or the partly mark on an item the server says is filled", () => {
    const detail = sample(true);
    detail.status.checklist[0].filled = true;
    render(<ChargeDetailView detail={detail} onDecide={noop} onAsk={noop} />);
    const item = checklistItem();
    expect(item).not.toHaveAttribute("data-partly");
    expect(within(item).getByText("Filled")).toBeInTheDocument();
    expect(screen.queryByTestId("missing-item")).toBeNull();
  });

  it("treats text of only spaces as absent: the item reads Missing with the dashed ring", () => {
    const detail = sample(true);
    detail.status.checklist[0].partly_filled_text = "   ";
    render(<ChargeDetailView detail={detail} onDecide={noop} onAsk={noop} />);
    const item = checklistItem();
    expect(item).not.toHaveAttribute("data-partly");
    expect(within(item).getByText("Missing")).toBeInTheDocument();
    expect(item.querySelector("[aria-hidden='true']")?.className).toMatch(/missing/);
    const node = screen.getByTestId("missing-item");
    expect(node).toHaveAttribute("data-mark", "missing");
    expect(within(node).getByText("Missing")).toBeInTheDocument();
  });
});
