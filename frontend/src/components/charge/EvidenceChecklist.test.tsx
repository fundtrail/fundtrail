import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ChecklistEntry, EvidenceFile, FtRecord, LinkView } from "@/lib/api";
import { EvidenceChecklist } from "./EvidenceChecklist";

function record(id: string, author: "agent" | "user", data: Record<string, unknown>): FtRecord {
  return {
    id,
    workspace_id: "ws",
    grant_id: "g",
    author,
    author_user_id: author === "user" ? "u" : null,
    written_at: "2026-03-01T10:00:00Z",
    replaces_id: null,
    data: data as unknown as FtRecord["data"],
  } as FtRecord;
}

const invoiceFile = { id: "f-inv", name: "invoice_1001.txt" } as EvidenceFile;
const bill = record("r-bill", "agent", {
  kind: "bill",
  total: { value: 124_000, text: "$1,240.00", citation: { file_id: "f-inv", passage: "$1,240.00", location: { type: "char_location" } } },
});
const link = record("r-link", "agent", { kind: "link", record_id: "r-bill", charge_id: "c", amount_cents: 124_000 });
const linkView = { link, record: bill, values: [], file: invoiceFile } as unknown as LinkView;
const removal = record("r-removal", "agent", { kind: "checklist_removal", charge_id: "c", default_item: "participant_list", reason: "The invoice is for a laptop, not a participant." });

function entry(over: Partial<ChecklistEntry>): ChecklistEntry {
  return {
    item_record_id: null,
    default_item: null,
    added_by: "default",
    needed: "",
    amount_cents: null,
    expected_by: null,
    filled: false,
    link_ids: [],
    removal_waiting_id: null,
    ...over,
  } as ChecklistEntry;
}

const checklist: ChecklistEntry[] = [
  entry({ default_item: "bill", needed: "A bill that adds up to the charge", amount_cents: 124_000, filled: true, link_ids: ["r-link"] }),
  entry({ item_record_id: "r-item", added_by: "agent", needed: "Per diem, 5 days at $100 a day", expected_by: "2026-04-15" }),
  entry({ default_item: "participant_list", needed: "Participant list", removal_waiting_id: "r-removal" }),
  entry({ item_record_id: "r-user-item", added_by: "user", needed: "Conference agenda", filled: true }),
];

function renderChecklist() {
  render(
    <EvidenceChecklist
      checklist={checklist}
      links={[linkView]}
      waiting={[{ record: removal, replaces: null, charge_ids: ["c"] }]}
      records={{ [bill.id]: bill, [link.id]: link, [removal.id]: removal }}
      files={{ [invoiceFile.id]: invoiceFile }}
    />,
  );
}

function item(name: string): HTMLElement {
  return screen.getByText(name).closest("li")!;
}

describe("EvidenceChecklist", () => {
  it("shows each item filled or missing, in words", () => {
    renderChecklist();
    expect(within(item("A bill that adds up to the charge")).getByText("Filled")).toBeInTheDocument();
    expect(within(item("Per diem, 5 days at $100 a day")).getByText("Missing")).toBeInTheDocument();
    expect(within(item("Participant list")).getByText("Missing")).toBeInTheDocument();
  });

  it("says who added each item", () => {
    renderChecklist();
    expect(within(item("A bill that adds up to the charge")).getByText(/Account default/)).toBeInTheDocument();
    expect(within(item("Per diem, 5 days at $100 a day")).getByText(/Added by the agent/)).toBeInTheDocument();
    expect(within(item("Conference agenda")).getByText(/Added by the accountant/)).toBeInTheDocument();
  });

  it("names what fills an item, its amount, and when a missing one is expected", () => {
    renderChecklist();
    const filled = item("A bill that adds up to the charge");
    expect(within(filled).getByText("$1,240.00")).toBeInTheDocument();
    expect(within(filled).getByText(/Filled by Bill, invoice_1001.txt/)).toBeInTheDocument();
    expect(within(item("Per diem, 5 days at $100 a day")).getByText(/Expected by Apr 15, 2026/)).toBeInTheDocument();
  });

  it("shows a removal waiting under its item, with the agent's reason", () => {
    renderChecklist();
    const row = item("Participant list");
    const box = within(row).getByTestId("suggestion");
    expect(within(box).getByText('Remove "Participant list" from the checklist', { selector: "p" })).toBeInTheDocument();
    expect(within(box).getByText("The invoice is for a laptop, not a participant.")).toBeInTheDocument();
    expect(within(box).getByText("Waiting for you")).toBeInTheDocument();
    expect(screen.getAllByTestId("suggestion")).toHaveLength(1);
  });

  it("decides a waiting removal in one place: the thread, not the checklist", () => {
    renderChecklist();
    const row = item("Participant list");
    expect(within(row).queryByRole("button")).toBeNull();
    expect(within(row).getByText("Accept or reject it in the review thread.")).toBeInTheDocument();
  });

  it("says so when the checklist is empty", () => {
    render(<EvidenceChecklist checklist={[]} links={[]} waiting={[]} records={{}} files={{}} />);
    expect(screen.getByText("No items on the checklist yet.")).toBeInTheDocument();
  });
});
