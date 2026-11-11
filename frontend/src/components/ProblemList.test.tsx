import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Charge, ChargeStatus, EvidenceFile, FtRecord, ProblemRow, Reason } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { UNREADABLE_FROM_LABEL } from "@/lib/format";
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

  it("renders the sample grant's fixture: the waiting extension, the held mail, then L-1002", async () => {
    const { rows } = await createFakeApiClient().getProblemList(SAMPLE_GRANT_ID);
    render(<ProblemList rows={rows} />);
    expect(shownOrder()).toEqual(["terms_waiting:1 term waiting to be confirmed", "held_mail:The sender isn't a known sender. · billing@labsupply.example", "charge:L-1002"]);
  });

  it("links each row to its page", async () => {
    const { rows } = await createFakeApiClient().getProblemList(SAMPLE_GRANT_ID);
    render(<ProblemList rows={rows} />);
    const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual(["/grants/grant-sample/terms", "/w/ws-sample/mail", "/grants/grant-sample/charges/chg-l-1002"]);
  });

  it("shows when a missing item is expected and marks an accepted reason", () => {
    const missing = { ...reason("missing_evidence", "A bill isn't on file."), expected_by: "2025-12-18" };
    const accepted = { ...reason("needs_human", "The agent is unsure."), accepted_by: "rec-accept" };
    render(<ProblemList rows={[{ kind: "charge", charge: charge("c1", "L-1", "2025-01-01", "A charge"), status: status("needs_human", [missing, accepted]) }]} />);
    expect(screen.getByText(/Expected by Dec 18, 2025/)).toBeInTheDocument();
    expect(within(screen.getByText("The agent is unsure.")).getByText("Accepted")).toBeInTheDocument();
  });

  it("says the From line couldn't be read for held mail with no sender, in place of the hold reason", async () => {
    const { rows } = await createFakeApiClient().getProblemList(SAMPLE_GRANT_ID);
    const held = rows.find((r) => r.kind === "held_mail");
    if (held?.kind !== "held_mail") throw new Error("the sample's problem list has no held mail");
    render(<ProblemList rows={[{ ...held, held: { ...held.held, sender: null, reason: "unverified_sender" } }]} />);
    expect(screen.getByText(UNREADABLE_FROM_LABEL)).toBeInTheDocument();
    expect(screen.queryByText(/couldn't be verified/)).toBeNull();
  });

  it("names a record that has no file by its kind and date", () => {
    render(
      <ProblemList
        rows={[
          {
            kind: "record",
            status: { grant_id: "g", record_id: "r1", file_id: null, problems: [{ check: "terms", problem: "disagree", text: "Confirmed terms disagree.", record_ids: [] }], flagged: true, accepted: false, snoozed: false },
            record: { id: "r1", workspace_id: "ws", grant_id: "g", author: "agent", author_user_id: null, written_at: "2026-03-02T10:00:00Z", replaces_id: null, data: { kind: "approval_rule" } as unknown as FtRecord["data"] },
            file: null,
          },
        ]}
      />,
    );
    expect(screen.getByText("Approval rule, written Mar 2, 2026")).toBeInTheDocument();
  });

  it("has no filter tabs unless asked, as on the closeout page", () => {
    render(<ProblemList rows={rows} />);
    expect(screen.queryByRole("group", { name: "Show on the problem list" })).toBeNull();
  });

  it("filters on screen by bucket, counting the rows the server sent, and keeps their order", () => {
    render(<ProblemList rows={rows} variant="pick" tabs />);
    expect(screen.getByRole("button", { name: "All 5" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Possible conflict 1" }));
    expect(shownOrder()).toEqual(["charge:L-1"]);
    fireEvent.click(screen.getByRole("button", { name: "All 5" }));
    expect(shownOrder()).toHaveLength(5);
  });

  it("picks a row on a plain click and leaves its link to its page", () => {
    const onSelect = vi.fn();
    render(<ProblemList rows={rows} onSelect={onSelect} selected="charge:c1" variant="pick" />);
    const link = screen.getByRole("link", { name: "Oldest conflict" });
    expect(link).toHaveAttribute("href", "/grants/g/charges/c1");
    expect(link).toHaveAttribute("aria-current", "true");
    fireEvent.click(screen.getByRole("link", { name: "Middle human" }));
    expect(onSelect).toHaveBeenLastCalledWith("charge:c2");
    // A click with a modifier key opens the page instead.
    fireEvent.click(screen.getByRole("link", { name: "Newest missing" }), { metaKey: true });
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("shows every reason, the ledger line, date and vendor, and when a missing item is expected, beside the picked item", () => {
    const missing = { ...reason("missing_evidence", "A bill isn't on file."), expected_by: "2025-12-18" };
    const two = status("needs_human", [reason("needs_human", "The agent is unsure."), missing]);
    const withVendor = { ...charge("c1", "L-1", "2025-01-01", "A charge"), vendor: "Example Vendor" };
    render(<ProblemList rows={[{ kind: "charge", charge: withVendor, status: two }]} variant="pick" />);
    expect(screen.getByText("The agent is unsure.")).toBeInTheDocument();
    expect(screen.getByText(/A bill isn't on file\./)).toBeInTheDocument();
    expect(screen.getByText(/Expected by Dec 18, 2025/)).toBeInTheDocument();
    expect(screen.getByText("L-1")).toBeInTheDocument();
    expect(screen.getByText("Jan 1, 2025")).toBeInTheDocument();
    expect(screen.getByText(/Example Vendor/)).toBeInTheDocument();
  });

  it("says so when nothing is on the list", () => {
    render(<ProblemList rows={[]} />);
    expect(screen.getByText("Nothing on the problem list.")).toBeInTheDocument();
  });
});
