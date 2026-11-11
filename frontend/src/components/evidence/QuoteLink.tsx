"use client";

import Link from "next/link";
import { useState } from "react";
import type { Citation } from "@/lib/api";
import { CLOSE_MATCH } from "@/components/viewer/words";
import styles from "./evidence.module.css";
import { excerptWindow, isExact, segments, valueRanges, type Range } from "./quote";

/** A small chevron at the end of a quote: it opens the file at that spot, in the app. */
function OpensIcon() {
  return (
    <svg className={styles.opens} viewBox="0 0 12 12" aria-hidden="true" focusable="false">
      <path d="M4.5 2.5 8 6 4.5 9.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * A value's quote on a card, linking to the viewer at its spot.
 *
 * - An exact passage is set in the serif on a quiet highlighter. A close
 *   match is the passage found, but not word for word, so it shows plain with
 *   the viewer's words for it; so does a quote that couldn't be placed.
 * - Where the stored ranges say where the value sits, its characters are set
 *   stronger, and a long quote shows the part around the value, with an
 *   ellipsis where it's cut, so the value is never hidden. "Show the whole
 *   quote" opens the full passage in place. Where the value's place isn't
 *   known, the whole quote shows.
 * - A photo's box has no passage, and says so plainly.
 *
 * `ranges` overrides where the values sit, for a passage shown once for
 * several values that cite it.
 */
export function QuoteLink({
  citation,
  href,
  ariaLabel,
  ranges,
}: {
  citation: Citation;
  href: string;
  ariaLabel?: string;
  ranges?: Range[] | null;
}) {
  const [open, setOpen] = useState(false);
  const passage = citation.passage;

  if (passage === null) {
    return (
      <Link className={`${styles.quote} ${styles.quoteBox}`} href={href} aria-label={ariaLabel}>
        <span className={styles.quoteText}>A box on the image</span>
        <OpensIcon />
      </Link>
    );
  }

  const valueAt = ranges === undefined ? valueRanges(citation) : ranges;
  const excerpt = excerptWindow(passage, valueAt);
  const shown = open || !excerpt ? { start: 0, end: passage.length } : excerpt;
  const text = segments(passage, shown, valueAt).map((s, i) =>
    s.value ? (
      <strong key={i} className={styles.valueChars}>
        {s.text}
      </strong>
    ) : (
      <span key={i}>{s.text}</span>
    ),
  );
  const exact = isExact(citation);

  return (
    <span className={styles.quoteWrap}>
      <Link className={styles.quote} href={href} aria-label={ariaLabel}>
        <span className={shown === excerpt ? `${styles.quoteText} ${styles.excerpt}` : styles.quoteText} data-testid="card-quote">
          {shown.start > 0 && <span className={styles.ellipsis}>…</span>}
          {exact ? <mark className={styles.hl}>{text}</mark> : text}
          {shown.end < passage.length && <span className={styles.ellipsis}>…</span>}
        </span>
        <OpensIcon />
      </Link>
      {citation.match === "close" && <span className={styles.matchNote}>{CLOSE_MATCH}</span>}
      {excerpt && (
        <button type="button" className={styles.more} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? "Show less" : "Show the whole quote"}
        </button>
      )}
    </span>
  );
}
