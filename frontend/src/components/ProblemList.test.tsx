import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Charge, ChargeStatus, EvidenceFile, ProblemRow, Reason } from "@/lib/api";
import { problemLists, SAMPLE_GRANT_ID } from "@/lib/api/fixtures";
import { ProblemList } from "./ProblemList";

function charge(id: string, line: string, tx: string, description: string): Charge {
  return {
    id,
    workspace_id: "ws",
    grant_id: "g",
    ledger_line_id: line,
    transaction_date: tx,
    posting_date: tx,
    arrived_at: `${tx}T00:00:00Z`,
    amount_cents: 10_000,
    description,
    account: "55016 Lab Instruments and Supplies",
    vendor: null,
    reference: null,
    original_line_id: null,
  };
}

function reason(bucket: Reason["bucket"], text: string): Reason {
  return { check: "c", problem: text, text, record_ids: [], bucket, expected_by: null, accepted_by: null, offered_note_id: null };
}

function status(bucket: ChargeStatus["bucket"], reasons: Reason[]): ChargeStatus {
  return { grant_id: "g", charge_id: "c", bucket, reasons, checklist: [], flagged: true, rechecking: false, accepted: false, snoozed: false };
}

const notice: EvidenceFile = {
  id: "f-notice",
  workspace_id: "ws",
  grant_id: "g",
  source: "drive",
  name: "amendment_001.pdf",
  media_type: "application/pdf",
  storage_path: "ws/g/f-notice/amendment_001.pdf",
  sha256: "x",
  document_date: null,
  arrived_at: "2026-03-01T00:00:00Z",
  sender: null,
  source_ref: null,
  parent_id: null,
};

/** Rows as a server might send them. Deliberately not in the order a client-side sort would pick. */
const rows: ProblemRow[] = [
  {
    kind: "grant",
    problem: { check: "budget", problem: "over_limit", text: "Spending is over the award's limit.", record_ids: [], flagged: true, accepted: false, snoozed: false },
  },
  { kind: "terms_waiting", file: notice, record_ids: ["t1", "t2"], text: "2 terms waiting to be confirmed" },
  { kind: "charge", charge: charge("c3", "L-3", "2026-03-01", "Newest missing"), status: status("missing_evidence", [reason("missing_evidence", "An item is missing.")]) },
  { kind: "charge", charge: charge("c1", "L-1", "2025-01-01", "Oldest conflict"), status: status("possible_conflict", [reason("possible_conflict", "After the end date.")]) },
  { kind: "charge", charge: charge("c2", "L-2", "2025-06-01", "Middle human"), status: status("needs_human", [reason("needs_human", "The agent is unsure.")]) },
];

function shownOrder(): string[] {
  return within(screen.getByRole("list", { name: "Problem list" }))
    .getAllByRole("listitem")
    .map((li) => li.getAttribute("data-kind") + ":" + (li.querySelector(".ft-id")?.textContent ?? li.querySelector(".ft-problem__text")?.textContent));
}

describe("ProblemList", () => {
  it("shows the rows exactly in the server's order, without sorting them", () => {
    render(<ProblemList rows={rows} />);
    expect(shownOrder()).toEqual([
      "grant:Spending is over the award's limit.",
      "terms_waiting:2 terms waiting to be confirmed",
      "charge:L-3",
      "charge:L-1",
      "charge:L-2",
    ]);
  });

  it("keeps a reversed order reversed", () => {
    render(<ProblemList rows={[...rows].reverse()} />);
    expect(shownOrder()).toEqual([
      "charge:L-2",
      "charge:L-1",
      "charge:L-3",
      "terms_waiting:2 terms waiting to be confirmed",
      "grant:Spending is over the award's limit.",
    ]);
  });

  it("puts the grant problem the server sends first at the top", () => {
    render(<ProblemList rows={rows} />);
    const first = screen.getAllByRole("listitem")[0];
    expect(within(first).getByText("Grant")).toBeInTheDocument();
    expect(within(first).getByText("Spending is over the award's limit.")).toBeInTheDocument();
  });

  it("shows waiting terms as one row for their source document", () => {
    render(<ProblemList rows={rows} />);
    const termRows = screen.getAllByRole("listitem").filter((li) => li.getAttribute("data-kind") === "terms_waiting");
    expect(termRows).toHaveLength(1);
    expect(within(termRows[0]).getByText("amendment_001.pdf")).toBeInTheDocument();
  });

  it("shows each charge's bucket and the server's reason text, not the passes", () => {
    const withPass = status("possible_conflict", [reason("possible_conflict", "After the end date."), reason("evidence_complete", "Bills cover it.")]);
    render(<ProblemList rows={[{ kind: "charge", charge: charge("c1", "L-1", "2025-01-01", "A charge"), status: withPass }]} />);
    expect(screen.getByText("Possible conflict")).toBeInTheDocument();
    expect(screen.getByText("After the end date.")).toBeInTheDocument();
    expect(screen.queryByText("Bills cover it.")).toBeNull();
  });

  it("renders the sample grant's fixture: the waiting extension first, then L-1002", () => {
    render(<ProblemList rows={problemLists[SAMPLE_GRANT_ID].rows} />);
    expect(shownOrder()).toEqual(["terms_waiting:1 term waiting to be confirmed", "charge:L-1002"]);
  });

  it("says so when nothing is on the list", () => {
    render(<ProblemList rows={[]} />);
    expect(screen.getByText("Nothing on the problem list.")).toBeInTheDocument();
  });
});
