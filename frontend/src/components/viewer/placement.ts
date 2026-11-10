import type { Citation } from "@/lib/api";

// Where the viewer draws a citation. The server matched it once, when the
// record was saved, and stored where the highlight goes (decision 0012). This
// file only reads what was stored; it never searches a file for a passage and
// never guesses a spot.
//
// Locations use the Anthropic API's names and counting (contracts.md, Cited
// values). The citation's location is read defensively here, so the viewer
// works whether the shared types carry it loosely or as a tagged union.

/** A box on a page, as fractions of the page from its top left corner. */
export interface Box {
  page: number;
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Characters in the file's stored text, counted the server's way (code points), end exclusive. */
export interface CharSpan {
  start: number;
  end: number;
}

/** The citation the viewer reads (records.py Citation). */
export type CitationLike = Citation;

export type Placement =
  /** Text, email or .docx: the exact characters to highlight, one span or several. */
  | { kind: "text"; spans: CharSpan[]; passageStart: number; passage: string }
  /** A PDF page with real text, or a photo or scan: boxes to outline. */
  | { kind: "boxes"; boxes: Box[]; passage: string | null }
  /**
   * A fact that couldn't be placed: open its page, if it names one, and show
   * the quote beside it. No highlight.
   */
  | { kind: "unplaced"; page: number | null; quote: string | null };

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function asBox(v: unknown, fallbackPage = 1): Box | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  const left = num(o.left);
  const top = num(o.top);
  const width = num(o.width);
  const height = num(o.height);
  if (left === null || top === null || width === null || height === null) return null;
  return { page: num(o.page) ?? fallbackPage, left, top, width, height };
}

function asSpan(v: unknown): CharSpan | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  const start = num(o.start_char_index);
  const end = num(o.end_char_index);
  return start !== null && end !== null && end > start ? { start, end } : null;
}

/** The location's fields, read as plain data. */
function fields(c: CitationLike): Record<string, unknown> & { type: string } {
  return c.location as unknown as Record<string, unknown> & { type: string };
}

/** The page a citation names, for opening the viewer there. */
export function citationPage(c: CitationLike): number | null {
  const loc = fields(c);
  if (loc.type === "page_location") return num(loc.start_page_number);
  if (loc.type === "image_box") return num(loc.page) ?? 1;
  return null;
}

/** The page caption on an evidence card: "p. 2", "pp. 2-3", or null when the citation has no page. */
export function pageCaption(c: CitationLike): string | null {
  const loc = fields(c);
  if (loc.type === "page_location") {
    const start = num(loc.start_page_number);
    const end = num(loc.end_page_number); // end exclusive
    if (start === null) return null;
    return end !== null && end - 1 > start ? `pp. ${start}-${end - 1}` : `p. ${start}`;
  }
  if (loc.type === "image_box") return `p. ${num(loc.page) ?? 1}`;
  return null;
}

/** True when the server found the citation in its file. */
export function isFound(c: CitationLike): boolean {
  return c.match === "exact" || c.match === "close";
}

/**
 * Where the viewer draws a citation.
 *
 * - Text and email (`char_location`), found: the stored character ranges, or
 *   the cited characters themselves when no finer ranges were stored.
 * - PDF with real text (`page_location`), found: the stored boxes on the page.
 * - Photo or scan (`image_box`), found by the second look: the box.
 * - Anything else, including a match that wasn't found, a PDF match with no
 *   stored boxes, and a custom content document: unplaced.
 *
 * `valueText` is what the document writes for the value. It stands in as the
 * quote for a photo or scan, which has no passage.
 */
export function placeCitation(c: CitationLike, valueText: string | null = null): Placement {
  const loc = fields(c);
  const unplaced: Placement = { kind: "unplaced", page: citationPage(c), quote: c.passage ?? valueText };
  if (!isFound(c)) return unplaced;

  if (loc.type === "char_location" && c.passage !== null) {
    const whole = asSpan(loc);
    if (!whole) return unplaced;
    const stored = (c.highlight ?? []).map(asSpan).filter((s): s is CharSpan => s !== null);
    return { kind: "text", spans: stored.length > 0 ? stored : [whole], passageStart: whole.start, passage: c.passage };
  }
  if (loc.type === "page_location") {
    const boxes = (c.highlight ?? []).map((b) => asBox(b)).filter((b): b is Box => b !== null);
    return boxes.length > 0 ? { kind: "boxes", boxes, passage: c.passage } : unplaced;
  }
  if (loc.type === "image_box") {
    const box = asBox(loc);
    return box ? { kind: "boxes", boxes: [box], passage: null } : unplaced;
  }
  return unplaced;
}

/**
 * The zoom that opens a box at a readable size: the box takes about half the
 * viewer's width, never smaller than the whole page and never more than 3x.
 */
export function zoomForBoxes(boxes: readonly Box[]): number {
  if (boxes.length === 0) return 1;
  const widest = Math.max(...boxes.map((b) => b.width));
  const zoom = 0.5 / widest;
  return Math.min(3, Math.max(1, Math.round(zoom * 4) / 4));
}
