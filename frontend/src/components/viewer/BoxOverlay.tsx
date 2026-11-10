import type { Box } from "./placement";
import styles from "./viewer.module.css";

/**
 * Outlines the boxes on one page. Boxes are fractions of the page, so they
 * scale with it at any zoom. The first box is where the viewer scrolls.
 */
export function BoxOverlay({ boxes, first }: { boxes: readonly Box[]; first: Box | null }) {
  return (
    <>
      {boxes.map((b, i) => (
        <span
          key={i}
          className={styles.box}
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
    </>
  );
}
