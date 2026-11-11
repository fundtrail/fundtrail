import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ChargeDetail, ChargeStatus, FtRecord } from "@/lib/api";
import { sampleChargeDetails } from "@/lib/api/fixtures/charge";
import { ChargeDetailView } from "./ChargeDetailView";

const noop = vi.fn(async () => {});

function sample(): ChargeDetail & { status: ChargeStatus } {
  return structuredClone(sampleChargeDetails()["chg-l-1002"]) as ChargeDetail & { status: ChargeStatus };
}

const REASON = "Cost date Feb 20, 2026 is after the grant's end date, Jan 31, 2026.";

describe("the charge in the problem list's pane (issue 356)", () => {
  it("leads with what needs the accountant, the thread one tab away, and links its own page from the header", () => {
    render(<ChargeDetailView detail={sample()} onDecide={noop} onAsk={noop} onWrite={noop} headingLevel={2} layout="pane" pageHref="/charge-page" />);
    const header = screen.getByRole("banner");
    expect(within(header).getByRole("link", { name: "Open on its own page" })).toHaveAttribute("href", "/charge-page");

    const needs = screen.getByRole("tab", { name: /Needs you/ });
    const thread = screen.getByRole("tab", { name: /Review thread/ });
    expect(needs).toHaveAttribute("aria-selected", "true");
    expect(thread).toHaveAttribute("aria-selected", "false");
    expect(within(screen.getByRole("tabpanel", { name: /Needs you/ })).getByText(REASON)).toBeInTheDocument();
    // The thread waits in its tab, hidden until picked.
    expect(screen.queryByRole("list", { name: "Review thread" })).toBeNull();

    fireEvent.click(thread);
    expect(thread).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("list", { name: "Review thread" })).toBeInTheDocument();
    expect(screen.getByLabelText("Ask the agent about L-1002")).toBeInTheDocument();
    expect(screen.queryByRole("tabpanel", { name: /Needs you/ })).toBeNull();
  });

  it("moves between the tabs with the arrow keys, with only the chosen tab a tab stop", () => {
    render(<ChargeDetailView detail={sample()} onDecide={noop} onAsk={noop} layout="pane" />);
    const needs = screen.getByRole("tab", { name: /Needs you/ });
    const thread = screen.getByRole("tab", { name: /Review thread/ });
    expect(needs).toHaveAttribute("tabindex", "0");
    expect(thread).toHaveAttribute("tabindex", "-1");
    fireEvent.keyDown(needs, { key: "ArrowRight" });
    expect(thread).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(thread);
    fireEvent.keyDown(thread, { key: "ArrowRight" });
    expect(needs).toHaveAttribute("aria-selected", "true");
  });

  it("counts the open reasons and the thread's entries on the tabs, in the server's numbers", () => {
    const detail = sample();
    render(<ChargeDetailView detail={detail} onDecide={noop} onAsk={noop} layout="pane" />);
    const open = detail.status.reasons.filter((r) => r.bucket !== "evidence_complete" && !r.accepted_by).length;
    expect(screen.getByRole("tab", { name: /Needs you/ })).toHaveTextContent(`Needs you${open}`);
    expect(screen.getByRole("tab", { name: /Review thread/ })).toHaveTextContent(`Review thread${detail.thread.entries.length}`);
  });
});

describe("the charge, decision first, on either page", () => {
  it("folds the trail, the passing reasons, the checklist and the history to closed lines under the open reasons", () => {
    render(<ChargeDetailView detail={sample()} onDecide={noop} onAsk={noop} />);
    for (const id of ["trail", "passing", "checklist", "history"]) {
      expect((screen.getByTestId(id) as HTMLDetailsElement).open).toBe(false);
    }
    expect(screen.getByTestId("trail").querySelector("summary")).toHaveTextContent("Evidence trail · 1 bill, 1 answer");
    // The reason leads, above the folded lines.
    const reason = within(screen.getByRole("list", { name: "Reasons" })).getByText(REASON);
    expect(reason.compareDocumentPosition(screen.getByTestId("trail")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("folds a reason already accepted when the charge opened into the trail, and says no reason is open", () => {
    const detail = sample();
    const accepted = {
      id: "r-acc",
      workspace_id: "ws",
      grant_id: detail.charge.grant_id,
      author: "user",
      author_user_id: "u",
      written_at: "2026-03-01T10:00:00Z",
      replaces_id: null,
      data: { kind: "accepted_reason", charge_id: detail.charge.id, note: "Approved late.", reusable: false },
    } as unknown as FtRecord;
    detail.status.reasons = detail.status.reasons.map((r) => (r.bucket === "evidence_complete" ? r : { ...r, accepted_by: accepted.id }));
    detail.records = { ...(detail.records ?? {}), [accepted.id]: accepted };
    render(<ChargeDetailView detail={detail} onDecide={noop} onAsk={noop} onWrite={noop} />);
    expect(screen.getByText("No open reasons on this charge.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Reasons" })).toBeNull();
    const settled = within(screen.getByTestId("trail")).getByRole("list", { name: "Accepted reasons" });
    expect(within(settled).getByText(REASON)).toBeInTheDocument();
  });
});
