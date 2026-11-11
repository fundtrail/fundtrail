"use client";

import { useId, useState, type ReactNode } from "react";
import type { CharRange, Citation } from "@/lib/api";

/** A run of characters within a passage, start inclusive, end exclusive. */
export interface Span {
  start: number;
  end: number;
}

function isCharRange(h: unknown): h is CharRange {
  return typeof h === "object" && h !== null && "start_char_index" in h && "end_char_index" in h;
}

/**
 * Where the value's own characters sit in the passage, from the ranges the
 * server stored with the citation (char_location only), measured from the
 * passage's start. Null when the server didn't say: then the quote is never cut.
 */
export function valueSpans(citation: Citation): Span[] | null {
  const loc = citation.location;
  const passage = citation.passage;
  if (loc.type !== "char_location" || passage === null) return null;
  const spans = (citation.highlight ?? [])
    .filter(isCharRange)
    .map((r) => ({ start: r.start_char_index - loc.start_char_index, end: r.end_char_index - loc.start_char_index }))
    .filter((s) => s.start >= 0 && s.end <= passage.length && s.end > s.start)
    .sort((a, b) => a.start - b.start);
  return spans.length > 0 ? spans : null;
}

/** Characters of the passage kept around the value when a quote is cut short. */
const BEFORE = 60;
const AFTER = 100;
/** The most characters the value's ranges may cover, first to last, for the quote to be cut short. */
const WINDOW = 120;

/**
 * The part of a long passage to show: the value's characters with some words
 * either side, cut at word breaks. A quote is cut short only when every value
 * it stands for is inside the part shown, so this is null, and the whole
 * passage shows, when the passage is short, when any value's place in it isn't
 * known (null spans), or when the values' ranges spread wider than the window.
 */
export function quoteExcerpt(passage: string, spans: Span[] | null): Span | null {
  if (!spans || spans.length === 0) return null;
  const first = Math.min(...spans.map((s) => s.start));
  const last = Math.max(...spans.map((s) => s.end));
  if (last - first > WINDOW) return null;
  let start = Math.max(0, first - BEFORE);
  let end = Math.min(passage.length, last + AFTER);
  if (start > 0) {
    const space = passage.lastIndexOf(" ", start);
    start = space >= 0 ? space + 1 : 0;
  }
  if (end < passage.length) {
    const space = passage.indexOf(" ", end);
    end = space >= 0 ? space : passage.length;
  }
  if (start === 0 && end === passage.length) return null;
  return { start, end };
}

/** The passage between start and end, with the value's characters set stronger. */
function withValue(passage: string, from: Span, spans: Span[] | null): ReactNode[] {
  const parts: ReactNode[] = [];
  let at = from.start;
  for (const s of spans ?? []) {
    const start = Math.max(s.start, from.start);
    const end = Math.min(s.end, from.end);
    if (end <= start || start < at) continue;
    if (start > at) parts.push(passage.slice(at, start));
    parts.push(<strong key={start}>{passage.slice(start, end)}</strong>);
    at = end;
  }
  if (at < from.end) parts.push(passage.slice(at, from.end));
  return parts;
}

/**
 * A value's quote, in the file's own words. Only an exact match carries the
 * highlighter; a close match is serif without it, with the viewer's words for
 * it beside; anything not found shows plain. A long passage shows the part
 * around the value, never cutting the value off, and opens in place.
 */
export function TermQuote({ citation, spans }: { citation: Citation & { passage: string }; spans: Span[] | null }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const passage = citation.passage;
  const cut = quoteExcerpt(passage, spans);
  const shown = open || !cut ? { start: 0, end: passage.length } : cut;
  const words = withValue(passage, shown, spans);
  // The highlighter needs an exact match of a passage that is text: a box on an image is never highlighted.
  const isText = citation.location.type !== "image_box";
  const match = !isText ? "plain" : citation.match === "exact" ? "exact" : citation.match === "close" ? "close" : "plain";

  return (
    <div className="ft-tq">
      <blockquote id={id} className={`ft-tq__text is-${match}`}>
        {shown.start > 0 && <span className="ft-tq__cut">… </span>}
        {match === "exact" ? <mark>{words}</mark> : words}
        {shown.end < passage.length && <span className="ft-tq__cut"> …</span>}
      </blockquote>
      {(match === "close" || cut) && (
        <p className="ft-tq__foot">
          {match === "close" && <span>Close match on the page</span>}
          {cut && (
            <button type="button" className="ft-linkbtn" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
              {open ? "Show less" : "Show the whole quote"}
            </button>
          )}
        </p>
      )}
    </div>
  );
}
