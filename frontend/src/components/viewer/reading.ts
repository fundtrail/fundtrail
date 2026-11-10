// Mapping highlights from the stored email into the text the agent reads
// (ruling 45, first version).
//
// On a sample grant the server serves `reading` beside the original: the text
// the agent read, with the grant's date in place of the message's own. Its
// segments are the spans kept from the stored file, in order; the gaps between
// them are headers replaced or dropped. Citations and highlights stay in stored
// character positions, so each one is carried forward through the segments.
// Every position here counts code points, as the server does.

import type { TextSegment } from "@/lib/api/types";
import type { CharSpan } from "./placement";

/** Where a gap between kept spans sits in the reading text: the replaced line, if any. */
function gapInReading(segments: readonly TextSegment[], storedAt: number, readingLength: number): CharSpan {
  // The last segment that starts at or before the position, and the first after it.
  let before: TextSegment | null = null;
  let after: TextSegment | null = null;
  for (const s of segments) {
    if (s.stored_start <= storedAt) before = s;
    else {
      after = s;
      break;
    }
  }
  const start = before ? before.reading_start + before.length : 0;
  const end = after ? after.reading_start : readingLength;
  return { start, end: Math.max(start, end) };
}

/** Trims line breaks off both ends of a range of `text`, so a replaced line highlights as a line. */
function trimBreaks(text: readonly string[], span: CharSpan): CharSpan {
  let { start, end } = span;
  while (start < end && (text[start] === "\n" || text[start] === "\r")) start++;
  while (end > start && (text[end - 1] === "\n" || text[end - 1] === "\r")) end--;
  return { start, end };
}

/**
 * Carries one highlight from stored positions into the reading text.
 *
 * - Inside a kept span, it moves with the span.
 * - Across a gap, it runs from its mapped start to its mapped end, so the
 *   replaced header between them is highlighted too.
 * - Wholly inside a gap (a header that was replaced), it highlights the line
 *   that replaced it. A header that was dropped has no line, so nothing is
 *   highlighted.
 */
export function mapSpanToReading(span: CharSpan, segments: readonly TextSegment[], readingText: string): CharSpan | null {
  const sorted = [...segments].sort((a, b) => a.stored_start - b.stored_start);
  let start: number | null = null;
  let end: number | null = null;
  for (const s of sorted) {
    const from = Math.max(span.start, s.stored_start);
    const to = Math.min(span.end, s.stored_start + s.length);
    if (to <= from) continue;
    const mappedStart = s.reading_start + (from - s.stored_start);
    const mappedEnd = s.reading_start + (to - s.stored_start);
    start = start === null ? mappedStart : Math.min(start, mappedStart);
    end = end === null ? mappedEnd : Math.max(end, mappedEnd);
  }
  if (start !== null && end !== null) return { start, end };

  const chars = Array.from(readingText); // code points, as the server counts
  const replaced = trimBreaks(chars, gapInReading(sorted, span.start, chars.length));
  return replaced.end > replaced.start ? replaced : null;
}

/** Carries every highlight into the reading text, dropping any that land nowhere. */
export function mapSpansToReading(spans: readonly CharSpan[], segments: readonly TextSegment[], readingText: string): CharSpan[] {
  return spans.map((s) => mapSpanToReading(s, segments, readingText)).filter((s): s is CharSpan => s !== null);
}
