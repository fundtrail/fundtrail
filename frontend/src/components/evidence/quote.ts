// How a card shows a value's quote: where the value sits inside it, and which
// part of a long quote to show so the value is never cut off.
//
// This reads only what the server stored (the citation's character ranges, as
// the viewer reads them). It never searches the passage for the value's text.

import type { Citation } from "@/lib/api";
import { placeCitation } from "@/components/viewer/placement";
import { splitBySpans } from "@/components/viewer/textSpans";

/** A range in the passage string, in UTF-16 units, end exclusive. */
export interface Range {
  start: number;
  end: number;
}

/** A quote longer than this many characters, or on three lines or more, is shown as an excerpt. */
export const QUOTE_LIMIT = 160;
/** How much of the quote to keep before the value in an excerpt. */
const BEFORE = 48;

/** True when the quote is the passage word for word, so it goes on the highlighter. */
export function isExact(c: Citation): boolean {
  return c.match === "exact";
}

/**
 * Where the value's own characters sit in the citation's passage, or null when
 * that isn't known: the citation isn't a text passage that was found, no finer
 * ranges were stored, or the passage shown isn't the stored characters (so the
 * stored positions don't count in it). Ranges that cover the whole passage say
 * nothing about where the value is, so they're null too.
 */
export function valueRanges(c: Citation): Range[] | null {
  const passage = c.passage;
  if (passage === null || !c.highlight || c.highlight.length === 0) return null;
  const placement = placeCitation(c);
  if (placement.kind !== "text") return null;
  const loc = c.location as unknown as { start_char_index?: unknown; end_char_index?: unknown };
  const stored = Number(loc.end_char_index) - Number(loc.start_char_index);
  if (!Number.isFinite(stored) || [...passage].length !== stored) return null;

  const ranges: Range[] = [];
  let at = 0;
  for (const piece of splitBySpans(passage, placement.spans, placement.passageStart)) {
    if (piece.marked) ranges.push({ start: at, end: at + piece.text.length });
    at += piece.text.length;
  }
  if (ranges.length === 0) return null;
  if (ranges.length === 1 && ranges[0].start === 0 && ranges[0].end === passage.length) return null;
  return ranges;
}

/** Every range of several citations of the same passage, merged and in order. */
export function unionRanges(all: (Range[] | null)[]): Range[] | null {
  const ranges = all.flatMap((r) => r ?? []).sort((a, b) => a.start - b.start);
  if (ranges.length === 0) return null;
  const merged: Range[] = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r.start <= last.end) last.end = Math.max(last.end, r.end);
    else merged.push({ ...r });
  }
  return merged;
}

export function isLongQuote(passage: string): boolean {
  return passage.length > QUOTE_LIMIT || (passage.match(/\n/g)?.length ?? 0) >= 2;
}

/**
 * The part of a long passage to show on a card: a window around the value's
 * first range (and its last, when they fit together), cut at word breaks, so
 * the value is always inside it. Null when the passage is short enough to show
 * whole, or when the value's place isn't known (then nothing is clamped).
 */
export function excerptWindow(passage: string, ranges: Range[] | null): Range | null {
  if (!ranges || ranges.length === 0 || !isLongQuote(passage)) return null;
  const valueStart = ranges[0].start;
  let valueEnd = ranges[ranges.length - 1].end;
  if (valueEnd - valueStart > QUOTE_LIMIT) valueEnd = ranges[0].end;

  let start = Math.max(0, valueStart - BEFORE);
  if (start > 0) {
    // Start at the next word, but never after the value.
    const next = passage.slice(start, valueStart).search(/\s/);
    if (next >= 0) start += next + 1;
  }
  let end = Math.min(passage.length, Math.max(valueEnd, start + QUOTE_LIMIT));
  if (end < passage.length) {
    // End at the last word break, but never before the value.
    const tail = passage.slice(valueEnd, end);
    const lastBreak = Math.max(tail.lastIndexOf(" "), tail.lastIndexOf("\n"));
    if (lastBreak >= 0) end = valueEnd + lastBreak;
  }
  if (start === 0 && end === passage.length) return null;
  return { start, end };
}

/** The window's text split into plain and value pieces, for setting the value stronger. */
export function segments(passage: string, window: Range, ranges: Range[] | null): { text: string; value: boolean }[] {
  const out: { text: string; value: boolean }[] = [];
  let at = window.start;
  for (const r of ranges ?? []) {
    const s = Math.max(r.start, window.start);
    const e = Math.min(r.end, window.end);
    if (e <= s) continue;
    if (s > at) out.push({ text: passage.slice(at, s), value: false });
    out.push({ text: passage.slice(s, e), value: true });
    at = e;
  }
  if (at < window.end) out.push({ text: passage.slice(at, window.end), value: false });
  return out;
}
