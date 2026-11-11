import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Citation, Match } from "@/lib/api";
import { quoteExcerpt, TermQuote, valueSpans } from "./TermQuote";

// A file's text, and a citation of one passage in it at character 100.
const BEFORE = "x".repeat(100);

function cite(passage: string, match: Match | null, value?: string): Citation & { passage: string } {
  const start = BEFORE.length;
  const at = value ? start + passage.indexOf(value) : -1;
  return {
    file_id: "file-1",
    passage,
    location: { type: "char_location", start_char_index: start, end_char_index: start + passage.length },
    match,
    highlight: value ? [{ start_char_index: at, end_char_index: at + value.length }] : null,
  };
}

function show(citation: Citation & { passage: string }) {
  return render(<TermQuote citation={citation} spans={valueSpans(citation)} />);
}

const SHORT = "Period of Performance End Date: January 31, 2026";

describe("TermQuote's highlighter", () => {
  it("marks an exact match", () => {
    const { container } = show(cite(SHORT, "exact"));
    expect(container.querySelector("mark")).toHaveTextContent(SHORT);
    expect(screen.queryByText("Close match on the page")).not.toBeInTheDocument();
  });

  it("shows a close match in the serif without the highlighter, and says it's a close match", () => {
    const { container } = show(cite(SHORT, "close"));
    expect(container.querySelector("mark")).toBeNull();
    expect(container.querySelector("blockquote")).toHaveClass("is-close");
    expect(screen.getByText("Close match on the page")).toBeInTheDocument();
  });

  it("shows a passage that wasn't found, or a box on an image, plain", () => {
    const notFound = show(cite(SHORT, "not_found"));
    expect(notFound.container.querySelector("mark")).toBeNull();
    expect(notFound.container.querySelector("blockquote")).toHaveClass("is-plain");
    notFound.unmount();
    const box: Citation & { passage: string } = {
      file_id: "file-2",
      passage: "Total $38.50",
      location: { type: "image_box", left: 0.1, top: 0.2, width: 0.3, height: 0.05 },
      match: null,
    };
    const { container } = show(box);
    expect(container.querySelector("mark")).toBeNull();
    expect(container.querySelector("blockquote")).toHaveClass("is-plain");
  });

  it("never highlights a box on an image, even as an exact match", () => {
    const box: Citation & { passage: string } = {
      file_id: "file-2",
      passage: "Total $38.50",
      location: { type: "image_box", left: 0.1, top: 0.2, width: 0.3, height: 0.05 },
      match: "exact",
    };
    const { container } = show(box);
    expect(container.querySelector("mark")).toBeNull();
    expect(container.querySelector("blockquote")).toHaveClass("is-plain");
  });
});

describe("TermQuote's excerpt", () => {
  // Four lines of a notice, the value on the fourth.
  const LONG =
    "Special conditions: Funds budgeted for participant support costs may not be diverted by the awardee to other " +
    "categories of expense without the prior written approval of the cognizant NSF Program Officer, requested in " +
    "writing at least thirty days before the change and kept with the award file for the life of the award, and " +
    "the request must be made through Research.gov by the principal investigator.";

  it("shows the part of a long quote that holds the value, set stronger, and opens the rest in place", () => {
    const { container } = show(cite(LONG, "exact", "Research.gov"));
    const quote = container.querySelector("blockquote")!;
    expect(quote.textContent).toMatch(/^… .*through Research\.gov by the principal investigator\.$/);
    expect(quote.textContent).not.toContain("Special conditions");
    expect(quote.querySelector("strong")).toHaveTextContent(/^Research\.gov$/);
    const toggle = screen.getByRole("button", { name: "Show the whole quote" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(quote.textContent).toBe(LONG);
    expect(screen.getByRole("button", { name: "Show less" })).toHaveAttribute("aria-expanded", "true");
  });

  it("never cuts a quote when the value's place in it isn't known", () => {
    const { container } = show(cite(LONG, "exact"));
    expect(container.querySelector("blockquote")!.textContent).toBe(LONG);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows the whole quote when the values' ranges together spread wider than the window", () => {
    // Two values, one near the start and one near the end of the long passage.
    const spans = [
      { start: 0, end: 18 },
      { start: LONG.indexOf("Research.gov"), end: LONG.indexOf("Research.gov") + 12 },
    ];
    expect(quoteExcerpt(LONG, spans)).toBeNull();
  });

  it("shows the whole quote for a single value whose ranges are far apart", () => {
    const at = BEFORE.length;
    const far: Citation & { passage: string } = {
      ...cite(LONG, "exact"),
      highlight: [
        { start_char_index: at + 20, end_char_index: at + 29 },
        { start_char_index: at + LONG.length - 30, end_char_index: at + LONG.length - 20 },
      ],
    };
    const { container } = show(far);
    expect(container.querySelector("blockquote")!.textContent).toBe(LONG);
    expect(screen.queryByRole("button", { name: "Show the whole quote" })).not.toBeInTheDocument();
  });

  it("doesn't cut a short quote", () => {
    expect(quoteExcerpt(SHORT, [{ start: 32, end: 48 }])).toBeNull();
  });

  it("reads the value's place from the stored ranges, measured from the passage", () => {
    expect(valueSpans(cite(SHORT, "exact", "January 31, 2026"))).toEqual([{ start: 32, end: 48 }]);
    expect(valueSpans(cite(SHORT, "exact"))).toBeNull();
  });
});
