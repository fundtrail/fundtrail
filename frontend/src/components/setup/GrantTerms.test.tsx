import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError, type EvidenceFile, type ProblemRow } from "@/lib/api";
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
    // The value shows in the term's row and again in its open detail.
    expect(within(group).getAllByText("Jan 31, 2027")).toHaveLength(2);
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

describe("issue 269: the empty Terms panel and the waiting problem", () => {
  it("says none are in force yet while terms wait, and no terms yet when none do", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    const onlyWaiting = detail.terms.filter((t) => t.state === "waiting");
    const { unmount } = render(<GrantTerms terms={onlyWaiting} rows={rows} />, { wrapper: Wrapper });
    expect(screen.getByText("No terms in force yet. Confirm the ones waiting above.")).toBeInTheDocument();
    unmount();
    render(<GrantTerms terms={[]} rows={[]} />, { wrapper: Wrapper });
    expect(screen.getByText("No terms yet. They appear as the agent reads the award letter.")).toBeInTheDocument();
  });

  it("doesn't repeat the waiting problem's line on a waiting term, and keeps any other problem", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    const waitingProblem = { check: "terms", problem: "waiting", text: "This term waits for the accountant to confirm it." };
    const other = { check: "check-x", problem: "problem-x", text: "Another problem with this term." };
    const terms = detail.terms.map((t) =>
      t.record.id === "rec-period-extension"
        ? { ...t, status: { grant_id: "grant-sample", record_id: t.record.id, problems: [waitingProblem, other], flagged: true } }
        : t,
    );
    render(<GrantTerms terms={terms} rows={rows} />, { wrapper: Wrapper });
    expect(within(waitingGroup()).queryByText("This term waits for the accountant to confirm it.")).not.toBeInTheDocument();
    expect(within(waitingGroup()).getByText("Another problem with this term.")).toBeInTheDocument();
  });
});

describe("issue 274: Open the source opens the value's spot", () => {
  it("links each value to the viewer at its record and value", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    expect(within(waitingGroup()).getByRole("link", { name: "Open the source of end date" })).toHaveAttribute(
      "href",
      "/grants/grant-sample/files/file-extension-notice?record=rec-period-extension&value=end",
    );
  });
});

describe("a shared quote never hides a value", () => {
  it("shows the whole passage when one value sharing it has no known place in it", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    const filler = "lorem ipsum dolor sit amet ".repeat(8);
    const passage = `Principal Investigator: ${filler}Dr. Robin Example, robin.example@university.example`;
    const at = 1000;
    const location = { type: "char_location" as const, start_char_index: at, end_char_index: at + passage.length };
    const nameAt = at + passage.indexOf("Dr. Robin Example");
    const terms = detail.terms.map((t) => {
      if (t.record.id !== "rec-person-pi") return t;
      const data = t.record.data as unknown as Record<string, { value: unknown; citation: unknown }>;
      const cite = (highlight: unknown) => ({ file_id: "file-award-letter", passage, location, match: "exact", highlight });
      return {
        ...t,
        record: {
          ...t.record,
          data: {
            ...t.record.data,
            // The name has a stored range; the role and the email have none.
            name: { ...data.name, citation: cite([{ start_char_index: nameAt, end_char_index: nameAt + 17 }]) },
            role: { ...data.role, citation: cite(null) },
            email: { ...data.email, citation: cite(null) },
          },
        },
      } as typeof t;
    });
    render(<GrantTerms terms={terms} rows={rows} />, { wrapper: Wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Dr\. Robin Example/ }));
    const person = screen.getByRole("button", { name: /Dr\. Robin Example/ }).closest("article") as HTMLElement;
    const quote = within(person).getAllByRole("blockquote")[0]!;
    expect(quote.textContent).toBe(passage);
    expect(within(person).queryByRole("button", { name: "Show the whole quote" })).not.toBeInTheDocument();
  });
});

describe("issue 278: a file that isn't an award letter", () => {
  const FLAG = { check: "flag", problem: "not_an_award_letter", text: "This file doesn't read as an award letter." };
  const DUPLICATE = { check: "duplicate", problem: "same_file", text: "This file is already on the grant." };
  const FAILED_READ = { check: "read", problem: "failed", text: "The file couldn't be read." };

  async function fileProblem(id: string, name: string, problems: (typeof FLAG)[]) {
    const { rows, Wrapper } = await sampleTerms();
    const file = { ...(rows.find((r) => r.kind === "terms_waiting") as { file: EvidenceFile }).file, id, name };
    const row: ProblemRow = { kind: "record", status: { grant_id: "grant-sample", file_id: id, problems, flagged: true }, file };
    return { row, Wrapper };
  }

  it("shows a notice for a flagged file no term cites, with only the flag in the server's words, above the waiting terms", async () => {
    const { row, Wrapper } = await fileProblem("file-not-a-letter", "lunch_menu.pdf", [FLAG, DUPLICATE]);
    render(<GrantTerms terms={[]} rows={[row]} />, { wrapper: Wrapper });
    const notice = screen.getByRole("region", { name: "Problem with lunch_menu.pdf" });
    expect(within(notice).getByRole("link", { name: "lunch_menu.pdf" })).toHaveAttribute("href", "/grants/grant-sample/files/file-not-a-letter");
    expect(within(notice).getByText("This file doesn't read as an award letter.")).toBeInTheDocument();
    expect(within(notice).queryByText("This file is already on the grant.")).not.toBeInTheDocument();
    expect(notice.compareDocumentPosition(screen.getByRole("heading", { name: "Waiting for you" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("No terms yet.")).toBeInTheDocument();
  });

  it("shows no notice for a file with only a duplicate or a failed read", async () => {
    const duplicate = await fileProblem("file-dup", "invoice_copy.pdf", [DUPLICATE]);
    const failed = await fileProblem("file-bad", "scan.pdf", [FAILED_READ]);
    render(<GrantTerms terms={[]} rows={[duplicate.row, failed.row]} />, { wrapper: duplicate.Wrapper });
    expect(screen.queryByRole("region", { name: /^Problem with/ })).not.toBeInTheDocument();
    expect(screen.getByText("No terms yet. They appear as the agent reads the award letter.")).toBeInTheDocument();
  });

  it("shows no notice for a flagged file a term cites", async () => {
    const { detail } = await sampleTerms();
    const { row, Wrapper } = await fileProblem("file-award-letter", "award_letter.pdf", [FLAG]);
    render(<GrantTerms terms={detail.terms} rows={[row]} />, { wrapper: Wrapper });
    expect(screen.queryByRole("region", { name: /^Problem with/ })).not.toBeInTheDocument();
  });
});

describe("the page's one main button", () => {
  const mains = () => document.querySelectorAll(".ft-btn--main");

  it("is the single waiting term's Confirm when there's nothing to confirm all of", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    expect(mains()).toHaveLength(1);
    expect(mains()[0]).toHaveTextContent("Confirm");
    expect(within(waitingGroup()).getByRole("button", { name: "Reject" })).toHaveClass("ft-btn--reject");
  });

  it("is Confirm all when it shows, each term's own Confirm an outlined approve button", async () => {
    const { detail, Wrapper } = await sampleTerms();
    const ids = ["rec-period-extension", "rec-person-pi"];
    const terms = detail.terms.map((t) => (ids.includes(t.record.id) ? { ...t, state: "waiting" as const } : t));
    const notice = (await fakeHarness().client.getProblemList("grant-sample")).rows.find((r) => r.kind === "terms_waiting")!;
    render(<GrantTerms terms={terms} rows={[{ ...notice, record_ids: ids } as ProblemRow]} />, { wrapper: Wrapper });
    expect(mains()).toHaveLength(1);
    expect(mains()[0]).toHaveTextContent("Confirm all 2");
    for (const confirm of within(waitingGroup()).getAllByRole("button", { name: "Confirm" })) {
      expect(confirm).toHaveClass("ft-btn--approve");
      expect(confirm).not.toHaveClass("ft-btn--main");
    }
  });
});

describe("which terms open by themselves", () => {
  /** A term row's disclosure button, found by the values the closed row shows. */
  const rowOf = (name: RegExp) => screen.getByRole("button", { name });

  it("opens a waiting term, so its quote shows before it is confirmed", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    const row = within(waitingGroup()).getByRole("button", { name: /Jan 31, 2027/ });
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(within(waitingGroup()).getByText(/This amendment extends the end date/)).toBeInTheDocument();
  });

  it("keeps a confirmed term in force closed, with its values but not its quotes, until it is clicked", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    const row = rowOf(/Dr\. Robin Example/);
    expect(row).toHaveAttribute("aria-expanded", "false");
    expect(row).toHaveTextContent("Dr. Robin Example");
    expect(screen.queryByText(/Principal Investigator: Dr. Robin Example/)).not.toBeInTheDocument();
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Principal Investigator: Dr. Robin Example/)).toBeInTheDocument();
  });

  it("opens a term in force with a value that couldn't be found", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    const terms = detail.terms.map((t) =>
      t.record.id === "rec-person-pi" ? { ...t, values: [{ path: "email", confirmed: false }] } : t,
    );
    render(<GrantTerms terms={terms} rows={rows} />, { wrapper: Wrapper });
    expect(rowOf(/Dr\. Robin Example/)).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("list", { name: "Values not confirmed" })).toHaveTextContent("Email");
    expect(rowOf(/Dr\. Jesse Sample/)).toHaveAttribute("aria-expanded", "false");
  });

  it("opens a term in force with a problem", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    const problem = { check: "check-x", problem: "problem-x", text: "A problem code found with this term." };
    const terms = detail.terms.map((t) =>
      t.record.id === "rec-approval-rule"
        ? { ...t, status: { grant_id: "grant-sample", record_id: t.record.id, problems: [problem], flagged: true } }
        : t,
    );
    render(<GrantTerms terms={terms} rows={rows} />, { wrapper: Wrapper });
    expect(rowOf(/Applies to/)).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("A problem code found with this term.")).toBeInTheDocument();
  });

  it("puts the terms no check uses in one closed group at the end", async () => {
    const { detail, Wrapper } = await sampleTerms();
    const terms = detail.terms.map((t) => (t.record.id === "rec-period" ? { ...t, state: "replaced" as const } : t));
    render(<GrantTerms terms={terms} rows={[]} />, { wrapper: Wrapper });
    const toggle = screen.getByRole("button", { name: /Not in force/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Replaced")).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.getByText("Replaced")).toBeInTheDocument();
  });

  it("opens the closed group when a term in it has a problem", async () => {
    const { detail, Wrapper } = await sampleTerms();
    const problem = { check: "check-x", problem: "problem-x", text: "A problem with the replaced term." };
    const terms = detail.terms.map((t) =>
      t.record.id === "rec-period"
        ? { ...t, state: "replaced" as const, status: { grant_id: "grant-sample", record_id: t.record.id, problems: [problem], flagged: true } }
        : t,
    );
    render(<GrantTerms terms={terms} rows={[]} />, { wrapper: Wrapper });
    expect(screen.getByRole("button", { name: /Not in force/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("A problem with the replaced term.")).toBeInTheDocument();
  });

  it("puts a rejected term first in the Terms panel, open, with Type the right value and its thread in reach", async () => {
    const { detail, Wrapper } = await sampleTerms();
    const terms = detail.terms.map((t) => (t.record.id === "rec-period-extension" ? { ...t, state: "rejected" as const } : t));
    render(<GrantTerms terms={terms} rows={[]} />, { wrapper: Wrapper });
    const panel = screen.getByRole("region", { name: "Terms" });
    const groups = within(panel).getAllByRole("group");
    expect(groups[0]).toHaveAccessibleName("Rejected");
    expect(within(groups[0]!).getByRole("button", { name: /Jan 31, 2027/ })).toHaveAttribute("aria-expanded", "true");
    expect(within(groups[0]!).getByText("Rejected", { selector: ".ft-tag" })).toBeInTheDocument();
    expect(within(groups[0]!).getByRole("button", { name: "Type the right value" })).toBeInTheDocument();
    expect(within(groups[0]!).getByRole("link", { name: "Open the term's thread" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Not in force/ })).not.toBeInTheDocument();
  });

  it("opens a row when a problem arrives after it was first shown", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    const { rerender } = render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    expect(rowOf(/Dr\. Jesse Sample/)).toHaveAttribute("aria-expanded", "false");
    const problem = { check: "check-x", problem: "problem-x", text: "A problem that came later." };
    const later = detail.terms.map((t) =>
      t.record.id === "rec-person-program-officer"
        ? { ...t, status: { grant_id: "grant-sample", record_id: t.record.id, problems: [problem], flagged: true } }
        : t,
    );
    rerender(<GrantTerms terms={later} rows={rows} />);
    expect(rowOf(/Dr\. Jesse Sample/)).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("A problem that came later.")).toBeInTheDocument();
  });

  it("opens a row the accountant closed when a new problem arrives", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    const { rerender } = render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    const row = rowOf(/Dr\. Jesse Sample/);
    fireEvent.click(row);
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "false");
    const problem = { check: "check-x", problem: "problem-x", text: "A new problem after the row was closed." };
    const later = detail.terms.map((t) =>
      t.record.id === "rec-person-program-officer"
        ? { ...t, status: { grant_id: "grant-sample", record_id: t.record.id, problems: [problem], flagged: true } }
        : t,
    );
    rerender(<GrantTerms terms={later} rows={rows} />);
    expect(rowOf(/Dr\. Jesse Sample/)).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("A new problem after the row was closed.")).toBeInTheDocument();
  });

  it("opens the Not in force group the accountant closed when a term in it gets a new problem", async () => {
    const { detail, Wrapper } = await sampleTerms();
    const replaced = detail.terms.map((t) => (t.record.id === "rec-period" ? { ...t, state: "replaced" as const } : t));
    const { rerender } = render(<GrantTerms terms={replaced} rows={[]} />, { wrapper: Wrapper });
    const toggle = screen.getByRole("button", { name: /Not in force/ });
    fireEvent.click(toggle);
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    const problem = { check: "check-x", problem: "problem-x", text: "A new problem on the replaced term." };
    const later = replaced.map((t) =>
      t.record.id === "rec-period" ? { ...t, status: { grant_id: "grant-sample", record_id: t.record.id, problems: [problem], flagged: true } } : t,
    );
    rerender(<GrantTerms terms={later} rows={[]} />);
    expect(screen.getByRole("button", { name: /Not in force/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("remembers the accountant's own click on a row", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    const row = within(waitingGroup()).getByRole("button", { name: /Jan 31, 2027/ });
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "false");
  });

  it("groups terms in force by kind, with a count where there is more than one", async () => {
    const { detail, Wrapper } = await sampleTerms();
    render(<GrantTerms terms={detail.terms} rows={[]} />, { wrapper: Wrapper });
    const budget = screen.getByRole("group", { name: "Budget lines" });
    expect(within(budget).getByRole("heading")).toHaveTextContent(/^Budget lines 4 terms$/);
    expect(within(screen.getByRole("group", { name: "Approval rules" })).getByRole("heading")).toHaveTextContent(/^Approval rules$/);
  });

  it("shows a passage that consecutive values share once, each value keeping its own link", async () => {
    const { detail, rows, Wrapper } = await sampleTerms();
    render(<GrantTerms terms={detail.terms} rows={rows} />, { wrapper: Wrapper });
    fireEvent.click(rowOf(/Dr\. Robin Example/));
    const person = rowOf(/Dr\. Robin Example/).closest("article") as HTMLElement;
    // Name, role and email quote the same line, so it shows once; the document date quotes another.
    expect(within(person).getAllByText(/Principal Investigator: Dr. Robin Example/)).toHaveLength(1);
    expect(within(person).getAllByRole("blockquote")).toHaveLength(2);
    const links = within(person).getAllByRole("link", { name: /^Open the source of / });
    expect(links.map((l) => l.getAttribute("aria-label"))).toEqual([
      "Open the source of name",
      "Open the source of role",
      "Open the source of email",
      "Open the source of document date",
    ]);
    expect(links[0]).toHaveAttribute("href", "/grants/grant-sample/files/file-award-letter?record=rec-person-pi&value=name");
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
