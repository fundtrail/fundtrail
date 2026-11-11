import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ChargeDetail, ChargeStatus, ChecklistEntry, FtRecord, Judgment, Reason } from "@/lib/api";
import { sampleChargeDetails } from "@/lib/api/fixtures/charge";
import { ChargeDetailView } from "./ChargeDetailView";
import { StatusReasons } from "./StatusReasons";

const noop = vi.fn(async () => {});

/** A fresh copy of a sample charge, with its status and first answer easy to change. */
function sample(id: "chg-l-1001" | "chg-l-1002"): ChargeDetail & { status: ChargeStatus } {
  return structuredClone(sampleChargeDetails()[id]) as ChargeDetail & { status: ChargeStatus };
}

function renderView(detail: ChargeDetail, withWrite = false) {
  return render(<ChargeDetailView detail={detail} onDecide={noop} onAsk={noop} onWrite={withWrite ? noop : undefined} />);
}

function disclosure(testId: string): HTMLDetailsElement {
  return screen.getByTestId(testId) as HTMLDetailsElement;
}

function setAnswer(detail: ChargeDetail, answer: string) {
  const judgment = (detail.answers ?? [])[0].judgment as FtRecord<Judgment>;
  (judgment.data as unknown as { answer: string }).answer = answer;
}

describe("the evidence trail opens only what needs the accountant", () => {
  it("opens a failing reason and closes a Supports answer, a fully covering bill, passing reasons and history", () => {
    renderView(sample("chg-l-1002"), true);
    expect(screen.getByTestId("reason")).toHaveAttribute("data-open", "true");
    expect(screen.getByTestId("answer")).toHaveAttribute("data-open", "false");
    const link = screen.getByTestId("link");
    expect(link).toHaveAttribute("data-open", "false");
    expect(link).toHaveAttribute("data-mark", "holds");
    expect(link).not.toHaveAttribute("data-break");
    expect(disclosure("passing").open).toBe(false);
    expect(disclosure("history").open).toBe(false);
    expect(disclosure("checklist").open).toBe(false);
  });

  it("words the closed lines as counts of what the server sent", () => {
    renderView(sample("chg-l-1002"));
    expect(within(disclosure("passing")).getByText("Passing")).toBeInTheDocument();
    expect(within(disclosure("passing")).getByText("· 2", { exact: false })).toBeInTheDocument();
    expect(disclosure("checklist").querySelector("summary")).toHaveTextContent("Evidence checklist · 1 of 1 filled");
    expect(disclosure("history").querySelector("summary")).toHaveTextContent("Status history · 1 change");
    expect(within(disclosure("passing")).getAllByRole("listitem")).toHaveLength(2);
  });

  it("leaves out the passing line and the history line when there is nothing in them", () => {
    const detail = sample("chg-l-1002");
    detail.status.reasons = detail.status.reasons.filter((r) => r.bucket !== "evidence_complete");
    detail.history = [];
    renderView(detail);
    expect(screen.queryByTestId("passing")).toBeNull();
    expect(screen.queryByTestId("history")).toBeNull();
  });

  it("opens Contradicts and Unsure answers", () => {
    for (const answer of ["contradicts", "unsure"]) {
      const detail = sample("chg-l-1001");
      setAnswer(detail, answer);
      const { unmount } = renderView(detail);
      const node = screen.getByTestId("answer");
      expect(node).toHaveAttribute("data-open", "true");
      expect(node).toHaveAttribute("data-break");
      unmount();
    }
  });

  it("opens the checklist for a missing item, which is also a dashed ring on the trail", () => {
    const detail = sample("chg-l-1001");
    detail.status.checklist.push({ added_by: "agent", needed: "Signed run log", filled: false, link_ids: [] } as ChecklistEntry);
    renderView(detail);
    expect(disclosure("checklist").open).toBe(true);
    const missing = screen.getByRole("list", { name: "Missing from the checklist" });
    expect(within(missing).getByText("Signed run log")).toBeInTheDocument();
    expect(within(missing).getByRole("listitem")).toHaveAttribute("data-mark", "missing");
  });

  it("opens the checklist when a removal waits", () => {
    const detail = sample("chg-l-1001");
    detail.status.checklist[0].removal_waiting_id = "r-removal";
    renderView(detail);
    expect(disclosure("checklist").open).toBe(true);
  });

  it("opens an empty checklist, with Add item in view and no count", () => {
    const detail = sample("chg-l-1001");
    detail.status.checklist = [];
    renderView(detail, true);
    expect(disclosure("checklist").open).toBe(true);
    expect(disclosure("checklist").querySelector("summary")).toHaveTextContent(/^Evidence checklist/);
    expect(disclosure("checklist").querySelector("summary")).not.toHaveTextContent("filled");
    expect(within(disclosure("checklist")).getByRole("button", { name: "Add item" })).toBeInTheDocument();
  });

  it("opens and closes a node from its head line", () => {
    renderView(sample("chg-l-1002"));
    const node = screen.getByTestId("answer");
    const head = within(node).getByRole("button", { name: /Is this cost necessary/ });
    expect(head).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(head);
    expect(head).toHaveAttribute("aria-expanded", "true");
    expect(node).toHaveAttribute("data-open", "true");
  });
});

describe("an answer's quotes", () => {
  it("ask the screen for a link with the answer's id and each quote's index", () => {
    const detail = sample("chg-l-1002");
    const judgment = (detail.answers ?? [])[0].judgment;
    const data = judgment.data as unknown as { quotes: unknown[] };
    data.quotes = [data.quotes[0], { ...(data.quotes[0] as object), passage: "A second passage" }];
    const quote = vi.fn(() => "/viewer");
    render(<ChargeDetailView detail={detail} onDecide={noop} onAsk={noop} links={{ quote }} />);
    expect(quote).toHaveBeenCalledWith(data.quotes[0], judgment.id, 0);
    expect(quote).toHaveBeenCalledWith(data.quotes[1], judgment.id, 1);
  });
});

describe("a linked bill", () => {
  it("keeps the viewer link and its toggle as siblings, never the link inside a control", () => {
    render(
      <ChargeDetailView
        detail={sample("chg-l-1002")}
        onDecide={noop}
        onAsk={noop}
        links={{ link: () => "/viewer" }}
      />,
    );
    const node = screen.getByTestId("link");
    const link = within(node).getByRole("link", { name: "sequencing_statement.eml" });
    expect(link.closest("button")).toBeNull();
    const toggle = within(node).getByRole("button", { name: "Details, sequencing_statement.eml" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle.contains(link)).toBe(false);
  });

  it("shows how much of the bill the charge uses on its line, whatever its length", () => {
    const detail = sample("chg-l-1002");
    const view = (detail.links ?? [])[0];
    (view.link.data as unknown as { amount_cents: number }).amount_cents = 123_456_789;
    (view.record.data as unknown as { total: { value: number } }).total.value = 200_000_000;
    renderView(detail);
    expect(within(screen.getByTestId("link")).getByText("$1,234,567.89 of $2,000,000.00")).toBeInTheDocument();
  });

  it("isn't drawn as holding while any of its values is unconfirmed", () => {
    const detail = sample("chg-l-1002");
    (detail.links ?? [])[0].values = [
      { path: "total", confirmed: false },
      { path: "vendor", confirmed: true },
    ];
    renderView(detail);
    const node = screen.getByTestId("link");
    expect(node).toHaveAttribute("data-mark", "human");
    expect(node).toHaveAttribute("data-break");
    expect(node).toHaveAttribute("data-open", "true");
    expect(within(node).getByText("Not confirmed: total")).toBeInTheDocument();
  });
});

describe("acting on a reason", () => {
  const failing: Reason = { check: "checklist", problem: "missing_item", text: "A bill isn't on file.", record_ids: [], bucket: "missing_evidence" } as Reason;
  const status = (reason: Reason): ChargeStatus =>
    ({ grant_id: "g", charge_id: "c", bucket: "missing_evidence", reasons: [reason], checklist: [], flagged: true }) as ChargeStatus;
  const accepted = {
    id: "r-acc",
    workspace_id: "ws",
    grant_id: "g",
    author: "user",
    author_user_id: "u",
    written_at: "2026-03-01T10:00:00Z",
    replaces_id: null,
    data: { kind: "accepted_reason", charge_id: "c", note: "Refunded in March.", reusable: false },
  } as unknown as FtRecord;

  it("puts Snooze on its own row for the whole charge, not inside a reason", () => {
    render(<StatusReasons status={status(failing)} onWrite={noop} />);
    const row = screen.getByTestId("charge-actions");
    expect(within(row).getByRole("button", { name: "Snooze" })).toBeInTheDocument();
    expect(within(screen.getByTestId("reason")).queryByRole("button", { name: "Snooze" })).toBeNull();
  });

  it("keeps the reason open after it is accepted and moves focus to the result", () => {
    const { rerender } = render(<StatusReasons status={status(failing)} onWrite={noop} />);
    expect(screen.getByTestId("reason")).toHaveAttribute("data-open", "true");
    rerender(<StatusReasons status={status({ ...failing, accepted_by: "r-acc" })} records={{ [accepted.id]: accepted }} onWrite={noop} />);
    expect(screen.getByTestId("reason")).toHaveAttribute("data-open", "true");
    const result = screen.getByTestId("accepted-result");
    expect(result).toHaveTextContent("Your note: Refunded in March.");
    expect(document.activeElement).toBe(result);
  });

  it("doesn't take focus for a reason that was already accepted when the page opened", () => {
    render(<StatusReasons status={status({ ...failing, accepted_by: "r-acc" })} records={{ [accepted.id]: accepted }} onWrite={noop} />);
    expect(screen.getByTestId("reason")).toHaveAttribute("data-open", "false");
    expect(document.activeElement).toBe(document.body);
  });
});
