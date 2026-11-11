import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GrantSummary } from "@/lib/api";
import { sampleSummary } from "@/lib/api/fixtures/grant";
import { CloseoutSteps } from "./CloseoutSteps";

const STEPS = [
  ["Notice of Expiration", "90 days before the end date. The university asks for a review of every charge."],
  ["End date", "The last day of the period of performance."],
  ["Adjustment period", "From the end date until the books close two months later."],
  ["Award Closeout Certification", "Due at the close of the 2nd month."],
  ["Final financial report", "Filed by central accounting by day 90. FundTrail isn't involved."],
] as const;

function steps() {
  return within(screen.getByRole("list")).getAllByRole("listitem");
}

describe("CloseoutSteps", () => {
  it("draws every step with its description, in order", () => {
    render(<CloseoutSteps summary={sampleSummary} />);
    const items = steps();
    expect(items).toHaveLength(STEPS.length);
    STEPS.forEach(([name, when], i) => {
      expect(items[i]).toHaveTextContent(name);
      expect(items[i]).toHaveTextContent(when);
    });
  });

  it("shows a date under End date only, and it's the end date in force", () => {
    render(<CloseoutSteps summary={sampleSummary} />);
    const items = steps();
    // The fixture's end date is 2026-01-31 and its next closeout date is 2026-05-01.
    expect(items[1]).toHaveTextContent("Jan 31, 2026");
    for (const item of items) expect(item).not.toHaveTextContent("May 1, 2026");
    items
      .filter((_, i) => i !== 1)
      .forEach((item) => expect(item).not.toHaveTextContent(/\d{4}/));
  });

  it("shows the server's next step in its own words in the summary line", () => {
    render(<CloseoutSteps summary={sampleSummary} />);
    const summary = screen.getByTestId("closeout-summary");
    expect(summary).toHaveTextContent("Next: Final financial report due, May 1, 2026.");
    expect(summary).toHaveTextContent("End date in force: Jan 31, 2026.");
  });

  it("marks no step as current or passed", () => {
    const { container } = render(<CloseoutSteps summary={sampleSummary} />);
    expect(container.querySelector("[aria-current]")).toBeNull();
    for (const item of steps()) {
      expect(item).toHaveAttribute("class", "ft-co-step");
      expect(item).not.toHaveTextContent("Now");
    }
  });

  it("says so when no end date is confirmed, and shows no next step the server didn't send", () => {
    const summary: GrantSummary = { ...sampleSummary, end_date: null, next_closeout: null };
    render(<CloseoutSteps summary={summary} />);
    expect(screen.getByTestId("closeout-summary")).toHaveTextContent("End date not confirmed yet.");
    expect(screen.getByTestId("closeout-summary")).not.toHaveTextContent("Next:");
    steps().forEach((item) => expect(item).not.toHaveTextContent(/\d{4}/));
  });
});
