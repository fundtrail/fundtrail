/**
 * The wordmark's glyph, the trail: a dot, a ring, a dashed stretch and the
 * highlighter's diamond. Drawn in currentColor, so it takes the text color of
 * where it sits. The same drawing as the sidebar's (AppShell.tsx), at any size.
 */
export function TrailMark({ className, width = 30 }: { className?: string; width?: number }) {
  return (
    <svg
      className={className}
      width={width}
      height={(width * 16) / 30}
      viewBox="0 0 30 16"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M3 8h9" stroke="currentColor" strokeWidth="2" />
      <path d="M15 8h6" stroke="currentColor" strokeWidth="2" strokeDasharray="2 2" />
      <circle cx="3.5" cy="8" r="3.5" fill="currentColor" />
      <circle cx="13" cy="8" r="2.6" fill="none" stroke="currentColor" strokeWidth="2" />
      <rect className="ft-wordmark__diamond" x="21.2" y="4.2" width="7.6" height="7.6" transform="rotate(45 25 8)" />
    </svg>
  );
}

/**
 * The start of a trail, for a place with nothing on it yet: the yellow dot for
 * now, then a dashed stretch to an open ring. Colored by the classes given.
 */
export function TrailStart({ className, classes }: { className?: string; classes: Record<string, string> }) {
  return (
    <svg className={className} width="112" height="28" viewBox="0 0 112 28" fill="none" aria-hidden="true" focusable="false">
      <path className={classes.startGap} d="M25 14H91" strokeWidth="2" strokeDasharray="5 5" />
      <circle className={classes.startRing} cx="102" cy="14" r="7" strokeWidth="2" strokeDasharray="3.5 2.4" />
      <circle className={classes.startNowRing} cx="12" cy="14" r="11" strokeWidth="1.25" />
      <circle className={classes.startNow} cx="12" cy="14" r="6.5" />
    </svg>
  );
}
