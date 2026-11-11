import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Citation, EvidenceFile } from "@/lib/api";
import { Quote } from "./Decide";

const files = { "f-1": { id: "f-1", name: "statement.pdf" } as EvidenceFile };

function citation(over: Partial<Citation>): Citation {
  return {
    file_id: "f-1",
    passage: "Run 7 was completed on February 20, 2026",
    location: { type: "page_location", start_page_number: 2, end_page_number: 3 },
    match: "exact",
    ...over,
  } as Citation;
}

function marked(container: HTMLElement): HTMLElement | null {
  return container.querySelector("mark");
}

describe("Quote", () => {
  it("puts an exact passage on the highlighter when asked", () => {
    const { container } = render(<Quote citation={citation({})} files={files} highlight />);
    expect(marked(container)).toHaveTextContent("Run 7 was completed on February 20, 2026");
  });

  it("never highlights a quote it wasn't asked to", () => {
    const { container } = render(<Quote citation={citation({})} files={files} />);
    expect(marked(container)).toBeNull();
  });

  it("sets a close match in the serif without yellow, with the viewer's words for it", () => {
    const { container } = render(<Quote citation={citation({ match: "close" })} files={files} highlight />);
    expect(marked(container)).toBeNull();
    expect(screen.getByText("Run 7 was completed on February 20, 2026")).toBeInTheDocument();
    expect(container.querySelector("figcaption")).toHaveTextContent("Close match on the page");
  });

  it("shows a passage the server didn't find plain", () => {
    const { container } = render(<Quote citation={citation({ match: "not_found" })} files={files} highlight />);
    expect(marked(container)).toBeNull();
    expect(container.querySelector("figcaption")).not.toHaveTextContent("Close match");
  });

  it("shows a box on a photo or scan plain", () => {
    const box = citation({ location: { type: "image_box", page: 1, left: 0.1, top: 0.1, width: 0.2, height: 0.1 } as Citation["location"] });
    const { container } = render(<Quote citation={box} files={files} highlight />);
    expect(marked(container)).toBeNull();
  });

  it("names the file and the page after the passage", () => {
    const { container } = render(<Quote citation={citation({})} files={files} />);
    expect(container.querySelector("figcaption")).toHaveTextContent("statement.pdf, p. 2");
  });

  it("makes the passage the link into the viewer, once", () => {
    render(<Quote citation={citation({})} files={files} href="/viewer" highlight />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveTextContent("Run 7 was completed on February 20, 2026");
    expect(links[0]).toHaveAttribute("href", "/viewer");
  });

  it("describes the link with the file and where in it, so it says what it opens", () => {
    render(<Quote citation={citation({ match: "close" })} files={files} href="/viewer" />);
    const link = screen.getByRole("link", { name: "Run 7 was completed on February 20, 2026" });
    expect(link).toHaveAccessibleDescription("statement.pdf, p. 2 · Close match on the page");
  });
});
