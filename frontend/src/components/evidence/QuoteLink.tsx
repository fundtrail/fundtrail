"use client";

import Link from "next/link";
import { useLayoutEffect, useRef, useState } from "react";
import type { Citation } from "@/lib/api";
import { isFound } from "@/components/viewer/placement";
import styles from "./evidence.module.css";

/**
 * A value's quote on a card, linking to the viewer at its spot. A passage the
 * server found in the file is shown verbatim in the serif on the highlighter;
 * one it couldn't place shows plain, and a photo's box, which has no passage,
 * says so in the interface font. A long quote is clamped to two lines, with a
 * button to read the whole of it in place.
 */
export function QuoteLink({ citation, href, ariaLabel }: { citation: Citation; href: string; ariaLabel?: string }) {
  const textRef = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  const [clamped, setClamped] = useState(false);
  const passage = citation.passage;

  useLayoutEffect(() => {
    const el = textRef.current;
    if (!el || open) return;
    const measure = () => setClamped(el.scrollHeight > el.clientHeight + 1);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [open, passage]);

  if (passage === null) {
    return (
      <Link className={`${styles.quote} ${styles.quoteBox}`} href={href} aria-label={ariaLabel}>
        A box on the image
      </Link>
    );
  }

  const verbatim = isFound(citation);
  return (
    <span className={styles.quoteWrap}>
      <Link className={styles.quote} href={href} aria-label={ariaLabel}>
        <span ref={textRef} className={open ? styles.quoteText : `${styles.quoteText} ${styles.clamp}`}>
          {verbatim ? <mark className={styles.hl}>{passage}</mark> : passage}
        </span>
      </Link>
      {(clamped || open) && (
        <button type="button" className={styles.more} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? "Show less" : "Show the whole quote"}
        </button>
      )}
    </span>
  );
}
