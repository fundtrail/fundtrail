// Splitting stored text into plain and highlighted pieces.
//
// The server counts characters the way Python does: one per Unicode code
// point. JavaScript strings count UTF-16 units, so a character outside the
// Basic Multilingual Plane (an emoji, say) is two units here and one there.
// Every index from the server goes through toUnits before it touches a string.

import type { CharSpan } from "./placement";

/** Turns code-point indexes into UTF-16 indexes for one string. */
export function codePointIndexer(text: string): (codePoint: number) => number {
  // Fast path: no surrogate pairs, so the two counts agree.
  if (!/[\uD800-\uDBFF]/.test(text)) return (i) => Math.min(Math.max(i, 0), text.length);
  const units: number[] = [];
  let u = 0;
  for (const ch of text) {
    units.push(u);
    u += ch.length;
  }
  units.push(u);
  return (i) => units[Math.min(Math.max(i, 0), units.length - 1)];
}

export interface Piece {
  text: string;
  marked: boolean;
  /** The first marked piece, which the viewer scrolls to. */
  first: boolean;
}

/**
 * Splits `text` into pieces, marking the spans. `offset` is the code-point
 * index in the stored text where `text` starts (0 for the whole file, the
 * passage's start when only the passage is shown). Overlapping spans merge,
 * and a span outside the text is dropped.
 */
export function splitBySpans(text: string, spans: readonly CharSpan[], offset = 0): Piece[] {
  const toUnits = codePointIndexer(text);
  const ranges = spans
    .map((s) => ({ start: toUnits(s.start - offset), end: toUnits(s.end - offset) }))
    .filter((r) => r.end > r.start)
    .sort((a, b) => a.start - b.start);

  const merged: { start: number; end: number }[] = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r.start <= last.end) last.end = Math.max(last.end, r.end);
    else merged.push({ ...r });
  }

  const pieces: Piece[] = [];
  let at = 0;
  merged.forEach((r, i) => {
    if (r.start > at) pieces.push({ text: text.slice(at, r.start), marked: false, first: false });
    pieces.push({ text: text.slice(r.start, r.end), marked: true, first: i === 0 });
    at = r.end;
  });
  if (at < text.length) pieces.push({ text: text.slice(at), marked: false, first: false });
  return pieces;
}
