/**
 * The sign-in page's one piece of art: the trail drawn large. Solid where
 * evidence holds (a dot, a ring with a check), the yellow dot for now, then a
 * dashed stretch where evidence is missing, and a diamond where the trail
 * breaks. Pure geometry, colored from the page's tokens through its classes.
 */
export function TrailArt({ className, classes }: { className?: string; classes: Record<string, string> }) {
  return (
    <svg className={className} viewBox="0 0 600 120" fill="none" aria-hidden="true" focusable="false">
      <path className={classes.held} d="M0 60H320" strokeWidth="3" />
      <path className={classes.gap} d="M334 60H600" strokeWidth="3" strokeDasharray="9 9" />
      <circle className={classes.dot} cx="66" cy="60" r="10" />
      <circle className={classes.ring} cx="193" cy="60" r="12" strokeWidth="3" />
      <path className={classes.check} d="M187.2 60.6l4 4 7.6-8.2" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle className={classes.nowRing} cx="320" cy="60" r="23" strokeWidth="1.5" />
      <circle className={classes.now} cx="320" cy="60" r="13" />
      <rect className={classes.break} x="437" y="50" width="20" height="20" transform="rotate(45 447 60)" />
    </svg>
  );
}
