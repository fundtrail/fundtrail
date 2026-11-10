import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError, type ProblemRow } from "@/lib/api";
import { extensionWithUnfoundEnd, SAMPLE_REUSABLE_NOTE } from "@/lib/api/fixtures/setup";
import { GrantTerms } from "./GrantTerms";
import { ReusableNotes } from "./ReusableNotes";
import { fakeHarness } from "./testing";

async function sampleTerms() {
  const { client, writeRecord, Wrapper } = fakeHarness();
  const detail = await client.getGrant("grant-sample");
  const list = await client.getProblemList("grant-sample");
  return { detail, rows: list.rows, writeRecord, Wrapper };
}

function waitingGroup() {
  return screen.getByRole("region", { name: "Terms waiting from extension_notice.txt" });
}

describe("GrantTerms", () => {
  it("groups waiting terms by source document, with the server's text", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    const group = waitingGroup();
    expect(within(group).getByText("1 term waiting to be confirmed")).toBeInTheDocument();
    expect(within(group).getByText("Jan 31, 2027")).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "Confirm" })).toBeInTheDocument();
  });

  it("confirming a term writes a confirmation naming it", async () => {
    const { detail, rows, writeRecord, Wrapper } = await sampleTerms();
    render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    fireEvent.click(within(waitingGroup()).getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(within(waitingGroup()).getByRole("status")).toHaveTextContent("Confirmed."));
    expect(writeRecord).toHaveBeenCalledWith("grant-sample", {
      data: { kind: "confirmation", record_ids: ["rec-period-extension"], decision: "confirmed" },
    });
  });

  it("rejecting a term writes a rejection", async () => {
    const { detail, rows, writeRecord, Wrapper } = await sampleTerms();
    render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    fireEvent.click(within(waitingGroup()).getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(writeRecord).toHaveBeenCalled());
    expect(writeRecord.mock.calls[0]![1]).toEqual({
      data: { kind: "confirmation", record_ids: ["rec-period-extension"], decision: "rejected" },
    });
  });

  it("typing the right value saves a term that replaces the agent's", async () => {
    const { detail, rows, writeRecord, Wrapper } = await sampleTerms();
    render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    const group = waitingGroup();
    fireEvent.click(within(group).getByRole("button", { name: "Type the right value" }));
    fireEvent.change(within(group).getByLabelText("End date"), { target: { value: "2027-02-28" } });
    fireEvent.click(within(group).getByRole("button", { name: "Save typed value" }));
    await waitFor(() => expect(writeRecord).toHaveBeenCalled());
    expect(writeRecord.mock.calls[0]![1]).toEqual({
      data: { kind: "period_of_performance", end: { value: "2027-02-28" }, dated: { value: "2026-01-15" } },
      replaces_id: "rec-period-extension",
    });
  });

  it("lists each value that couldn't be found in the file", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    const terms = detail.terms.map((t) => (t.record.id === "rec-period-extension" ? extensionWithUnfoundEnd() : t));
    render(<GrantTerms terms={terms} rows={rows} />, { wrapper: Wrapper });
    const list = within(waitingGroup()).getByRole("list", { name: "Values not confirmed" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["End date"]);
  });

  it("shows the write check's problems as the server words them", async () => {
    const { detail, rows, writeRecord, Wrapper } = await sampleTerms();
    writeRecord.mockRejectedValueOnce(new ApiError(422, ["The record is already confirmed."]));
    render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    fireEvent.click(within(waitingGroup()).getByRole("button", { name: "Confirm" }));
    expect(await within(waitingGroup()).findByRole("alert")).toHaveTextContent("The record is already confirmed.");
  });

  it("offers to type the right value after rejecting, replacing the rejected term", async () => {
    const { detail, rows, writeRecord, Wrapper } = await sampleTerms();
    render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    const group = waitingGroup();
    fireEvent.click(within(group).getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(within(group).getByRole("status")).toHaveTextContent("Rejected."));
    fireEvent.click(within(group).getByRole("button", { name: "Type the right value" }));
    fireEvent.click(within(group).getByRole("button", { name: "Save typed value" }));
    await waitFor(() => expect(writeRecord).toHaveBeenCalledTimes(2));
    expect(writeRecord.mock.calls[1]![1]).toMatchObject({ replaces_id: "rec-period-extension" });
  });

  it("offers to type the right value on an agent term the server says was rejected, and links its thread", async () => {
    const { detail, Wrapper } = await sampleTerms();
    const rejected = detail.terms.filter((t) => t.record.id === "rec-period-extension").map((t) => ({ ...t, state: "rejected" as const }));
    render(<GrantTerms terms={rejected} rows={[]} />, { wrapper: Wrapper });
    expect(screen.getByRole("button", { name: "Type the right value" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the term's thread" })).toHaveAttribute("href", "/grants/grant-sample/records/rec-period-extension");
  });

  it("hides each term's buttons once all of a document's terms are confirmed", async () => {
    const { detail, writeRecord, Wrapper } = await sampleTerms();
    const ids = ["rec-period-extension", "rec-person-pi"];
    const terms = detail.terms.map((t) => (ids.includes(t.record.id) ? { ...t, state: "waiting" as const } : t));
    const notice = (await fakeHarness().client.getProblemList("grant-sample")).rows.find((r) => r.kind === "terms_waiting")!;
    const rows: ProblemRow[] = [{ ...notice, record_ids: ids } as ProblemRow];
    render(<GrantTerms terms={terms} rows={rows} />, { wrapper: Wrapper });
    const group = waitingGroup();
    fireEvent.click(within(group).getByRole("button", { name: "Confirm all 2" }));
    await waitFor(() => expect(within(group).getByText("All 2 confirmed.")).toBeInTheDocument());
    expect(writeRecord.mock.calls[0]![1]).toEqual({ data: { kind: "confirmation", record_ids: ids, decision: "confirmed" } });
    expect(within(group).queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
  });

  it("says so when nothing waits", async () => {
    const { detail, Wrapper } = await sampleTerms();
    const rows: ProblemRow[] = [];
    const terms = detail.terms.filter((t) => t.state !== "waiting");
    render(<GrantTerms terms={terms} rows={rows} />, { wrapper: Wrapper });
    expect(screen.getByText("No terms are waiting to be confirmed.")).toBeInTheDocument();
  });
});

describe("ReusableNotes", () => {
  it("shows what a note excuses, who wrote it and when, and its limits", () => {
    render(<ReusableNotes notes={[SAMPLE_REUSABLE_NOTE]} />);
    expect(screen.getByText("“The core sends one usage statement a quarter.”")).toBeInTheDocument();
    expect(screen.getByText(/Written by the accountant, Apr 9, 2026/)).toBeInTheDocument();
    expect(screen.getByText("$2,180.00")).toBeInTheDocument();
    expect(screen.getByText("None yet.")).toBeInTheDocument();
  });

  it("lists every charge a note covered", () => {
    const covered = [{ ...SAMPLE_REUSABLE_NOTE.charge, id: "chg-x", ledger_line_id: "L-2001" }];
    render(<ReusableNotes notes={[{ ...SAMPLE_REUSABLE_NOTE, covered }]} />);
    expect(within(screen.getByRole("list", { name: "Charges it covered" })).getByRole("link", { name: "L-2001" })).toBeInTheDocument();
  });
});
