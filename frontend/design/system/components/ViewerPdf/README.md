# ViewerPdf

The viewer's body for a PDF with real text: every page of the original, in order, scrolled so the cited passage sits in the middle of the view, with the exact passage highlighted.

**Use it** inside the viewer sheet (`ft-sheet__doc`) when a fact, receipt or approval cites a PDF. Its renderer is `FTViewer.pdf` in the viewer script built into this card and the Demo, with `render`, `target`, `zooms` and `initialView`.

**The consumer provides** the file: its pages and the facts read from it, each with `label`, `value`, `page` and the exact `text` of its passage. When the same text appears twice on a page (the line item and the total), the fact also names its `block`, so the right one is marked.

- Pages keep US Letter proportions (612 by 792 at 100%) on `paper-raised` with a thin `rule` border, and "Page 1 of 2" under each in the interface font. The page text is the document's own, in the document serif.
- Only the active passage is marked, with `mark.ft-mark-hl.is-active`. Other cited passages stay unmarked; the side list and the pager reach them.
- The bar says what is cited and where: "**Total** Exact passage · page 1". The pager steps through the file's facts in order and moves across pages.
- Zoom runs 75% to 200% in five steps. The level shows between the buttons, and each button is disabled at its end. After a zoom, the passage stays in view: centered vertically, and horizontally the view scrolls only as far as it needs to show the whole passage.
- One CSS variable, `--ft-pdf-z`, scales the page, so text stays sharp at every zoom.
- Under reduced motion, moving to a passage jumps instead of scrolling.

Don't: crop the page to the passage, mark every cited passage at once, or call a PDF highlight approximate. With real text, it is exact.

**Hash params, for screenshots:** `#fact=N` picks a fact by index, `&zoom=1.5` sets the zoom, and `&t=dark` sets the dark theme.
