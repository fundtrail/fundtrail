/**
 * The sign-in page's one piece of art: the trail drawn large. Solid where
 * evidence holds (a dot, a ring with a check), a diamond where the trail
 * breaks and the solid line turns dashed, then the dashed stretch where
 * evidence is missing, with the yellow dot for now on it. Pure geometry,
 * colored from the page's tokens through its classes. The solid part never
 * moves; only the stretch after the break draws in (see signin.module.css).
 */
export function TrailArt({ className, classes }: { className?: string; classes: Record<string, string> }) {
  return (
    <svg className={className} viewBox="0 0 600 120" fill="none" aria-hidden="true" focusable="false">
      <path className={classes.held} d="M0 60H300" strokeWidth="3" />
      <circle className={classes.dot} cx="66" cy="60" r="10" />
      <circle className={classes.ring} cx="183" cy="60" r="12" strokeWidth="3" />
      <path className={classes.check} d="M177.2 60.6l4 4 7.6-8.2" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
      <g className={classes.after}>
        <path className={classes.gap} d="M318 60H600" strokeWidth="3" strokeDasharray="9 9" />
        <circle className={classes.now} cx="453" cy="60" r="12" strokeWidth="5" />
      </g>
      <rect className={classes.break} x="290" y="50" width="20" height="20" transform="rotate(45 300 60)" />
    </svg>
  );
}
