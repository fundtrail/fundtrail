import type { Box } from "./placement";
import styles from "./viewer.module.css";

/**
 * Draws the boxes on one page, exactly where they were stored. Boxes are
 * fractions of the page, so they scale with it at any zoom. The first box is
 * where the viewer scrolls.
 *
 * - `mark`, for a PDF passage with real text: a highlighter. The boxes are one
 *   layer multiplied over the rendered page, so the words stay readable through
 *   the yellow, and overlapping boxes never stack darker.
 * - `box`, for a photo or a scan: an outlined box with a light wash, because a
 *   second look checked the area, not the characters.
 *
 * The first box carries the name a screen reader announces, saying what it
 * marks; the rest of the same passage are hidden from it.
 */
export function BoxOverlay({
  boxes,
  first,
  variant = "box",
  label = null,
}: {
  boxes: readonly Box[];
  first: Box | null;
  variant?: "mark" | "box";
  /** What the value is, for example "Total". */
  label?: string | null;
}) {
  if (boxes.length === 0) return null;
  const what = variant === "mark" ? "highlighted passage" : "box checked by a second look";
  const name = `${label ?? "Value"}, ${what}`;
  return (
    <div className={variant === "mark" ? styles.markLayer : styles.boxLayer} data-variant={variant}>
      {boxes.map((b, i) => (
        <span
          key={i}
          className={variant === "mark" ? styles.markBox : styles.box}
          data-testid="highlight-box"
          data-scroll-target={b === first ? "true" : undefined}
          role={b === first ? "img" : undefined}
          aria-label={b === first ? name : undefined}
          aria-hidden={b === first ? undefined : true}
          style={{
            left: `${b.left * 100}%`,
            top: `${b.top * 100}%`,
            width: `${b.width * 100}%`,
            height: `${b.height * 100}%`,
          }}
        />
      ))}
    </div>
  );
}
