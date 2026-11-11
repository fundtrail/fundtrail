import type { Box } from "./placement";
import styles from "./viewer.module.css";

/**
 * Draws the boxes on one page. Boxes are fractions of the page, so they scale
 * with it at any zoom. The first box is where the viewer scrolls.
 *
 * - `mark`, for a PDF passage with real text: a highlighter. The boxes are one
 *   layer multiplied over the rendered page, so the words stay readable through
 *   the yellow and the boxes of one passage read as one stroke where they meet.
 * - `box`, for a photo or a scan: an outlined box with a light wash, because a
 *   second look checked the area, not the characters.
 */
export function BoxOverlay({
  boxes,
  first,
  variant = "box",
}: {
  boxes: readonly Box[];
  first: Box | null;
  variant?: "mark" | "box";
}) {
  if (boxes.length === 0) return null;
  return (
    <div className={variant === "mark" ? styles.markLayer : styles.boxLayer} data-variant={variant}>
      {boxes.map((b, i) => (
        <span
          key={i}
          className={variant === "mark" ? styles.markBox : styles.box}
          data-testid="highlight-box"
          data-scroll-target={b === first ? "true" : undefined}
          aria-label="Highlighted value"
          role="img"
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
