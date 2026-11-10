import { describe, expect, it } from "vitest";
import { pageCaption, placeCitation, zoomForBoxes, type CitationLike } from "./placement";
import { splitBySpans } from "./textSpans";

const chars = (start: number, end: number, extra: Partial<CitationLike> = {}): CitationLike => ({
  file_id: "f",
  passage: "x".repeat(end - start),
  location: { type: "char_location", start_char_index: start, end_char_index: end },
  match: "exact",
  ...extra,
});

describe("placeCitation", () => {
  it("uses the stored ranges for text", () => {
    const p = placeCitation(chars(10, 30, { highlight: [{ start_char_index: 12, end_char_index: 15 }, { start_char_index: 20, end_char_index: 25 }] }));
    expect(p).toMatchObject({ kind: "text", spans: [{ start: 12, end: 15 }, { start: 20, end: 25 }], passageStart: 10 });
  });

  it("is unplaced when the match wasn't found or never ran", () => {
    expect(placeCitation(chars(0, 5, { match: "not_found" })).kind).toBe("unplaced");
    expect(placeCitation(chars(0, 5, { match: null })).kind).toBe("unplaced");
  });

  it("treats a custom content document as unplaced", () => {
    const p = placeCitation({ file_id: "f", passage: "q", location: { type: "content_block_location", start_block_index: 0, end_block_index: 1 }, match: "exact" });
    expect(p).toEqual({ kind: "unplaced", page: null, quote: "q" });
  });
});

describe("pageCaption", () => {
  it("names one page or a range, end exclusive", () => {
    expect(pageCaption({ file_id: "f", passage: "q", location: { type: "page_location", start_page_number: 2, end_page_number: 3 } })).toBe("p. 2");
    expect(pageCaption({ file_id: "f", passage: "q", location: { type: "page_location", start_page_number: 2, end_page_number: 4 } })).toBe("pp. 2-3");
    expect(pageCaption(chars(0, 3))).toBeNull();
  });
});

describe("zoomForBoxes", () => {
  it("zooms so a small box is readable, within 1x and 3x", () => {
    expect(zoomForBoxes([])).toBe(1);
    expect(zoomForBoxes([{ page: 1, left: 0, top: 0, width: 0.25, height: 0.1 }])).toBe(2);
    expect(zoomForBoxes([{ page: 1, left: 0, top: 0, width: 0.8, height: 0.1 }])).toBe(1);
    expect(zoomForBoxes([{ page: 1, left: 0, top: 0, width: 0.01, height: 0.1 }])).toBe(3);
  });
});

describe("splitBySpans", () => {
  it("merges overlapping spans and keeps the text whole", () => {
    const pieces = splitBySpans("abcdefghij", [{ start: 2, end: 5 }, { start: 4, end: 7 }]);
    expect(pieces.map((p) => [p.text, p.marked])).toEqual([["ab", false], ["cdefg", true], ["hij", false]]);
  });

  it("counts from an offset when only the passage is shown", () => {
    const pieces = splitBySpans("Total: $5", [{ start: 107, end: 109 }], 100);
    expect(pieces.filter((p) => p.marked).map((p) => p.text)).toEqual(["$5"]);
  });
});
