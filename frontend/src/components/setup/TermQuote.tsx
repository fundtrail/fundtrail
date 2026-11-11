"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

/**
 * A value's quote: the passage exactly as the file has it, in serif on the
 * highlighter, held to two lines. When it runs longer, a control opens the
 * whole passage in place. Then "Open the source", as on every quote.
 */
export function TermQuote({ passage, href, muted = false }: { passage: string; href: string; muted?: boolean }) {
  const id = useId();
  const ref = useRef<HTMLQuoteElement>(null);
  const [open, setOpen] = useState(false);
  const [long, setLong] = useState(false);

  // Whether the clamp cuts anything off, measured at the width the row has.
  useEffect(() => {
    const el = ref.current;
    if (!el || open) return;
    const measure = () => setLong(el.scrollHeight > el.clientHeight + 1);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [open, passage]);

  return (
    <div className="ft-tq">
      <blockquote id={id} ref={ref} className={`ft-tq__text${open ? " is-open" : ""}${muted ? " is-muted" : ""}`}>
        <mark>{passage}</mark>
      </blockquote>
      <p className="ft-tq__foot">
        <Link className="ft-link" href={href}>
          Open the source
        </Link>
        {(long || open) && (
          <button type="button" className="ft-linkbtn" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
            {open ? "Show less" : "Show the whole quote"}
          </button>
        )}
      </p>
    </div>
  );
}
