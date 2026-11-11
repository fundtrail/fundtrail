import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GrantSummary, ReadingProgress } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { AgentProgressLine } from "./AgentProgress";

async function summaryWith(fields: { reading?: ReadingProgress | null; last_run_summary?: string | null }): Promise<GrantSummary> {
  const { summary } = await createFakeApiClient().getGrant(SAMPLE_GRANT_ID);
  return { ...summary, reading: undefined, last_run_summary: undefined, ...fields };
}

const progress = (files_read: number, files_total: number, lines_read: number, lines_total: number): ReadingProgress => ({ files_read, files_total, lines_read, lines_total });

describe("the agent's progress line (ruling 71)", () => {
  it.each([
    ["files only", progress(3, 8, 0, 0), "The agent is reading: 3 of 8 files."],
    ["ledger lines only", progress(0, 0, 12, 40), "The agent is reading: 12 of 40 ledger lines."],
    ["both", progress(3, 8, 12, 40), "The agent is reading: 3 of 8 files, 12 of 40 ledger lines."],
    ["one of each", progress(0, 1, 1, 1), "The agent is reading: 0 of 1 file, 1 of 1 ledger line."],
  ])("formats the server's numbers while reading %s", async (_, reading, words) => {
    render(<AgentProgressLine summary={await summaryWith({ reading, last_run_summary: "Read invoice_1001.txt." })} />);
    expect(screen.getByRole("status")).toHaveTextContent(words);
    // Reading wins over the last run's summary.
    expect(screen.queryByText("Read invoice_1001.txt.")).toBeNull();
  });

  it("says nothing of reading when neither total is above zero, and shows the last run's summary as when not reading", async () => {
    const { unmount } = render(<AgentProgressLine summary={await summaryWith({ reading: progress(0, 0, 0, 0) })} />);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    unmount();
    render(<AgentProgressLine summary={await summaryWith({ reading: progress(0, 0, 0, 0), last_run_summary: "Answered the thread on L-1002." })} />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Answered the thread on L-1002.");
    expect(status).not.toHaveTextContent("The agent is reading");
  });

  it("shows the last run's summary in the server's words when nothing is being read", async () => {
    render(<AgentProgressLine summary={await summaryWith({ reading: null, last_run_summary: "Read extension_notice.txt: a new end date, waiting for the accountant." })} />);
    expect(screen.getByRole("status")).toHaveTextContent("Read extension_notice.txt: a new end date, waiting for the accountant.");
    expect(screen.getByRole("status")).not.toHaveTextContent("The agent is reading");
  });

  it("shows nothing when neither field is present", async () => {
    render(<AgentProgressLine summary={await summaryWith({})} />);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("doesn't touch the status region when a refetch brings the same numbers", async () => {
    const { rerender } = render(<AgentProgressLine summary={await summaryWith({ reading: progress(3, 8, 12, 40) })} />);
    const region = screen.getByRole("status");
    const changes: MutationRecord[] = [];
    const observer = new MutationObserver((records) => changes.push(...records));
    observer.observe(region, { subtree: true, childList: true, characterData: true, attributes: true });
    rerender(<AgentProgressLine summary={await summaryWith({ reading: progress(3, 8, 12, 40) })} />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    observer.disconnect();
    expect(changes).toHaveLength(0);
    expect(screen.getByRole("status")).toBe(region);
    // New numbers do change it, once.
    rerender(<AgentProgressLine summary={await summaryWith({ reading: progress(4, 8, 12, 40) })} />);
    expect(region).toHaveTextContent("The agent is reading: 4 of 8 files, 12 of 40 ledger lines.");
  });
});
