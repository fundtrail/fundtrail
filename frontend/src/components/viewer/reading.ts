// Mapping highlights from the stored email into the text the agent reads
// (ruling 45, first version).
//
// On a sample grant the server serves `reading` beside the original: the text
// the agent read, with the grant's date in place of the message's own. Its
// segments are the spans kept from the stored file, in order; the gaps between
// them are headers replaced or dropped. Citations and highlights stay in stored
// character positions, so each one is carried forward through the segments.
// Every position here counts code points, as the server does.
//
// Known limit (ruling 49, accepted for the first version): the segments say
// only what was kept, not which part of a gap was replaced and which was
// dropped. A dropped header that sits next to the replaced Date header shares
// its gap, so a range inside the dropped header highlights the Date line. The
// agent's citations never land in dropped headers, because it never reads them.

import type { TextSegment } from "@/lib/api/types";
import type { CharSpan } from "./placement";

interface Gap {
  /** The gap's whole region in the reading text, between the kept spans around it. */
  region: CharSpan;
  /** The replaced line inside it, without line breaks; empty when the header was only dropped. */
  line: CharSpan;
}

/** The gap holding a stored position that no kept span holds. */
function gapAt(segments: readonly TextSegment[], storedAt: number, chars: readonly string[]): Gap {
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
  const end = Math.max(start, after ? after.reading_start : chars.length);
  let a = start;
  let b = end;
  while (a < b && (chars[a] === "\n" || chars[a] === "\r")) a++;
  while (b > a && (chars[b - 1] === "\n" || chars[b - 1] === "\r")) b--;
  return { region: { start, end }, line: { start: a, end: b } };
}

/** The kept span holding a stored character, if any. */
function segmentAt(segments: readonly TextSegment[], storedAt: number): TextSegment | null {
  return segments.find((s) => s.stored_start <= storedAt && storedAt < s.stored_start + s.length) ?? null;
}

/**
 * Carries one highlight from stored positions into the reading text.
 *
 * Each end is placed on its own:
 * - an end inside a kept span moves with the span;
 * - an end inside a gap reaches out to the gap's replaced line, so a range
 *   that starts or ends in the replaced Date header keeps the Date line;
 * - an end inside a gap with no replaced line (a dropped header) stops at the
 *   kept text beside the gap.
 * A range inside one gap therefore highlights its replaced line, or nothing
 * when the header was dropped. An empty range highlights nothing.
 */
export function mapSpanToReading(span: CharSpan, segments: readonly TextSegment[], readingText: string): CharSpan | null {
  if (span.end <= span.start) return null;
  const sorted = [...segments].sort((a, b) => a.stored_start - b.stored_start);
  const chars = Array.from(readingText); // code points, as the server counts

  let start: number;
  const first = segmentAt(sorted, span.start);
  if (first) start = first.reading_start + (span.start - first.stored_start);
  else {
    const gap = gapAt(sorted, span.start, chars);
    start = gap.line.end > gap.line.start ? gap.line.start : gap.region.end;
  }

  let end: number;
  const last = segmentAt(sorted, span.end - 1);
  if (last) end = last.reading_start + (span.end - last.stored_start);
  else {
    const gap = gapAt(sorted, span.end - 1, chars);
    end = gap.line.end > gap.line.start ? gap.line.end : gap.region.start;
  }

  return end > start ? { start, end } : null;
}

/** Carries every highlight into the reading text, dropping any that land nowhere. */
export function mapSpansToReading(spans: readonly CharSpan[], segments: readonly TextSegment[], readingText: string): CharSpan[] {
  return spans.map((s) => mapSpanToReading(s, segments, readingText)).filter((s): s is CharSpan => s !== null);
}

/**
 * For a view that shows only the cited passage (ruling 50): on a sample grant
 * the passage is reading text, while its location and highlights stay in stored
 * positions. Returns the highlights in reading positions and where the passage
 * starts in the reading text, to split the passage by.
 */
export function passageInReading(
  spans: readonly CharSpan[],
  passageStart: number,
  segments: readonly TextSegment[],
  readingText: string,
): { spans: CharSpan[]; offset: number } {
  const sorted = [...segments].sort((a, b) => a.stored_start - b.stored_start);
  const kept = segmentAt(sorted, passageStart);
  let offset: number;
  if (kept) offset = kept.reading_start + (passageStart - kept.stored_start);
  else {
    // A passage that starts in a gap starts on the replaced line, or on the kept text after a dropped header.
    const gap = gapAt(sorted, passageStart, Array.from(readingText));
    offset = gap.line.end > gap.line.start ? gap.line.start : gap.region.end;
  }
  return { spans: mapSpansToReading(spans, segments, readingText), offset };
}
